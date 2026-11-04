"""Central execution policy; retained collectors require explicit administrative opt-in."""
from core.config import settings
from jobs.connectors import SourceError


def mode():
    value = settings.JOB_DISCOVERY_ENGINE
    if value not in {"oss", "legacy"}:
        raise SourceError("Invalid job discovery engine configuration.")
    if value == "legacy" and not settings.JOB_LEGACY_ENABLED:
        raise SourceError("Legacy collection requires explicit administrative enablement.")
    return value


def active(source):
    return source.provider == "oss" if mode() == "oss" else source.provider not in {"oss", "manual", "adzuna"}


def require_legacy():
    if mode() != "legacy":
        from fastapi import HTTPException
        raise HTTPException(409, "Legacy collectors are archived. Use open-source source setup.")


def sources_for(db, owner_id):
    from db.models import JobSource
    return [s for s in db.query(JobSource).filter_by(user_id=owner_id, enabled=True) if active(s)]
