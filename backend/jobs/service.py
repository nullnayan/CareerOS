"""Persist source observations, immutable JD snapshots, and per-workspace matches."""
from datetime import datetime
from uuid import uuid4
import hashlib
import json
from sqlalchemy import or_
from db.models import (JobSearchPreferences, JobPosting, JobSourceOccurrence, JobDescriptionRevision,
                       JobMatch, LatexMaster, ConfirmedSkill, LatexTailoringRun)
from jobs.connectors import Snapshot, canonical_url, fingerprint
from jobs.matching import evaluate
from jobs.schemas import SearchPreferences
from tailoring.latex import plain_text
from jobs.salary import salary_facts


def preferences_for(db, user_id) -> tuple[SearchPreferences, bool]:
    saved = db.get(JobSearchPreferences, user_id)
    return (SearchPreferences(**saved.data), True) if saved else (SearchPreferences(), False)


def profile_evidence(db, user_id) -> tuple[str, list[str]]:
    master = db.query(LatexMaster).filter_by(user_id=user_id, status="active").first()
    skills = [row.name for row in db.query(ConfirmedSkill).filter_by(user_id=user_id)]
    return plain_text(master.source) if master else "", skills


_MATCH_NOT_LOADED = object()


def assess(db, job, preferences, evidence, match=_MATCH_NOT_LOADED, version=None):
    job.facts = salary_facts(job.description, job.facts)
    if match is _MATCH_NOT_LOADED:
        match = db.query(JobMatch).filter_by(user_id=job.user_id, job_id=job.id).first()
    if not match:
        match = JobMatch(user_id=job.user_id, job_id=job.id, title=job.title, source_url=job.apply_url, state="new")
        db.add(match)
    result = evaluate(job, preferences, evidence[0], evidence[1])
    result["evidence_version"] = version or evidence_version(preferences, evidence)
    match.title, match.company, match.location = job.title, job.company, job.location
    match.source_url, match.match_score = job.apply_url, result["relevance_score"]
    match.matched_skills, match.assessment = result["matched_skills"], result
    match.fetched_at = datetime.utcnow()
    return match


def evidence_version(preferences, evidence):
    return hashlib.sha256(json.dumps(["search-v5-source-experience", datetime.utcnow().date().isoformat(), preferences.model_dump(mode="json"), evidence], sort_keys=True).encode()).hexdigest()


def ingest(db, source, snapshot: Snapshot, preferences, evidence, closure_since=None) -> dict:
    now = datetime.utcnow()
    seen = set()
    created = updated = 0
    # Preload only this execution's identities, in bounded SQL parameter batches.
    # Maps also include pending objects because production disables autoflush.
    prepared = []
    for listing in snapshot.jobs:
        native = str(listing.native_id)[:300]
        if native in seen: continue
        seen.add(native)
        prepared.append((listing, native, canonical_url(listing.apply_url), fingerprint(listing)))
    seen.clear()
    def chunks(values):
        values = list(dict.fromkeys(values))
        for start in range(0, len(values), 300): yield values[start:start + 300]
    occurrences = {}
    for batch in chunks(row[1] for row in prepared):
        occurrences.update({row.native_id: row for row in db.query(JobSourceOccurrence).filter(
            JobSourceOccurrence.source_id == source.id, JobSourceOccurrence.native_id.in_(batch))})
    jobs = {}
    for column, values in ((JobPosting.id, [row.job_id for row in occurrences.values()]),
                           (JobPosting.apply_url, [row[2] for row in prepared]),
                           (JobPosting.identity_key, [row[3] for row in prepared])):
        for batch in chunks(values):
            jobs.update({row.id: row for row in db.query(JobPosting).filter(JobPosting.user_id == source.user_id, column.in_(batch))})
    by_url, by_identity = {}, {}
    for job in jobs.values():
        by_url.setdefault(job.apply_url, job); by_identity.setdefault(job.identity_key, job)
    revisions, matches = set(), {}
    for batch in chunks(jobs):
        revisions.update(db.query(JobDescriptionRevision.job_id, JobDescriptionRevision.content_hash).filter(JobDescriptionRevision.job_id.in_(batch)).all())
        matches.update({row.job_id: row for row in db.query(JobMatch).filter(JobMatch.user_id == source.user_id, JobMatch.job_id.in_(batch))})
    changed = {}
    version = evidence_version(preferences, evidence)
    for listing, native_id, url, identity in prepared:
        listing.facts = salary_facts(listing.description, listing.facts)
        seen.add(native_id)
        occurrence = occurrences.get(native_id)
        job = jobs.get(occurrence.job_id) if occurrence else None
        if not job:
            job = by_url.get(url) or by_identity.get(identity)
        content_hash = hashlib.sha256(listing.description.encode()).hexdigest()
        if not job:
            job = JobPosting(id=str(uuid4()), user_id=source.user_id, identity_key=identity, title=listing.title, company=listing.company,
                location=listing.location, apply_url=url, description=listing.description, description_hash=content_hash,
                description_complete=listing.complete, facts=listing.facts, published_at=listing.published_at,
                first_seen_at=now, last_seen_at=now, status="open")
            db.add(job); created += 1
            jobs[job.id] = job; by_url.setdefault(url, job); by_identity.setdefault(identity, job)
        else:
            updated += 1
            # An aggregator excerpt must not replace an employer's full description.
            if listing.complete or not job.description_complete:
                job.title, job.company, job.location = listing.title, listing.company, listing.location
                job.description, job.description_hash = listing.description, content_hash
                job.description_complete, job.facts = listing.complete, listing.facts
                if listing.published_at: job.published_at = listing.published_at
                elif listing.facts.get("publication_date_unknown"): job.published_at = None
            job.last_seen_at, job.status = now, "open"
        if (job.id, content_hash) not in revisions:
            db.add(JobDescriptionRevision(job_id=job.id, content_hash=content_hash, description=listing.description, complete=listing.complete))
            revisions.add((job.id, content_hash))
        if not occurrence:
            occurrence = JobSourceOccurrence(source_id=source.id, native_id=native_id, job_id=job.id, source_url=listing.apply_url)
            db.add(occurrence)
            occurrences[native_id] = occurrence
        occurrence.active, occurrence.last_seen_at = True, now
        changed[job.id] = job
    # These models link by IDs without ORM relationships; persist parent rows
    # before the dependent revisions/occurrences/matches under real FK checks.
    if changed: db.flush(list(changed.values()))
    for job in changed.values():
        matches[job.id] = assess(db, job, preferences, evidence, match=matches.get(job.id), version=version)
    db.flush()
    closed = 0
    if (snapshot.complete and snapshot.scope == "company_board") or closure_since is not None:
        missing = {}
        for occurrence in db.query(JobSourceOccurrence).filter_by(source_id=source.id, active=True).all():
            if (occurrence.last_seen_at < closure_since if closure_since is not None else occurrence.native_id not in seen):
                occurrence.active = False
                missing[occurrence.job_id] = True
        db.flush()
        active = set()
        for batch in chunks(missing):
            active.update(row[0] for row in db.query(JobSourceOccurrence.job_id).filter(
                JobSourceOccurrence.job_id.in_(batch), JobSourceOccurrence.active.is_(True)).distinct())
        for batch in chunks(set(missing) - active):
            closing = db.query(JobPosting, JobMatch).outerjoin(JobMatch, (JobMatch.job_id == JobPosting.id) & (JobMatch.user_id == source.user_id)).filter(
                JobPosting.user_id == source.user_id, JobPosting.id.in_(batch)).all()
            for job, match in closing:
                job.status = "closed"
                assess(db, job, preferences, evidence, match=match, version=version)
                closed += 1
    source.last_checked_at, source.last_success_at = now, now
    source.last_error, source.last_count = None, len(seen)
    return {"new": created, "updated": updated, "closed": closed, "listed": len(seen),
            **snapshot.metadata(), "complete_snapshot": snapshot.complete or closure_since is not None,
            "can_close_missing": snapshot.metadata()["can_close_missing"] or closure_since is not None,
            "closure_reconciled": closure_since is not None}


def job_json(db, job, match, detail=False):
    sources = db.query(JobSourceOccurrence).filter_by(job_id=job.id).all()
    run = db.get(LatexTailoringRun, match.tailoring_run_id) if match and match.tailoring_run_id else None
    if run and run.job_description != job.description: run = None
    result = {"id": job.id, "title": job.title, "company": job.company, "location": job.location,
              "apply_url": (job.facts or {}).get("preserve_apply_url", job.apply_url), "description_complete": job.description_complete,
              "status": job.status, "state": (match.state or "new") if match else "new",
              "assessment": {key: value for key, value in (match.assessment or {}).items() if key not in {"relevance_score", "note"}} if match else None, "facts": job.facts,
              "first_seen_at": job.first_seen_at.isoformat(), "last_seen_at": job.last_seen_at.isoformat(),
              "published_at": job.published_at.isoformat() if job.published_at else None,
              "source_ids": list(dict.fromkeys(source.source_id for source in sources)),
              "tailoring_run_id": run.id if run else None, "resume_status": run.status if run else None}
    if detail:
        result.update(description=job.description, sources=[{"source_id": s.source_id, "url": s.source_url,
            "active": s.active, "last_seen_at": s.last_seen_at.isoformat()} for s in sources])
    return result
