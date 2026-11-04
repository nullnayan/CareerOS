"""Bounded public-feed status checks. Absence/404 is never confirmed closure.

https://jobicy.com/jobs-rss-feed (batch status, 100 IDs)
https://himalayas.app/api (single-job status, 410 means closed)
"""
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from db.models import JobPosting, JobSourceOccurrence
from jobs.connectors import SourceError, request_json
from jobs.service import assess


def candidates(db, source, limit=100):
    # Use the existing occurrence timestamp as a rotating queue; no new schema.
    cutoff = datetime.utcnow() - timedelta(hours=24 if source.provider == "himalayas" else 1)
    rows = db.query(JobSourceOccurrence).filter_by(source_id=source.id, active=True).filter(
        JobSourceOccurrence.last_seen_at < cutoff).order_by(JobSourceOccurrence.last_seen_at, JobSourceOccurrence.id).limit(limit)
    return [(r.native_id, r.source_url) for r in rows]


def fetch_statuses(provider, items):
    from jobs.engine import mode
    if mode() == "oss": return {}
    if not items: return {}
    if provider == "jobicy":
        ids = [native for native, _ in items[:100] if re.fullmatch(r"[1-9][0-9]*", native)]
        if not ids: return {}
        data = request_json("https://jobicy.com/api/jobs/status", {"ids": ",".join(ids)})
        if not isinstance(data, dict) or data.get("success") is False or not isinstance(data.get("jobs"), list):
            raise SourceError("Unexpected Jobicy status response.")
        results = {}
        for item in data["jobs"]:
            if not isinstance(item, dict): continue
            native, status = str(item.get("id")), item.get("status")
            if native in ids and status in {"active", "closed", "unknown"}:
                if native in results: raise SourceError("Repeated identity in Jobicy status response.")
                results[native] = status
        if set(results) != set(ids): raise SourceError("Unexpected Jobicy status response; requested identities are missing.")
        return results
    if provider == "himalayas":
        results = {}
        for native, _ in items[:5]:
            parsed = urlsplit(native)
            if parsed.scheme != "https" or parsed.netloc != "himalayas.app" or not re.fullmatch(r"/companies/[a-zA-Z0-9_-]+/jobs/[a-zA-Z0-9_-]+", parsed.path):
                continue
            try:
                data = request_json("https://himalayas.app/jobs/api" + parsed.path)
                if not isinstance(data, dict) or not isinstance(data.get("job"), dict):
                    raise SourceError("Unexpected Himalayas status response.")
                if data["job"].get("guid") != native:
                    raise SourceError("Himalayas status identity does not match the requested job.")
                results[native] = "active"
            except SourceError as exc:
                if exc.status_code == 410: results[native] = "closed"
                elif exc.status_code == 404: results[native] = "unknown"
                else: raise
        return results
    return {}


def apply_statuses(db, source, statuses, preferences, evidence):
    now, closed = datetime.utcnow(), 0
    for native, status in statuses.items():
        occurrence = db.query(JobSourceOccurrence).filter_by(source_id=source.id, native_id=native).first()
        if not occurrence: continue
        job = db.get(JobPosting, occurrence.job_id)
        occurrence.last_seen_at = now
        # Unknown preserves the occurrence and job; the UI shows the uncertainty.
        facts = dict(job.facts or {})
        checks = dict(facts.get("source_status_checks", {}))
        checks[source.id] = {"status": status, "checked_at": now.isoformat()}
        job.facts = {**facts, "source_status_checks": checks}
        if status == "closed":
            occurrence.active = False
            db.flush()
            if not db.query(JobSourceOccurrence).filter_by(job_id=job.id, active=True).count():
                job.status = "closed"
                closed += 1
        elif status == "active":
            occurrence.active = True
            job.status = "open"
        assess(db, job, preferences, evidence)
    return {"checked": len(statuses), "closed": closed, "unknown": sum(s == "unknown" for s in statuses.values())}
