"""Search breadth and honest experience filters on disposable data only."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from core.config import settings
from db.models import User, JobPosting, JobRefreshRun, AutomationTask
from jobs.matching import evaluate, source_experience
from jobs.oss.normalize import normalize_job
from jobs.oss.coordinator import fetch
from jobs.schemas import SearchPreferences
from jobs.service import ingest
from jobs.scheduling import state_for
from tests.test_job_discovery import isolated, posting
from tests.test_oss_integration import batch


@pytest.fixture(autouse=True)
def oss_mode(monkeypatch):
    monkeypatch.setattr(settings, "JOB_DISCOVERY_ENGINE", "oss")
    monkeypatch.setattr(settings, "JOB_LEGACY_ENABLED", False)


@pytest.mark.parametrize("raw,expected", [("0-2 Yrs", 0), ("3-5 years", 3), ("10+ years", 10), ("Fresher", 0), ("Not disclosed", None)])
def test_source_range_is_not_lost_or_assumed_zero(raw, expected):
    job = normalize_job({"id": "one", "title": "Software Engineer", "company": "Example", "job_url": "https://www.naukri.com/job/one", "experience_range": raw}, source_id="naukri", tool="jobspy")
    assert job.facts["experience_range"] == raw
    assert source_experience(job.facts) == expected


def test_naukri_range_blocks_experienced_listing_for_freshers_even_without_description_years():
    job = posting(title="Software Engineer", description="Build Python services.", facts={"experience_range": "3-5 Yrs"})
    result = evaluate(job, SearchPreferences(), "Python", [])
    assert result["minimum_experience"] == 3
    assert result["eligibility"] == "ineligible"
    assert evaluate(job, SearchPreferences(max_required_experience=5), "Python", [])["eligibility"] != "ineligible"


def test_jobspy_uses_full_page_and_selected_source_age():
    with patch("jobs.oss.jobspy_adapter.collect", return_value=batch()) as collector:
        fetch("naukri", {"max_posting_age_days": 3})
    request = collector.call_args.args[0]
    assert request.max_results == request.max_details == 20
    assert request.max_age_days == 3
    assert request.deadline_seconds >= 85


def seed(client, factory):
    assert client.put("/jobs/preferences", json={"max_required_experience": 0, "max_posting_age_days": None}).status_code == 200
    source = client.post("/jobs/oss/connections", json={"key": "naukri"}).json()
    client.post("/jobs/search")
    from jobs.connectors import Listing, Snapshot
    with factory() as db:
        from db.models import JobSource
        owner = db.query(User).one()
        rows = []
        for name, years, days in [("fresh", "0-2 Yrs", 0), ("experienced", "3-5 Yrs", 2), ("ten", "10-12 Yrs", 6), ("unknown", None, 0), ("old", "0 Yrs", 10)]:
            rows.append(Listing(name, "Software Engineer", name, "India", f"https://www.naukri.com/job/{name}", "Build Python services.", True,
                                datetime.utcnow() - timedelta(days=days, hours=1), {"experience_range": years, "employment_type": "full_time"}))
        ingest(db, db.get(JobSource, source["id"]), Snapshot(rows, True), SearchPreferences(max_posting_age_days=None), ("Python", []))
        db.commit()
    return source


def companies(client, **params):
    response = client.get("/jobs", params={"salary_floor": 0, **params})
    assert response.status_code == 200, response.text
    return {row["company"] for row in response.json()["items"]}


def test_feed_experience_date_and_no_score_gate(isolated):
    client, factory = isolated
    seed(client, factory)
    assert companies(client, max_experience=0) == {"fresh", "unknown", "old"}
    assert companies(client, max_experience=0, include_unknown_experience="false") == {"fresh", "old"}
    assert companies(client, max_experience=0.5, include_unknown_experience="false") == {"fresh", "old"}
    assert companies(client, max_experience=3, posted_within=3) == {"fresh", "experienced", "unknown"}
    assert companies(client, max_experience=10, posted_within=7) == {"fresh", "experienced", "ten", "unknown"}
    assert companies(client, max_experience=10, posted_within=1) == {"fresh", "unknown"}
    # Older clients cannot reintroduce a hidden relevance gate.
    assert companies(client, max_experience=10, minimum_score=100) == companies(client, max_experience=10)
    assessment = client.get("/jobs").json()["items"][0]["assessment"]
    assert "relevance_score" not in assessment
    assert client.get("/jobs?max_experience=11").status_code == 422
    assert client.put("/jobs/preferences", json={"max_required_experience": 10}).status_code == 200


def test_new_search_resets_successful_checkpoint_but_preserves_real_rate_limit(isolated):
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    source = client.post("/jobs/oss/connections", json={"key": "naukri"}).json()
    from db.models import JobSource
    from jobs.scheduling import save_state
    with factory() as db:
        save_state(db, db.get(JobSource, source["id"]), {"health": "partial", "cursor": "old", "retry_at": (datetime.utcnow() + timedelta(hours=1)).isoformat()})
        db.commit()
    assert client.post("/jobs/search").status_code == 200
    with factory() as db:
        state = state_for(db, db.get(JobSource, source["id"]))
        assert state.summary["cursor"] is None and state.summary["retry_at"] is None
        db.query(AutomationTask).delete()
        state.summary = {**state.summary, "health": "rate_limited", "retry_at": "2099-01-01T00:00:00"}
        db.commit()
    assert client.post("/jobs/search").status_code == 200
    with factory() as db:
        assert state_for(db, db.get(JobSource, source["id"])).summary["retry_at"] == "2099-01-01T00:00:00"


def test_continuation_is_not_cut_off_after_fifteen_minutes(isolated):
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    client.post("/jobs/oss/connections", json={"key": "naukri"})
    client.post("/jobs/search")
    from automation.service import execute
    with factory() as db:
        task = db.query(AutomationTask).one()
        task.created_at = datetime.utcnow() - timedelta(minutes=30)
        task.status = "running"
        with patch("api.jobs.refresh", return_value={"status": "partial", "sources": [{"cursor": "next"}], "deferred": []}):
            execute(db, task)
        followup = db.query(AutomationTask).filter(AutomationTask.id != task.id).one()
        assert followup.available_at < datetime.utcnow() + timedelta(seconds=15)


def test_finished_source_is_not_refetched_during_same_search(isolated):
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    client.post("/jobs/oss/connections", json={"key": "naukri"})
    client.post("/jobs/search")
    with patch("api.jobs.fetch_source", return_value=batch().to_snapshot()) as collector:
        assert client.post("/jobs/refresh").status_code == 200
        again = client.post("/jobs/refresh")
    assert collector.call_count == 1
    assert any(item["reason"] == "Scan completed for this search" for item in again.json()["deferred"])
