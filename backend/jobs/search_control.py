"""Explicit search sessions, persistent pause, and clearing the visible catalogue."""
import uuid
from datetime import datetime
from sqlalchemy import text
from db.models import (JobRefreshRun, JobPosting, JobMatch, JobSourceOccurrence, JobDescriptionRevision,
                       JobApplication, AutomationTask, AutomationSettings, JobSource)


def control(db, owner_id, fresh=False):
    query = db.query(JobRefreshRun).filter_by(user_id=owner_id, status="search_control")
    if fresh: query = query.populate_existing()
    row = query.first()
    return dict(row.summary) if row else {}


def set_control(db, owner_id, values):
    row = db.query(JobRefreshRun).filter_by(user_id=owner_id, status="search_control").first()
    if not row:
        row = JobRefreshRun(user_id=owner_id, status="search_control", summary={}); db.add(row)
    old = dict(row.summary or {})
    if old.get("generation") and (values.get("paused") or values.get("generation") != old.get("generation")):
        from jobs.oss.cancellation import cancel, token
        cancel(token(owner_id, "generation", old["generation"]))
    row.summary = values
    row.finished_at = datetime.utcnow()


def clear_listings(db, owner):
    if db.get_bind().dialect.name == "postgresql": db.execute(text("SELECT pg_advisory_xact_lock(30103002)"))
    now = datetime.utcnow()
    # Retain postings referenced by application history; remove them from results.
    jobs = db.query(JobPosting).filter_by(user_id=owner.id).all()
    identifiers = [job.id for job in jobs]
    tracked = {row.job_id for row in db.query(JobApplication).filter_by(user_id=owner.id)}
    removable = [identifier for identifier in identifiers if identifier not in tracked]
    db.query(JobMatch).filter_by(user_id=owner.id).delete(synchronize_session=False)
    if identifiers:
        db.query(JobSourceOccurrence).filter(JobSourceOccurrence.job_id.in_(identifiers)).update({"active": False}, synchronize_session=False)
    if removable:
        db.query(JobSourceOccurrence).filter(JobSourceOccurrence.job_id.in_(removable)).delete(synchronize_session=False)
        db.query(JobDescriptionRevision).filter(JobDescriptionRevision.job_id.in_(removable)).delete(synchronize_session=False)
        db.query(JobPosting).filter(JobPosting.id.in_(removable)).delete(synchronize_session=False)
    for job in jobs:
        if job.id in tracked: job.status = "cleared"
    for task in db.query(AutomationTask).filter(AutomationTask.user_id == owner.id, AutomationTask.status.in_(["queued", "running"])):
        if task.kind in {"discover", "prepare"}:
            task.status, task.finished_at, task.error = "cancelled", now, "Job listings were cleared; start a new search when ready."
    schedule = db.get(AutomationSettings, owner.id)
    if schedule:
        schedule.data = {**schedule.data, "enabled": False}; schedule.next_run_at = None
    # New searches must begin fresh scans, while provider-mandated deadlines stay.
    for source in db.query(JobSource).filter_by(user_id=owner.id):
        source.last_count = 0
    for state in db.query(JobRefreshRun).filter_by(user_id=owner.id, status="source_state"):
        state.summary = {**state.summary, "cursor": None, "cursor_history": [], "traversal_started_at": None,
                         "traversal_valid": False, "last_scan": None}
    set_control(db, owner.id, {"paused": True, "generation": str(uuid.uuid4()), "cleared_at": now.isoformat()})
    db.commit()
    return {"cleared": len(jobs), "deleted": len(removable), "retained_for_applications": len(tracked), "paused": True}
