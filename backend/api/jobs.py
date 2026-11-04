"""Personal fresher preferences, read-only source refresh, and ranked job feed."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import uuid
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text, or_, func, case, Float, cast
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from core.workspace import get_workspace_owner
from db.session import get_db
from db.models import (JobSearchPreferences, JobSource, JobPosting, JobMatch, JobRefreshRun,
                       LatexMaster, LatexTailoringRun, JobSourceOccurrence)
from jobs.schemas import (SearchPreferences, SourceInput, ManualJob, FeedInput,
                         EmployerConnectionInput, ExportPreviewInput, ExportImportInput)
from jobs.connectors import board_slug, detect_board, public_url, fetch_source, SourceError, Snapshot, Listing
from jobs.service import preferences_for, profile_evidence, assess, ingest, job_json, evidence_version
from jobs.registry import source_register, EMPLOYERS, capability
from jobs.scheduling import state_for, save_state, source_status, due, next_check, polling_floor
from jobs.verification import candidates, fetch_statuses, apply_statuses
from jobs.directory import company_directory
from jobs.connections import requirements, connect_free_defaults
from jobs.search_control import control, set_control, clear_listings
from jobs.engine import mode, active, sources_for, require_legacy

router = APIRouter(prefix="/jobs", tags=["Job discovery"])


def owned_job(db, identifier, owner):
    job = db.query(JobPosting).filter_by(id=identifier, user_id=owner.id).first()
    if not job: raise HTTPException(404, "Job not found.")
    return job


def source_json(source, db=None):
    return {"id": source.id, "provider": source.provider, "board": source.board, "company": source.company,
            "enabled": source.enabled, "archived": not active(source) and source.provider != "manual", "last_error": source.last_error, "last_count": source.last_count,
            "last_checked_at": source.last_checked_at.isoformat() if source.last_checked_at else None,
            "last_success_at": source.last_success_at.isoformat() if source.last_success_at else None,
            **(source_status(db, source) if db is not None else {})}


@router.get("/preferences")
def get_preferences(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    prefs, confirmed = preferences_for(db, owner.id)
    return {"preferences": prefs.model_dump(mode="json"), "confirmed": confirmed}


@router.put("/preferences")
def save_preferences(request: SearchPreferences, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    saved = db.get(JobSearchPreferences, owner.id)
    if not saved:
        saved = JobSearchPreferences(user_id=owner.id, data={}); db.add(saved)
    saved.data, saved.confirmed_at = request.model_dump(mode="json"), datetime.utcnow()
    evidence = profile_evidence(db, owner.id)
    for job in db.query(JobPosting).filter_by(user_id=owner.id): assess(db, job, request, evidence)
    db.commit()
    return {"preferences": saved.data, "confirmed": True}


@router.get("/catalog")
def catalog(owner=Depends(get_workspace_owner)):
    from core.config import settings
    from jobs.employer_review import employer_reviews
    return {"engine": mode(), "company_boards": company_directory() if mode() == "legacy" else [], "source_register": source_register(), "employer_candidates": EMPLOYERS,
            "employer_reviews": employer_reviews(),
            "adzuna_configured": bool(settings.ADZUNA_APP_ID and settings.ADZUNA_APP_KEY),
            "external_only": [{"name": name, "url": url} for name, url in [
                ("LinkedIn", "https://www.linkedin.com/jobs/"), ("Naukri", "https://www.naukri.com/"),
                ("Unstop", "https://unstop.com/jobs"), ("Wellfound", "https://wellfound.com/jobs"),
                ("Internshala", "https://internshala.com/")]]}


@router.get("/sources")
def sources(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    return [source_json(source, db) for source in db.query(JobSource).filter_by(user_id=owner.id).order_by(JobSource.company)]


@router.get("/connections")
def connections(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    return {"platforms": requirements(db, owner), "feeds": [source_json(s, db) for s in
        db.query(JobSource).filter_by(user_id=owner.id, provider="structured_feed")]}


@router.get("/oss")
def oss_catalog(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    from jobs.oss.coordinator import catalog as available, ledger
    from jobs.oss.runtime import runtime_status
    connections = {s.board: source_json(s, db) for s in db.query(JobSource).filter_by(user_id=owner.id, provider="oss")}
    rows = available()
    from jobs.oss.coordinator import specification
    for source in db.query(JobSource).filter_by(user_id=owner.id, provider="oss"):
        if source.board.startswith("ats-user-"):
            state = state_for(db, source)
            item = specification(source.board, (state.summary if state else {}).get("configuration"))
            rows.append({**item, "scope": "User-supplied employer board", "verification": "not_live_verified"})
    archived = [source_json(s, db) for s in db.query(JobSource).filter(JobSource.user_id == owner.id, JobSource.provider.notin_(["oss", "manual"]))]
    return {"engine": mode(), "sources": [{**row, "connection": connections.get(row["key"])} for row in rows],
            "coverage": ledger(), "runtime": runtime_status(), "archived": archived}


class OSSConnection(BaseModel):
    key: str = Field(min_length=1, max_length=80)


@router.post("/oss/connections")
def connect_oss(request: OSSConnection, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    if mode() != "oss": raise HTTPException(409, "Open-source engine is inactive.")
    from jobs.oss.coordinator import specification
    try: item = specification(request.key)
    except ValueError as exc: raise HTTPException(422, str(exc)) from None
    if not item["connectable"]: raise HTTPException(409, item["limitation"])
    if db.get_bind().dialect.name == "postgresql": db.execute(text("SELECT pg_advisory_xact_lock(30103003)"))
    source = db.query(JobSource).filter_by(user_id=owner.id, provider="oss", board=item["key"]).first()
    if not source:
        source = JobSource(user_id=owner.id, provider="oss", board=item["key"], company=item["name"], enabled=True)
        db.add(source); db.flush()
        save_state(db, source, {"health": "never_checked", "configuration": {"engine": "oss", "tool": item["tool"], "url": item["url"]}})
        db.commit()
    return source_json(source, db)


class OSSEmployer(BaseModel):
    company: str = Field(min_length=1, max_length=150)
    url: str = Field(min_length=8, max_length=2000)


@router.post("/oss/employer")
def connect_oss_employer(request: OSSEmployer, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    if mode() != "oss": raise HTTPException(409, "Open-source engine is inactive.")
    from jobs.oss.coordinator import specification
    key = "ats-user-" + hashlib.sha256(request.url.strip().encode()).hexdigest()[:32]
    configuration = {"url": request.url.strip(), "company": request.company.strip(), "tool": "ats_scrapers", "engine": "oss"}
    try: specification(key, configuration)
    except (ValueError, TypeError): raise HTTPException(422, "Use an exact public employer board on a supported ATS host; no login or credential URLs.") from None
    if not configuration["company"]: raise HTTPException(422, "Supply an employer name.")
    if db.get_bind().dialect.name == "postgresql": db.execute(text("SELECT pg_advisory_xact_lock(30103003)"))
    source = db.query(JobSource).filter_by(user_id=owner.id, provider="oss", board=key).first()
    if not source:
        source = JobSource(user_id=owner.id, provider="oss", board=key, company=configuration["company"], enabled=True)
        db.add(source); db.flush()
        save_state(db, source, {"configuration": configuration, "health": "never_checked"})
        db.commit()
    return source_json(source, db)


@router.post("/connections/free")
def connect_free(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    require_legacy()
    return connect_free_defaults(db, owner)


@router.post("/sources/feed")
def add_feed(request: FeedInput, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    require_legacy()
    board = hashlib.sha256(request.feed_url.encode()).hexdigest()
    source = db.query(JobSource).filter_by(user_id=owner.id, provider="structured_feed", board=board).first()
    if source: return source_json(source, db)
    source = JobSource(user_id=owner.id, provider="structured_feed", board=board, company=request.company, enabled=request.enabled)
    db.add(source); db.flush()
    save_state(db, source, {"configuration": request.model_dump(exclude={"company", "enabled"}), "health": "never_checked"})
    db.commit()
    return source_json(source, db)


@router.post("/sources")
def add_source(request: SourceInput, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    require_legacy()
    if request.provider == "adzuna":
        raise HTTPException(422, "Adzuna is excluded from free discovery. Historical listings and configured credentials are retained.")
    provider = request.provider
    try:
        if provider == "auto": provider, board = detect_board(request.board)
        else:
            from jobs.adapters import normalize
            board = normalize(provider, request.board)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    if request.provider in {"remotive", "jobicy", "himalayas"}: board = "public"
    if request.provider == "adzuna" and not (len(board) == 2 and board.isalpha()):
        raise HTTPException(422, "Adzuna board must be a two-letter country code, such as in.")
    source = db.query(JobSource).filter_by(user_id=owner.id, provider=provider, board=board).first()
    if source: return source_json(source)
    source = JobSource(user_id=owner.id, provider=provider, board=board, company=request.company.strip(), enabled=request.enabled)
    db.add(source); db.commit()
    return source_json(source)


@router.post("/sources/employer")
def add_employer(request: EmployerConnectionInput, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    require_legacy()
    from jobs.enterprise import configuration
    config = configuration(request.provider, request.url, request.full_descriptions)
    board = hashlib.sha256((config.get("site_url") or config["feed_url"]).encode()).hexdigest()
    source = db.query(JobSource).filter_by(user_id=owner.id, provider=request.provider, board=board).first()
    if source: return source_json(source, db)
    source = JobSource(user_id=owner.id, provider=request.provider, board=board, company=request.company.strip(), enabled=request.enabled)
    db.add(source); db.flush()
    save_state(db, source, {"configuration": config, "health": "never_checked"})
    db.commit()
    return source_json(source, db)


@router.post("/imports/preview")
def preview_export(request: ExportPreviewInput, owner=Depends(get_workspace_owner)):
    from jobs.reviewed_exports import preview
    try: return preview(request.content, request.format)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.post("/imports/commit")
def import_export(request: ExportImportInput, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    from jobs.reviewed_exports import selected
    if not request.confirmed: raise HTTPException(422, "Explicit confirmation is required for reviewed import.")
    try: records = selected(request.content, request.format, request.rows, request.full_descriptions)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    grouped = {}
    for site, job in records: grouped.setdefault(site, []).append(job)
    prefs, _ = preferences_for(db, owner.id)
    evidence = profile_evidence(db, owner.id)
    counts = []
    for site, jobs in grouped.items():
        source = db.query(JobSource).filter_by(user_id=owner.id, provider="manual", board="reviewed:" + site).first()
        if not source:
            source = JobSource(user_id=owner.id, provider="manual", board="reviewed:" + site, company=site + " reviewed export", enabled=False)
            db.add(source); db.flush()
        counts.append({"site": site, **ingest(db, source, Snapshot(jobs, False, scope="rolling_feed"), prefs, evidence)})
    db.commit()
    return {"sources": counts, "imported": len(records), "note": "Selected records imported; discovery and automation settings preserved."}


class SourceState(BaseModel):
    enabled: bool


@router.patch("/sources/{identifier}")
def source_state(identifier: str, request: SourceState, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    source = db.query(JobSource).filter_by(id=identifier, user_id=owner.id).first()
    if not source: raise HTTPException(404, "Source not found.")
    if not active(source): raise HTTPException(409, "This collector is archived in the current engine mode.")
    source.enabled = request.enabled
    if request.enabled:
        previous = state_for(db, source)
        if previous:
            if previous.summary.get("health") in {"login_required", "permission_required", "blocked", "runtime_missing", "unsupported"}:
                save_state(db, source, {**previous.summary, "health": "never_checked"})
    db.commit()
    return source_json(source)


@router.post("/refresh")
def refresh(db: Session = Depends(get_db), owner=Depends(get_workspace_owner), automatic: bool = False, task_id: str | None = None):
    search_control = control(db, owner.id)
    if search_control.get("paused"):
        raise HTTPException(409, "Discovery is paused. Click Search jobs when you are ready.")
    prefs, confirmed = preferences_for(db, owner.id)
    if not confirmed: raise HTTPException(409, "Save your job preferences before refreshing sources.")
    enabled = sources_for(db, owner.id)
    if search_control.get("source_ids"):
        enabled = [s for s in enabled if s.id in search_control["source_ids"]]
    if not enabled: raise HTTPException(409, "Add and enable at least one job source.")
    if not any(source.provider != "adzuna" for source in enabled):
        raise HTTPException(409, "Enable a free company board or public feed. Adzuna is excluded from free discovery.")
    # Serialize only the run claim, not network requests. A second refresh sees the
    # persisted running claim. Stale claims from a crashed process can be retried.
    if db.get_bind().dialect.name == "postgresql": db.execute(text("SELECT pg_advisory_xact_lock(30103002)"))
    old = db.query(JobRefreshRun).filter_by(user_id=owner.id, status="running").all()
    for pending in old:
        heartbeat = datetime.fromisoformat(pending.summary["heartbeat_at"]) if pending.summary.get("heartbeat_at") else pending.started_at
        if heartbeat > datetime.utcnow() - timedelta(minutes=10):
            raise HTTPException(409, "A job refresh is already running.")
        pending.status, pending.finished_at = "failed", datetime.utcnow()
        pending.summary = {"error": "Previous refresh was interrupted. Retried by a new run."}
    run = JobRefreshRun(user_id=owner.id, status="running", summary={})
    db.add(run)
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "A job refresh is already running.") from None
    results, failures = [], []
    evidence = profile_evidence(db, owner.id)
    data = prefs.model_dump(mode="json")
    from jobs.oss.cancellation import token
    data["_cancel_tokens"] = ([token(owner.id, "generation", search_control["generation"])] if search_control.get("generation") else []) + ([token(owner.id, "task", task_id)] if task_id else [])
    # At most three distinct providers per execution, oldest checked first.
    # Pending sources stay due for the next worker/manual execution. Checkpoints
    # advance only in the same commit as successful ingestion.
    selected, skipped, providers = [], [], set()
    requested_engine = mode()
    for source in sorted(enabled, key=lambda s: s.last_checked_at or datetime.min):
        state = source_status(db, source)
        if source.provider == "oss" and search_control.get("generation") and state.get("scan_generation") == search_control["generation"] and not state.get("cursor"):
            skipped.append({"source_id": source.id, "company": source.company, "ready": False, "reason": "Scan completed for this search"})
            continue
        domain_key = source.board if source.provider == "oss" else source.provider
        if not due(source, state) or domain_key in providers or len(selected) >= 3:
            skipped.append({"source_id": source.id, "company": source.company,
                            "ready": due(source, state),
                            "reason": "Excluded paid source" if source.provider == "adzuna" else "Polling/backoff; retained for later" if not due(source, state) else "Execution/provider budget; retained for later"})
            continue
        cursor = state.get("cursor")
        if source.provider == "jobicy" and state.get("cursor_started_at") and datetime.fromisoformat(state["cursor_started_at"]) < datetime.utcnow() - timedelta(hours=20):
            cursor = None
        checks = candidates(db, source, 5 if source.provider == "himalayas" else 100) if source.provider in {"jobicy", "himalayas"} else []
        selected.append((source.id, source.provider, source.board, source.company, cursor, datetime.utcnow(), checks, state.get("configuration") or {}))
        providers.add(domain_key)
    # Finish all read transactions before slow network work.
    db.commit()
    # Workers only fetch plain data; all database writes stay in this thread.
    def fetch_and_verify(provider, board, company, cursor, checks, configuration):
        snapshot = fetch_source(provider, board, company, {**data, "_cursor": cursor, "_configuration": configuration})
        # Verify only older occurrences absent from this page. A failed status
        # call leaves the scan/checkpoint unchanged and enters provider backoff.
        current = {str(job.native_id) for job in snapshot.jobs}
        return snapshot, fetch_statuses(provider, [item for item in checks if item[0] not in current])
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = {pool.submit(fetch_and_verify, provider, board, company, cursor, checks, configuration): (identifier, cursor, started)
                   for identifier, provider, board, company, cursor, started, checks, configuration in selected}
        for future in as_completed(pending):
            identifier, requested_cursor, started = pending[future]
            source = db.get(JobSource, identifier)
            try:
                snapshot, statuses = future.result()
                if mode() != requested_engine: raise SourceError("Search engine changed during collection; result discarded.")
                current_control = control(db, owner.id, fresh=True)
                if current_control.get("paused") or current_control.get("generation") != search_control.get("generation"):
                    skipped.append({"source_id": identifier, "company": source.company, "reason": "Search was cleared or replaced during the scan"})
                    db.rollback(); continue
                current_prefs, _ = preferences_for(db, owner.id)
                if current_prefs.model_dump(mode="json") != {key: value for key, value in data.items() if not key.startswith("_")}:
                    skipped.append({"source_id": identifier, "company": source.company, "ready": True, "reason": "Preferences changed during collection; result discarded"})
                    db.rollback(); continue
                db.refresh(source)
                if not source.enabled:
                    skipped.append({"source_id": identifier, "company": source.company, "reason": "Source disabled during scan"})
                    db.rollback(); continue
                if automatic:
                    from automation.service import settings_for
                    if not settings_for(db, owner.id)[1].enabled:
                        skipped.append({"source_id": identifier, "company": source.company, "reason": "Automation paused during scan"})
                        db.rollback(); continue
                previous = state_for(db, source)
                prior = previous.summary if previous else {}
                expired_cursor = source.provider == "jobicy" and prior.get("cursor_started_at") and datetime.fromisoformat(prior["cursor_started_at"]) < datetime.utcnow() - timedelta(hours=20)
                continuing = prior.get("cursor") and not expired_cursor
                cursor_history = prior.get("cursor_history", []) if continuing else []
                if snapshot.cursor:
                    token = hashlib.sha256(snapshot.cursor.encode()).hexdigest()
                    if token in cursor_history:
                        snapshot.cursor = None
                        snapshot.complete = False
                        snapshot.traversal_valid = False
                        snapshot.warnings.append("Cursor cycle detected; source requires review.")
                    else: cursor_history = (cursor_history + [token])[-100:]
                traversal_start = prior.get("traversal_started_at") if requested_cursor else started.isoformat()
                traversal_valid = snapshot.traversal_valid and (not requested_cursor or prior.get("traversal_valid", False))
                if requested_cursor and snapshot.board_version != prior.get("board_version"):
                    traversal_valid = False
                    snapshot.warnings.append("Board changed during traversal; missing jobs retained until a stable complete scan.")
                if requested_cursor and traversal_start and snapshot.jobs and snapshot.scope != "rolling_feed":
                    repeated = db.query(JobSourceOccurrence.id).filter(
                        JobSourceOccurrence.source_id == source.id,
                        JobSourceOccurrence.last_seen_at >= datetime.fromisoformat(traversal_start),
                        JobSourceOccurrence.native_id.in_([str(job.native_id)[:300] for job in snapshot.jobs])).first()
                    if repeated:
                        traversal_valid = False
                        snapshot.warnings.append("Repeated jobs across continuation pages; missing jobs retained.")
                closure_since = (datetime.fromisoformat(traversal_start) if traversal_start and traversal_valid
                    and snapshot.traversal_end and not snapshot.cursor and snapshot.scope != "rolling_feed" else None)
                counts = ingest(db, source, snapshot, prefs, evidence, closure_since=closure_since)
                counts["status_checks"] = apply_statuses(db, source, statuses, prefs, evidence)
                next_time = next_check(source.provider, continuation=bool(snapshot.cursor))
                # Continuations are still throttled; Jobicy cursors expire after a day.
                save_state(db, source, {**snapshot.metadata(), "cursor": snapshot.cursor,
                    "scan_generation": search_control.get("generation"),
                    "cursor_started_at": prior.get("cursor_started_at") if continuing and snapshot.cursor else datetime.utcnow().isoformat(),
                    "health": "healthy" if counts["complete_snapshot"] else "partial", "retry_at": next_time,
                    "cursor_history": cursor_history,
                    "traversal_started_at": traversal_start if snapshot.cursor else None,
                    "traversal_valid": traversal_valid, "board_version": snapshot.board_version,
                    "last_scan": counts})
                run.summary = {"heartbeat_at": datetime.utcnow().isoformat(), "sources": [*results, {"source_id": identifier, "company": source.company, **counts}],
                               "errors": failures, "deferred": skipped}
                db.commit()
                results.append({"source_id": identifier, "company": source.company, **counts})
            except Exception as exc:
                db.rollback()
                if getattr(exc, "reason", None) == "cancelled":
                    skipped.append({"source_id": identifier, "reason": "Cancelled before collection completed", "ready": False})
                    continue
                source = db.get(JobSource, identifier)
                message = str(exc) if isinstance(exc, SourceError) else "Source could not be processed. Existing listings were preserved."
                source.last_checked_at, source.last_error = datetime.utcnow(), message
                delay = exc.retry_after_seconds if isinstance(exc, SourceError) else None
                status_code = exc.status_code if isinstance(exc, SourceError) else None
                health = "rate_limited" if status_code == 429 or "429" in message else "permission_required" if status_code == 403 or "403" in message else "login_required" if status_code == 401 or "401" in message else "blocked" if "redirect" in message.lower() else "changed_format" if "Unexpected" in message else "unreachable"
                health = getattr(exc, "reason", health)
                prior_row = state_for(db, source)
                prior = prior_row.summary if prior_row else {}
                failures_count = prior.get("failures", 0) + 1
                save_state(db, source, {**prior, "health": health, "failures": failures_count, "retry_at": next_check(source.provider,
                    max(delay or 0, min(86400, polling_floor(source.provider) * 2 ** min(failures_count - 1, 5))))})
                run.summary = {"heartbeat_at": datetime.utcnow().isoformat(), "sources": results, "errors": failures, "deferred": skipped}
                db.commit()
                failures.append({"source_id": identifier, "company": source.company, "message": message,
                                 "retry_after_seconds": exc.retry_after_seconds if isinstance(exc, SourceError) else None})
    run = db.get(JobRefreshRun, run.id)
    run.status = "partial" if (failures and results) or any(not s["complete_snapshot"] for s in results) or any("budget" in s["reason"] for s in skipped) else "failed" if failures else "succeeded"
    run.finished_at = datetime.utcnow()
    run.summary = {"sources": results, "errors": failures, "deferred": skipped, "new": sum(s["new"] for s in results), "listed": sum(s["listed"] for s in results)}
    db.commit()
    return {"id": run.id, "status": run.status, **run.summary}


@router.get("/refreshes")
def refreshes(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    return [{"id": run.id, "status": run.status, "started_at": run.started_at.isoformat(),
             "finished_at": run.finished_at.isoformat() if run.finished_at else None, "summary": run.summary}
            for run in db.query(JobRefreshRun).filter(JobRefreshRun.user_id == owner.id, JobRefreshRun.status.notin_(["source_state", "search_control"])).order_by(JobRefreshRun.started_at.desc()).limit(10)]


@router.post("/clear")
def clear_jobs(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    return clear_listings(db, owner)


@router.post("/pause")
def pause_search(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    from db.models import AutomationTask
    from jobs.oss.cancellation import cancel, token
    saved = control(db, owner.id)
    set_control(db, owner.id, {**saved, "paused": True})
    for task in db.query(AutomationTask).filter(AutomationTask.user_id == owner.id, AutomationTask.kind == "discover", AutomationTask.status.in_(["queued", "running"])):
        cancel(token(owner.id, "task", task.id))
        task.status, task.finished_at = "cancelled", datetime.utcnow()
    db.commit()
    return {"paused": True, "note": "Discovery stopped; saved jobs and preferences retained."}


@router.post("/search")
def start_search(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    from automation.service import queue_discovery, lock_owner
    lock_owner(db)
    prefs, confirmed = preferences_for(db, owner.id)
    if not confirmed: raise HTTPException(409, "Save your job preferences before searching.")
    chosen = sources_for(db, owner.id)
    if not chosen: raise HTTPException(409, "Connect an active source for the current discovery engine first.")
    query = hashlib.sha256(json.dumps([mode(), prefs.model_dump(mode="json"), sorted(s.id for s in chosen)], sort_keys=True).encode()).hexdigest()
    current = control(db, owner.id)
    from db.models import AutomationTask
    existing = db.query(AutomationTask).filter(AutomationTask.user_id == owner.id, AutomationTask.kind == "discover",
        AutomationTask.status.in_(["queued", "running"])).first()
    if existing and (existing.payload.get("engine", "legacy") != mode() or current.get("query") != query):
        for old in db.query(AutomationTask).filter(AutomationTask.user_id == owner.id, AutomationTask.kind == "discover", AutomationTask.status.in_(["queued", "running"])):
            old.status, old.finished_at, old.error = "cancelled", datetime.utcnow(), "Search engine or query was replaced."
        existing = None
    if existing and existing.payload.get("search_id") and not current.get("paused"):
        return {"search_id": existing.payload["search_id"], "status": existing.status}
    if existing: raise HTTPException(409, "Another discovery task is already pending. Cancel it in Automation before starting a new search.")
    identifier = str(uuid.uuid4())
    # An explicit new search starts at page one. Preserve real access/rate-limit
    # cooldowns, but do not let the previous successful search's poll floor hide it.
    if mode() == "oss":
        for source in chosen:
            row = state_for(db, source)
            if row:
                values = {**row.summary, "cursor": None, "cursor_history": [], "scan_generation": None,
                          "traversal_started_at": None, "traversal_valid": False}
                if values.get("health") in {"healthy", "partial"}: values["retry_at"] = None
                row.summary = values
    set_control(db, owner.id, {"paused": False, "generation": identifier, "search_id": identifier, "engine": mode(), "query": query, "source_ids": [s.id for s in chosen]})
    task = queue_discovery(db, owner.id)
    task.payload = {**task.payload, "search_id": identifier, "search_only": True, "source_ids": [s.id for s in chosen]}
    db.commit()
    return {"search_id": identifier, "status": task.status}


@router.get("/search/{identifier}")
def search_status(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    from db.models import AutomationTask, AutomationWorker
    tasks = db.query(AutomationTask).filter(AutomationTask.user_id == owner.id,
        AutomationTask.payload["search_id"].as_string() == identifier).all()
    if not tasks: raise HTTPException(404, "Search not found.")
    pending = [task for task in tasks if task.status in {"queued", "running"}]
    observed = {}
    deferred = {}
    source_errors = []
    for task in sorted(tasks, key=lambda item: item.created_at):
        source_errors.extend((task.result or {}).get("errors", []))
        for item in (task.result or {}).get("sources", []): observed[item["source_id"]] = item
        for item in (task.result or {}).get("deferred", []): deferred[item["source_id"]] = item
    enabled = sources_for(db, owner.id)
    saved_ids = next((task.payload.get("source_ids") for task in tasks if task.payload.get("source_ids")), None)
    if saved_ids: enabled = [s for s in enabled if s.id in saved_ids]
    unvisited = [source for source in enabled if source.id not in observed]
    unfinished = any(item.get("cursor") for item in observed.values()) or any(deferred.get(source.id, {}).get("ready") for source in unvisited)
    status = ("running" if pending else "failed" if all(task.status == "failed" for task in tasks)
              else "cancelled" if all(task.status == "cancelled" for task in tasks)
              else "incomplete" if unfinished else "partial" if unvisited or source_errors else "completed")
    if control(db, owner.id).get("paused"): status = "paused"
    worker = db.query(AutomationWorker).order_by(AutomationWorker.heartbeat_at.desc()).first()
    return {"search_id": identifier, "status": status,
            "coverage": {"checked_sources": len(set(observed) & {source.id for source in enabled}), "enabled_sources": len(enabled),
                         "remaining_sources": [source.company for source in unvisited], "more_pages": any(item.get("cursor") for item in observed.values())},
            "worker_running": bool(worker and worker.heartbeat_at > datetime.utcnow() - timedelta(seconds=35)),
            "pending": len(pending), "completed_batches": sum(task.status == "succeeded" for task in tasks),
            "next_check_at": min((task.available_at.isoformat() for task in pending), default=None),
            "errors": [task.error for task in tasks if task.error] + [error.get("message", "Source unavailable") for error in source_errors]}


@router.get("")
def feed(q: str = "", eligibility: str = "suitable", state: str = "active", source_id: str = "", limit: int = 50,
         page: int = 1, sort: str = "best", work_mode: str = "", employment_type: str = "",
         minimum_score: int = 0, salary_floor: int = 0, posted_within: int = 0, include_unverified_salary: bool = True,
         max_experience: float | None = None, include_unknown_experience: bool = True,
         db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    prefs, confirmed = preferences_for(db, owner.id)
    if max_experience is not None:
        if not 0 <= max_experience <= 10: raise HTTPException(422, "Experience must be between 0 and 10 years.")
        prefs = prefs.model_copy(update={"max_required_experience": max_experience})
    evidence = profile_evidence(db, owner.id)
    if page < 1 or limit < 1 or limit > 300 or sort not in {"best", "relevance", "newest", "salary_desc", "salary_asc", "wfh_first", "onsite_first"} or not 0 <= minimum_score <= 100 or not 0 <= salary_floor <= 100000000 or not 0 <= posted_within <= 365:
        raise HTTPException(422, "Invalid page, sort, relevance, salary or posting-age filter.")
    if work_mode not in {"", "remote", "hybrid", "onsite", "unknown"} or employment_type not in {"", "full_time", "internship", "contract", "part_time", "unknown"}:
        raise HTTPException(422, "Choose a supported work arrangement and employment type.")
    if control(db, owner.id).get("paused"):
        return {"items": [], "total": 0, "page": page, "page_size": limit, "has_next": False, "paused": True,
                "stored": db.query(JobPosting).filter(JobPosting.user_id == owner.id, JobPosting.status != "cleared").count(),
                "preferences_confirmed": confirmed, "master_active": bool(evidence[0]),
                "diagnostics": {"eligible_matches": 0, "relevance_matches": 0, "salary_unverified_matches": 0,
                                "salary_excluded": 0, "include_unverified_salary": include_unverified_salary}}
    # Assess only missing/stale cached matches after master/confirmed-skill or
    # preference changes. Ingestion already invalidates changed descriptions.
    version = evidence_version(prefs, evidence)
    stale = db.query(JobPosting, JobMatch).outerjoin(JobMatch, (JobMatch.job_id == JobPosting.id) & (JobMatch.user_id == owner.id)).filter(
        JobPosting.user_id == owner.id, JobPosting.status != "cleared", or_(JobMatch.id.is_(None), JobMatch.assessment.is_(None),
        JobMatch.assessment["evidence_version"].as_string().is_(None), JobMatch.assessment["evidence_version"].as_string() != version))
    for job, cached in stale: assess(db, job, prefs, evidence, match=cached, version=version)
    db.commit()
    query = db.query(JobPosting, JobMatch).join(JobMatch, (JobMatch.job_id == JobPosting.id) & (JobMatch.user_id == owner.id)).filter(JobPosting.user_id == owner.id, JobPosting.status != "cleared")
    if control(db, owner.id).get("paused"): query = query.filter(False)
    mode = JobMatch.assessment["work_mode"].as_string()
    annual_min = cast(JobPosting.facts["annual_salary_min_inr"].as_string(), Float)
    annual_max = cast(JobPosting.facts["annual_salary_max_inr"].as_string(), Float)
    if work_mode: query = query.filter(mode == work_mode)
    if employment_type: query = query.filter(JobMatch.assessment["employment_type"].as_string() == employment_type)
    if posted_within: query = query.filter(JobPosting.published_at >= datetime.utcnow() - timedelta(days=posted_within))
    required_years = cast(JobMatch.assessment["minimum_experience"].as_string(), Float)
    if max_experience is not None:
        experience_condition = required_years <= max_experience
        if include_unknown_experience: experience_condition = or_(experience_condition, required_years.is_(None))
        query = query.filter(experience_condition)
    elif not include_unknown_experience: query = query.filter(required_years.isnot(None))
    query = query.filter(or_(JobPosting.facts["source_expiry_at"].as_string().is_(None), JobPosting.facts["source_expiry_at"].as_string() > datetime.utcnow().isoformat()))
    status = JobMatch.assessment["eligibility"].as_string()
    if eligibility == "suitable": query = query.filter(status != "ineligible")
    elif eligibility in {"eligible", "review", "ineligible"}: query = query.filter(status == eligibility)
    if state == "active": query = query.filter(JobMatch.state != "dismissed")
    elif state in {"saved", "dismissed"}: query = query.filter(JobMatch.state == state)
    if source_id:
        from db.models import JobSourceOccurrence
        query = query.filter(db.query(JobSourceOccurrence.id).filter(JobSourceOccurrence.job_id == JobPosting.id, JobSourceOccurrence.source_id == source_id).exists())
    if q:
        # Escape LIKE wildcards; this searches retained jobs, not the internet.
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.filter(or_(*(column.ilike(pattern, escape="\\") for column in (JobPosting.title, JobPosting.company, JobPosting.location))))
    eligible_count = query.count()
    # Retain the old argument for older clients; relevance no longer hides jobs.
    relevance_count = query.count()
    unverified_count = query.filter(annual_min.is_(None)).count()
    if salary_floor:
        salary_condition = annual_min > salary_floor
        if include_unverified_salary: salary_condition = or_(salary_condition, annual_min.is_(None))
        query = query.filter(salary_condition)
    elif not include_unverified_salary: query = query.filter(annual_min.isnot(None))
    total = query.count()
    remote_rank = case((mode == "remote", 0), (mode == "hybrid", 1), (mode == "onsite", 2), else_=3)
    newest = func.coalesce(JobPosting.published_at, JobPosting.first_seen_at).desc()
    if sort in {"best", "wfh_first"}: ordering = [remote_rank, annual_max.desc().nullslast(), newest]
    elif sort == "onsite_first": ordering = [case((mode == "onsite", 0), (mode == "hybrid", 1), (mode == "remote", 2), else_=3), annual_max.desc().nullslast(), newest]
    elif sort == "salary_desc": ordering = [annual_max.desc().nullslast(), newest]
    elif sort == "salary_asc": ordering = [annual_min.asc().nullslast(), newest]
    elif sort == "newest": ordering = [func.coalesce(JobPosting.published_at, JobPosting.first_seen_at).desc()]
    else: ordering = [newest]
    rows = query.order_by(*ordering, JobPosting.id).offset((page - 1) * limit).limit(limit).all()
    items = [job_json(db, job, match) for job, match in rows]
    return {"items": items, "total": total, "page": page, "page_size": limit, "has_next": page * limit < total,
            "diagnostics": {"eligible_matches": eligible_count, "relevance_matches": relevance_count,
                            "salary_unverified_matches": unverified_count, "salary_excluded": relevance_count - total,
                            "include_unverified_salary": include_unverified_salary},
            "stored": db.query(JobPosting).filter(JobPosting.user_id == owner.id, JobPosting.status != "cleared").count(),
            "preferences_confirmed": confirmed, "master_active": bool(evidence[0])}


@router.post("/import")
def import_job(request: ManualJob, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    try: url = public_url(request.apply_url)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    source = db.query(JobSource).filter_by(user_id=owner.id, provider="manual", board="manual").first()
    if not source:
        source = JobSource(user_id=owner.id, provider="manual", board="manual", company="Added by you", enabled=False)
        db.add(source); db.flush()
    listing = Listing(str(uuid.uuid4()), request.title.strip(), request.company.strip(), request.location.strip(), url,
                      request.description.strip(), request.description_complete)
    prefs, _ = preferences_for(db, owner.id)
    ingest(db, source, Snapshot([listing], False), prefs, profile_evidence(db, owner.id))
    db.commit()
    from jobs.connectors import canonical_url
    job = db.query(JobPosting).filter_by(user_id=owner.id, apply_url=canonical_url(url)).first()
    match = db.query(JobMatch).filter_by(user_id=owner.id, job_id=job.id).first()
    return job_json(db, job, match, True)


@router.get("/{identifier}")
def detail(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    job = owned_job(db, identifier, owner)
    if (job.facts or {}).get("source_expiry_at", "9999") <= datetime.utcnow().isoformat():
        raise HTTPException(410, "This source listing has expired. Saved history is retained.")
    prefs, _ = preferences_for(db, owner.id)
    match = assess(db, job, prefs, profile_evidence(db, owner.id)); db.commit()
    return job_json(db, job, match, True)


class JobState(BaseModel):
    state: str


@router.patch("/{identifier}/state")
def job_state(identifier: str, request: JobState, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    if request.state not in {"new", "saved", "dismissed"}: raise HTTPException(422, "Choose new, saved, or dismissed.")
    job = owned_job(db, identifier, owner)
    prefs, _ = preferences_for(db, owner.id)
    match = assess(db, job, prefs, profile_evidence(db, owner.id))
    match.state = request.state; db.commit()
    return job_json(db, job, match)


@router.post("/{identifier}/tailor")
def tailor_job(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    job = owned_job(db, identifier, owner)
    if (job.facts or {}).get("source_expiry_at", "9999") <= datetime.utcnow().isoformat():
        raise HTTPException(410, "This source listing has expired.")
    if job.status != "open": raise HTTPException(409, "This opening is no longer listed. Verify it before preparing a resume.")
    if not job.description_complete: raise HTTPException(409, "This is a search excerpt. Add the full job description before tailoring.")
    master = db.query(LatexMaster).filter_by(user_id=owner.id, status="active").first()
    if not master: raise HTTPException(409, "Review and activate your master resume first.")
    prefs, _ = preferences_for(db, owner.id)
    match = assess(db, job, prefs, profile_evidence(db, owner.id))
    existing = db.get(LatexTailoringRun, match.tailoring_run_id) if match.tailoring_run_id else None
    if existing and existing.master_id == master.id and existing.job_description == job.description:
        return {"run_id": existing.id, "url": f"/tailor?run={existing.id}"}
    from api.tailor import analyze, AnalyzeRequest
    result = analyze(AnalyzeRequest(master_id=master.id, job_description=job.description,
                     label=f"{job.company} · {job.title}"[:150]), db, owner)
    match.tailoring_run_id = result["id"]; db.commit()
    return {"run_id": result["id"], "url": f"/tailor?run={result['id']}"}
