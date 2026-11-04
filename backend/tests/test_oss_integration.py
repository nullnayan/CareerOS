"""Production mode isolation and OSS-to-website integration on disposable SQLite."""
import json
from unittest.mock import patch
import pytest
from core.config import settings
from tests.test_job_discovery import isolated, DESCRIPTION
from db.models import JobSource, JobPosting, AutomationTask, JobRefreshRun, User
from jobs.connectors import SourceError, fetch_source
from jobs.oss.contracts import CollectorBatch, NormalizedJob, CollectorFailure
from jobs.oss.coordinator import fetch


@pytest.fixture(autouse=True)
def oss_mode(monkeypatch):
    monkeypatch.setattr(settings, "JOB_DISCOVERY_ENGINE", "oss")
    monkeypatch.setattr(settings, "JOB_LEGACY_ENABLED", False)


def batch(cursor=None):
    return CollectorBatch([NormalizedJob("one", "Graduate Software Engineer", "Fixture", "India",
        "https://www.shine.com/jobs/one", DESCRIPTION, True)], cursor, "partial" if cursor else "exhausted", tool_version="fixture")


@pytest.mark.parametrize("provider", ["greenhouse", "lever", "workday", "structured_feed", "remotive", "adzuna"])
def test_legacy_dispatch_blocked_even_if_enabled(provider):
    with patch("jobs.connectors.request_json", side_effect=AssertionError("network")):
        with pytest.raises(SourceError, match="inactive"): fetch_source(provider, "public", "Fixture", {})


def test_oss_setup_keeps_pause_and_legacy_rows_and_cannot_enable_them(isolated):
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    from jobs.search_control import set_control
    with factory() as db:
        owner = db.query(User).one()
        source = JobSource(user_id=owner.id, provider="lever", board="ion", company="Legacy", enabled=True)
        db.add(source); db.flush(); identifier = source.id
        set_control(db, owner.id, {"paused": True, "generation": "original"}); db.commit()
    with patch("jobs.oss.omkar_adapter.collect", side_effect=AssertionError("No collection during setup")):
        first = client.post("/jobs/oss/connections", json={"key": "shine"})
        assert first.status_code == 200, first.text
        assert client.post("/jobs/oss/connections", json={"key": "shine"}).json()["id"] == first.json()["id"]
        catalog = client.get("/jobs/oss").json()
        assert len(catalog["coverage"]["sources"]) == 47
        assert len(catalog["runtime"]) == 6
    assert client.patch(f"/jobs/sources/{identifier}", json={"enabled": False}).status_code == 409
    assert client.post("/jobs/connections/free").status_code == 409
    assert client.post("/jobs/sources", json={"provider": "lever", "board": "one", "company": "No"}).status_code == 409
    assert client.post("/jobs/sources/feed", json={"company": "No", "feed_url": "https://example.com/feed"}).status_code == 409
    assert client.post("/jobs/sources/employer", json={"provider": "workday", "company": "No", "url": "https://example.wd5.myworkdayjobs.com/External", "access_reviewed": True}).status_code == 409
    with factory() as db:
        assert db.get(JobSource, identifier).enabled
        assert db.query(JobRefreshRun).filter_by(status="search_control").one().summary["paused"]
        assert db.query(AutomationTask).count() == db.query(JobPosting).count() == 0
    assert client.post("/jobs/refresh").status_code == 409


def test_oss_search_ingestion_and_legacy_exclusion(isolated):
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    source = client.post("/jobs/oss/connections", json={"key": "shine"}).json()
    with factory() as db:
        owner = db.query(User).one()
        db.add(JobSource(user_id=owner.id, provider="lever", board="ion", company="Legacy", enabled=True)); db.commit()
    start = client.post("/jobs/search").json()
    assert client.post("/jobs/search").json()["search_id"] == start["search_id"]
    with patch("jobs.oss.omkar_adapter.collect", return_value=batch()) as collector, patch("jobs.connectors.lever", side_effect=AssertionError("Legacy network")):
        result = client.post("/jobs/refresh")
    assert result.status_code == 200 and not result.json()["errors"], result.text
    assert collector.call_count == 1
    with factory() as db:
        job = db.query(JobPosting).one()
        assert job.description_complete and job.facts["access_route"] == "oss_shine"
        assert db.query(AutomationTask).one().payload["engine"] == "oss"
    status = client.get("/jobs/search/" + start["search_id"]).json()
    assert status["coverage"]["enabled_sources"] == 1
    assert source["id"] not in [s["id"] for s in client.get("/jobs/sources").json() if s["archived"]]


def test_cursors_are_bound_to_query_and_all_roles_rotate():
    prefs = {"target_roles": ["Backend", "Engineer"], "locations": ["India"], "country_code": "in"}
    with patch("jobs.oss.omkar_adapter.collect", return_value=batch()) as collect:
        first = fetch("shine", prefs)
        second = fetch("shine", {**prefs, "_cursor": first.cursor})
        assert [c.args[0].role for c in collect.call_args_list] == ["Backend", "Engineer"]
        assert not second.cursor
        fetch("shine", {**prefs, "target_roles": ["Changed"], "_cursor": first.cursor})
        assert collect.call_args.args[0].cursor is None


def test_ai_description_needs_matching_evidence_and_is_an_excerpt():
    from jobs.oss.crawl_extract import validate_ai_record
    text = "Engineer at Fixture. Build stable Python services for our customers."
    record = {"title": "Engineer", "company": "Fixture", "source_url": "https://example.com/job",
              "description": "Invented qualifications and salary", "evidence": {"title": "Engineer", "company": "Fixture", "description": "Build stable Python services for our customers."}}
    assert validate_ai_record(record, allowed_links={record["source_url"]}, source_text=text) is None
    record["description"] = record["evidence"]["description"]
    result = validate_ai_record(record, allowed_links={record["source_url"]}, source_text=text)
    assert result and not result["description_complete"]


def test_typed_failure_preserves_reason_and_never_falls_back():
    with patch("jobs.oss.omkar_adapter.collect", side_effect=CollectorFailure("rate_limited", "Wait", 429, 120)):
        with pytest.raises(SourceError) as error: fetch("shine", {})
    assert error.value.reason == "rate_limited" and error.value.retry_after_seconds == 120


def test_exact_employer_setup_and_host_boundary(isolated):
    client, _ = isolated
    client.put("/jobs/preferences", json={})
    payload = {"company": "Fixture", "url": "https://job-boards.greenhouse.io/fixture"}
    first = client.post("/jobs/oss/employer", json=payload)
    assert first.status_code == 200, first.text
    assert client.post("/jobs/oss/employer", json=payload).json()["id"] == first.json()["id"]
    assert any(row["connection"] and row["connection"]["id"] == first.json()["id"] for row in client.get("/jobs/oss").json()["sources"])
    for url in ("https://127.0.0.1/jobs", "https://evil.example/jobs", "https://greenhouse.io.evil.example/jobs"):
        assert client.post("/jobs/oss/employer", json={**payload, "url": url}).status_code == 422


def test_pause_during_collection_discards_late_oss_results(isolated):
    from jobs.search_control import set_control
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    client.post("/jobs/oss/connections", json={"key": "shine"})
    client.post("/jobs/search")
    def pause_then_return(request):
        with factory() as db:
            owner = db.query(User).one()
            set_control(db, owner.id, {"paused": True, "generation": "replaced"}); db.commit()
        return batch()
    with patch("jobs.oss.omkar_adapter.collect", side_effect=pause_then_return):
        response = client.post("/jobs/refresh")
    assert response.status_code == 200, response.text
    with factory() as db: assert db.query(JobPosting).count() == 0


def test_registered_fallback_resumes_without_repeating_primary():
    with patch("jobs.oss.ats_adapter.collect", side_effect=CollectorFailure("unsupported", "Shape changed")) as primary, patch("jobs.oss.crawl_adapter.collect", side_effect=[batch("next"), batch()]) as fallback:
        first = fetch("wipro", {})
        second = fetch("wipro", {"_cursor": first.cursor})
        assert primary.call_count == 1 and fallback.call_count == 2
        assert first.jobs[0].facts["access_route"] == "oss_crawl4ai"
        assert fallback.call_args.args[0].cursor == "next" and second.cursor is None


@pytest.mark.parametrize("reason", ["blocked", "rate_limited", "login_required", "cancelled"])
def test_fallback_does_not_retry_access_denials_or_cancelled_tasks(reason):
    with patch("jobs.oss.ats_adapter.collect", side_effect=CollectorFailure(reason, "Stop")), patch("jobs.oss.crawl_adapter.collect") as fallback:
        with pytest.raises(SourceError): fetch("wipro", {})
        fallback.assert_not_called()


def test_valid_empty_query_does_not_invoke_fallback():
    with patch("jobs.oss.ats_adapter.collect", return_value=CollectorBatch([], None, "exhausted")), patch("jobs.oss.crawl_adapter.collect") as fallback:
        assert not fetch("wipro", {}).jobs
        fallback.assert_not_called()


def test_pause_endpoint_keeps_jobs_and_signals_running_tasks(isolated, monkeypatch, tmp_path):
    from jobs.oss import cancellation
    monkeypatch.setattr(cancellation, "RUNTIME_ROOT", tmp_path)
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    client.post("/jobs/oss/connections", json={"key": "shine"})
    search = client.post("/jobs/search").json()
    with factory() as db:
        task = db.query(AutomationTask).one(); task.status = "running"; task_id = task.id; owner_id = task.user_id; db.commit()
    assert client.post("/jobs/pause").json()["paused"]
    assert cancellation.marker(cancellation.token(owner_id, "task", task_id)).exists()
    assert cancellation.marker(cancellation.token(owner_id, "generation", search["search_id"])).exists()
    with factory() as db:
        assert db.query(AutomationTask).one().status == "cancelled"
        assert db.query(JobSource).count() == 1


def test_omkar_page_slices_resume_and_detect_repeat():
    from jobs.oss.omkar_adapter import collect
    from jobs.oss.contracts import CollectorRequest, query_fingerprint
    from dataclasses import replace
    request = CollectorRequest("shine", "shine", "shine", 0,
        query_fingerprint("shine", "shine", "engineer", "India", "IN"), "engineer", "India", "IN", max_results=1)
    rows = [{"id": str(i), "title": "Engineer", "company": "Example", "link": f"https://www.shine.com/jobs/{i}", "description": DESCRIPTION} for i in range(3)]
    with patch("jobs.oss.omkar_adapter.invoke", return_value={"jobs": rows, "has_more": True, "next_page": 2}):
        a = collect(request); b = collect(replace(request, cursor=a.next_cursor)); c = collect(replace(request, cursor=b.next_cursor))
        assert [j.native_id for part in (a, b, c) for j in part.jobs] == ["0", "1", "2"]
        repeated = collect(replace(request, cursor=c.next_cursor))
        assert not repeated.next_cursor and not repeated.jobs


def test_old_worker_task_rejected_and_explicit_rollback(isolated, monkeypatch):
    from automation.service import execute
    from fastapi import HTTPException
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    with factory() as db:
        owner = db.query(User).one()
        task = AutomationTask(user_id=owner.id, kind="discover", status="queued", payload={}, result={}, dedupe_key="old", attempts=0)
        db.add(task); db.flush()
        with pytest.raises(HTTPException, match="inactive discovery"): execute(db, task)
    monkeypatch.setattr(settings, "JOB_DISCOVERY_ENGINE", "legacy")
    with pytest.raises(SourceError, match="explicit"): fetch_source("lever", "ion", "Old", {})
    monkeypatch.setattr(settings, "JOB_LEGACY_ENABLED", True)
    with patch("jobs.adapters.dispatch", return_value="old"):
        assert fetch_source("lever", "ion", "Old", {}) == "old"
