from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import uuid
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from db.models import (AutomationSettings, AutomationTask, AutomationWorker, JobSearchPreferences,
                       JobSource, JobPosting, JobMatch, LatexMaster, LatexTailoringRun,
                       ConfirmedSkill, User, WorkspaceSettings)


class SettingsInput(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=180, ge=15, le=1440)
    prepare_resumes: bool = True
    max_preparations: int = Field(default=5, ge=1, le=20)
    minimum_score: int = Field(default=0, ge=0, le=100)  # Legacy setting, no longer used.
    daily_pdf_limit: int = Field(default=5, ge=1, le=20)


def settings_for(db, owner_id):
    row = db.get(AutomationSettings, owner_id)
    return row, SettingsInput(**row.data) if row else SettingsInput()


def lock_owner(db):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(30103101)"))


def require_setup(db, owner_id):
    if not db.get(JobSearchPreferences, owner_id):
        raise HTTPException(409, "Save your job preferences first.")
    from jobs.engine import sources_for
    if not sources_for(db, owner_id):
        raise HTTPException(409, "Enable a job source first.")


def enqueue(db, owner_id, kind, payload, key):
    dedupe = hashlib.sha256(key.encode()).hexdigest()
    existing = db.query(AutomationTask).filter_by(dedupe_key=dedupe).first()
    if existing:
        return existing
    item = AutomationTask(user_id=owner_id, kind=kind, payload=payload, dedupe_key=dedupe,
                          status="queued", result={}, attempts=0)
    try:
        with db.begin_nested():
            db.add(item)
            db.flush()
    except IntegrityError:
        return db.query(AutomationTask).filter_by(dedupe_key=dedupe).one()
    return item


def queue_discovery(db, owner_id, automatic=False, slot=None):
    from jobs.engine import mode
    lock_owner(db)
    require_setup(db, owner_id)
    pending = db.query(AutomationTask).filter(AutomationTask.user_id == owner_id,
        AutomationTask.kind == "discover", AutomationTask.status.in_(["queued", "running"])).first()
    if pending:
        return pending
    return enqueue(db, owner_id, "discover", {"automatic": automatic, "engine": mode()},
                   f"discover:{owner_id}:{slot or uuid.uuid4()}")


def queue_preparation(db, owner_id, job_id, automatic=False):
    job = db.query(JobPosting).filter_by(id=job_id, user_id=owner_id).first()
    if not job:
        raise HTTPException(404, "Job not found.")
    if job.status != "open" or not job.description_complete:
        raise HTTPException(409, "An open job and full description are required.")
    if (job.facts or {}).get("source_expiry_at", "9999") <= datetime.utcnow().isoformat():
        raise HTTPException(410, "This source listing has expired.")
    if not 50 <= len(job.description) <= 50000:
        raise HTTPException(409, "Use a full job description between 50 and 50,000 characters.")
    master = db.query(LatexMaster).filter_by(user_id=owner_id, status="active").first()
    if not master:
        raise HTTPException(409, "Activate your reviewed master first.")
    confirmed = sorted((s.canonical, s.category) for s in db.query(ConfirmedSkill).filter_by(user_id=owner_id))
    key = json.dumps(["prepare-v1", owner_id, job.id, master.id, job.description_hash, confirmed])
    return enqueue(db, owner_id, "prepare", {"job_id": job.id, "master_id": master.id,
        "description_hash": job.description_hash, "automatic": automatic}, key)


def task_json(item):
    return {"id": item.id, "kind": item.kind, "status": item.status, "attempts": item.attempts,
            "error": item.error, "payload": item.payload, "result": item.result,
            "created_at": item.created_at.isoformat(),
            "available_at": item.available_at.isoformat(),
            "finished_at": item.finished_at.isoformat() if item.finished_at else None}


def daily_prepared(db, owner_id, now=None):
    now = now or datetime.utcnow()
    local = now + timedelta(hours=5, minutes=30)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=5, minutes=30)
    rows = db.query(AutomationTask).filter(AutomationTask.user_id == owner_id,
        AutomationTask.kind == "prepare", AutomationTask.status == "succeeded", AutomationTask.finished_at >= start).all()
    return sum(bool(row.result.get("pdf_url")) for row in rows)


def retry_after_seconds(value, now=None):
    """Honor server backoff without allowing malformed/unbounded queue delays."""
    now = now or datetime.utcnow()
    try:
        seconds = float(value)
        if not math.isfinite(seconds):
            return 30
    except (TypeError, ValueError):
        try:
            date = parsedate_to_datetime(str(value))
            if date.tzinfo:
                date = date.astimezone(timezone.utc).replace(tzinfo=None)
            seconds = (date - now).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return 30
    return int(min(86400, max(30, math.ceil(seconds))))


def schedule_due(db, now=None):
    now = now or datetime.utcnow()
    # This process serves only the workspace currently selected in the app.
    workspace = db.get(WorkspaceSettings, 1)
    if not workspace:
        return
    from jobs.search_control import control
    if control(db, workspace.owner_id).get("paused"): return
    row, config = settings_for(db, workspace.owner_id)
    if not row or not config.enabled or (row.next_run_at and row.next_run_at > now):
        return
    try:
        queue_discovery(db, workspace.owner_id, True, (row.next_run_at or now).isoformat())
    except HTTPException:
        # Setup may be removed after enabling. Retry one bounded interval later.
        pass
    row.next_run_at = now + timedelta(minutes=config.interval_minutes)
    db.commit()


def claim(db, worker_id, now=None):
    now = now or datetime.utcnow()
    # A crash cannot leave a running task permanently stuck.
    abandoned = db.query(AutomationTask).filter(AutomationTask.status == "running", AutomationTask.lease_until < now).all()
    for task in abandoned:
        task.status = "queued" if task.attempts < 3 else "failed"
        task.error = "Worker lease expired; recovered after interruption."
        task.lease_owner, task.lease_until = None, None
        if task.status == "failed": task.finished_at = now
    db.flush()
    workspace = db.get(WorkspaceSettings, 1)
    if not workspace:
        db.commit(); return None
    candidates = db.query(AutomationTask).filter(AutomationTask.user_id == workspace.owner_id,
        AutomationTask.status == "queued", AutomationTask.available_at <= now).order_by(AutomationTask.created_at).with_for_update(skip_locked=True).all()
    for task in candidates:
        _, config = settings_for(db, task.user_id)
        if task.payload.get("automatic") and not config.enabled:
            continue
        if task.kind == "prepare" and daily_prepared(db, task.user_id, now) >= config.daily_pdf_limit:
            local = now + timedelta(hours=5, minutes=30)
            task.available_at = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1) - timedelta(hours=5, minutes=30)
            task.error = "Daily PDF limit reached; resumes after midnight Asia/Kolkata."
            continue
        task.status, task.lease_owner = "running", worker_id
        task.lease_until, task.attempts = now + timedelta(minutes=20), task.attempts + 1
        task.error = None
        db.commit()
        return task.id
    db.commit()
    return None


def execute(db, task):
    _, current = settings_for(db, task.user_id)
    if task.payload.get("automatic") and not current.enabled:
        raise HTTPException(409, "Automation was paused before this task started.")
    owner = db.get(User, task.user_id)
    if not owner:
        raise HTTPException(409, "Workspace owner is missing.")
    if task.kind == "discover":
        from jobs.engine import mode
        if task.payload.get("engine", "legacy") != mode():
            raise HTTPException(409, "This task belongs to an inactive discovery engine. Start a new search.")
        from api.jobs import refresh
        search_id = task.payload.get("search_id")
        if search_id:
            from jobs.search_control import control
            current_search = control(db, owner.id)
            if current_search.get("paused") or current_search.get("search_id") != search_id:
                raise HTTPException(409, "This search was cleared or replaced.")
        extra = {"task_id": task.id} if mode() == "oss" else {}
        result = refresh(db, owner, automatic=bool(task.payload.get("automatic")), **extra)
        if task.status == "running": task.lease_until = datetime.utcnow() + timedelta(minutes=20)
        if result["status"] == "failed":
            delay = max((retry_after_seconds(error.get("retry_after_seconds")) for error in result.get("errors", [])), default=30)
            raise HTTPException(503, "All job sources failed. Check source health and retry later.", headers={"Retry-After": str(delay)})
        row, config = settings_for(db, owner.id)
        if row:
            row.last_run_at = datetime.utcnow()
        if (search_id or (config.enabled and task.payload.get("automatic"))) and (
                any(source.get("cursor") for source in result.get("sources", [])) or
                any(source.get("ready") for source in result.get("deferred", []))):
            payload = {"automatic": False, "search_id": search_id, "search_only": True, "engine": mode()} if search_id else {"automatic": True, "engine": mode()}
            followup = enqueue(db, owner.id, "discover", payload, "continue:" + task.id)
            followup.available_at = datetime.utcnow() + timedelta(seconds=10 if mode() == "oss" else 60)
        preparation_ids = []
        if config.prepare_resumes and not task.payload.get("search_only") and (not task.payload.get("automatic") or config.enabled):
            from jobs.service import assess, preferences_for, profile_evidence
            prefs, _ = preferences_for(db, owner.id)
            evidence = profile_evidence(db, owner.id)
            ranked = []
            for job in db.query(JobPosting).filter_by(user_id=owner.id, status="open", description_complete=True):
                match = assess(db, job, prefs, evidence)
                if match.state != "dismissed" and match.assessment["eligibility"] == "eligible":
                    ranked.append((job.published_at or job.first_seen_at, job.id))
            prior_tasks = db.query(AutomationTask).filter_by(user_id=owner.id, kind="prepare").all()
            prior_ids = {item.id for item in prior_tasks}
            capacity = max(0, config.max_preparations - sum(item.status in {"queued", "running"} for item in prior_tasks))
            # Completed/failed dedupe hits must not repeatedly consume the first
            # ranking slots and starve lower jobs. Also bound accumulated pending
            # work when the daily PDF cap has deferred earlier preparations.
            for _, job_id in sorted(ranked, reverse=True):
                if len(preparation_ids) >= capacity:
                    break
                try:
                    preparation = queue_preparation(db, owner.id, job_id, task.payload.get("automatic", False))
                    if preparation.id not in prior_ids and preparation.status == "queued":
                        preparation_ids.append(preparation.id)
                        prior_ids.add(preparation.id)
                except HTTPException:
                    continue
        db.commit()
        return {**result, "preparation_task_ids": preparation_ids}
    if task.kind == "prepare":
        from api.tailor import analyze, AnalyzeRequest, prepare, PrepareRequest, SkillDecision
        job = db.query(JobPosting).filter_by(id=task.payload["job_id"], user_id=owner.id).first()
        master = db.query(LatexMaster).filter_by(id=task.payload["master_id"], user_id=owner.id, status="active").first()
        if not job or not master or job.description_hash != task.payload["description_hash"]:
            raise HTTPException(409, "Job description or active master changed. Queue a fresh preparation.")
        if job.status != "open" or not job.description_complete:
            raise HTTPException(409, "Job is closed or its full description is no longer available.")
        if (job.facts or {}).get("source_expiry_at", "9999") <= datetime.utcnow().isoformat():
            raise HTTPException(410, "This source listing has expired.")
        run = db.get(LatexTailoringRun, task.payload.get("run_id")) if task.payload.get("run_id") else None
        if not run:
            analyzed = analyze(AnalyzeRequest(master_id=master.id, job_description=job.description,
                label=f"{job.company} · {job.title}"[:150]), db, owner)
            run = db.get(LatexTailoringRun, analyzed["id"])
            task.payload = {**task.payload, "run_id": run.id}
            from jobs.service import assess, preferences_for, profile_evidence
            prefs, _ = preferences_for(db, owner.id)
            match = assess(db, job, prefs, profile_evidence(db, owner.id))
            match.tailoring_run_id = run.id
            db.commit()
        confirmed = {s.canonical: s for s in db.query(ConfirmedSkill).filter_by(user_id=owner.id)}
        decisions = [SkillDecision(canonical=c["canonical"], category=confirmed[c["canonical"]].category)
            for c in run.candidates if c["canonical"] in confirmed and confirmed[c["canonical"]].category in master.categories]
        awaiting = [c["name"] for c in run.candidates if c["canonical"] not in {d.canonical for d in decisions}]
        if run.status != "ready":
            prepare(run.id, PrepareRequest(confirmed_skills=decisions), db, owner)
        return {"run_id": run.id, "url": f"/tailor?run={run.id}", "status": "ready",
                "pdf_url": f"/tailor/runs/{run.id}/pdf", "awaiting_confirmation": awaiting,
                "note": "Draft contains only previously confirmed additions. Review omitted suggestions before applying."}
    raise HTTPException(422, "Unknown task type.")


def process_one(factory, worker_id):
    with factory() as db:
        schedule_due(db)
        identifier = claim(db, worker_id)
    if not identifier:
        return False
    with factory() as db:
        task = db.get(AutomationTask, identifier)
        try:
            output = execute(db, task)
            # Do not let a late worker overwrite a task recovered by a new lease.
            task = db.query(AutomationTask).populate_existing().filter_by(id=identifier,
                status="running", lease_owner=worker_id).with_for_update().first()
            if not task:
                db.rollback()
                return True
            task.status, task.result, task.error = "succeeded", output, None
            task.finished_at = datetime.utcnow()
        except Exception as error:
            db.rollback()
            task = db.query(AutomationTask).populate_existing().filter_by(id=identifier,
                status="running", lease_owner=worker_id).with_for_update().first()
            if not task:
                db.rollback()
                return True
            code = error.status_code if isinstance(error, HTTPException) else 503
            task.error = str(error.detail)[:1000] if isinstance(error, HTTPException) else "Background task failed. Check local worker logs and retry."
            transient = code in {429, 502, 503, 504} and "LaTeX" not in task.error and "baseline" not in task.error.lower()
            task.status = "queued" if transient and task.attempts < 3 else "failed"
            server_delay = retry_after_seconds((error.headers or {}).get("Retry-After")) if isinstance(error, HTTPException) else 30
            delay = max(server_delay, 30 * 2 ** max(0, task.attempts - 1))
            task.available_at = datetime.utcnow() + timedelta(seconds=delay)
            if task.status == "failed": task.finished_at = datetime.utcnow()
        task.lease_owner, task.lease_until = None, None
        db.commit()
    return True
