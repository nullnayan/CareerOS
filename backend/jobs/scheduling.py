"""Durable source checkpoints using existing refresh metadata, no data migration.

source_state rows are control records, excluded from user-visible run history.
The refresh coordinator serializes writes under its existing workspace claim.
"""
from datetime import datetime, timedelta
from db.models import JobRefreshRun
from jobs.registry import capability


def polling_floor(provider):
    entry = capability(provider)
    return (entry or {}).get("polling_floor_seconds") or 3600


def state_for(db, source):
    return db.query(JobRefreshRun).filter(JobRefreshRun.user_id == source.user_id,
        JobRefreshRun.status == "source_state", JobRefreshRun.summary["source_id"].as_string() == source.id).first()


def save_state(db, source, values):
    row = state_for(db, source)
    if not row:
        row = JobRefreshRun(user_id=source.user_id, status="source_state", summary={})
        db.add(row)
    configuration = row.summary.get("configuration")
    row.summary = {"source_id": source.id, **({"configuration": configuration} if configuration else {}), **values}
    row.finished_at = datetime.utcnow()
    return row


def source_status(db, source):
    row = state_for(db, source)
    values = dict(row.summary) if row else {}
    values.setdefault("health", "unreachable" if source.last_error else "healthy" if source.last_success_at else "never_checked")
    if source.provider == "adzuna": values["health"] = "excluded_paid"
    values["capability"] = capability(source.provider)
    return values


def due(source, values):
    from jobs.engine import active
    if not active(source): return False
    if source.provider == "adzuna": return False
    if values.get("health") in {"login_required", "permission_required", "blocked", "unsupported", "runtime_missing"}: return False
    value = values.get("retry_at")
    if value and datetime.fromisoformat(value) > datetime.utcnow(): return False
    return True


def next_check(provider, delay=None, continuation=False):
    # Walking a different page is not re-polling the same board/feed. Still pace
    # continuations rather than issuing an unbounded burst.
    floor = (10 if provider == "oss" else 60) if continuation else polling_floor(provider)
    return (datetime.utcnow() + timedelta(seconds=max(floor, delay or 0))).isoformat()
