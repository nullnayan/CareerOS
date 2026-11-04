"""Public status/caching regression cases; no accounts or live network."""
import io
import json
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.error import HTTPError
import pytest
from tests.test_job_discovery import isolated, setup_source, listing
from tests.test_free_discovery import make_due
from jobs.connectors import Snapshot, SourceError, request_json
from jobs.verification import fetch_statuses
from jobs import http_cache
from db.models import JobSourceOccurrence, JobPosting, JobSource


@pytest.fixture(autouse=True)
def cache_isolation():
    http_cache.clear()
    yield
    http_cache.clear()


def response(data, headers=None):
    stream = io.BytesIO(json.dumps(data).encode())
    stream.headers = headers or {}
    return stream


def test_conditional_response_revalidates_without_serving_stale_on_error():
    url = "https://api.lever.co/test"
    with patch("jobs.connectors.urlopen", return_value=response({"jobs": [1]}, {"ETag": '"v1"'})):
        assert request_json(url) == {"jobs": [1]}
    with patch("jobs.connectors.urlopen", side_effect=HTTPError(url, 304, "Not modified", {}, None)) as fetch:
        assert request_json(url) == {"jobs": [1]}
        assert fetch.call_args.args[0].get_header("If-none-match") == '"v1"'
    with patch("jobs.connectors.urlopen", side_effect=HTTPError(url, 429, "Wait", {"Retry-After": "7200"}, None)):
        with pytest.raises(SourceError) as error: request_json(url)
        assert error.value.status_code == 429 and error.value.retry_after_seconds == 7200


@pytest.mark.parametrize("headers", [{"ETag": "a", "Cache-Control": "no-store"}, {"ETag": "a", "Cache-Control": "private"}, {"ETag": "a", "Vary": "Cookie"}])
def test_private_responses_are_not_cached(headers):
    url = "https://api.lever.co/test"
    with patch("jobs.connectors.urlopen", return_value=response({}, headers)):
        request_json(url)
    assert http_cache.get(url) is None


def test_status_results_ignore_unrequested_ids_and_validate_destinations():
    with patch("jobs.verification.request_json", return_value={"jobs": [{"id": 1, "status": "closed"}, {"id": 99, "status": "closed"}]}):
        assert fetch_statuses("jobicy", [("1", "")]) == {"1": "closed"}
    with patch("jobs.verification.request_json") as fetch:
        assert fetch_statuses("himalayas", [("https://127.0.0.1/companies/a/jobs/b", "")]) == {}
        fetch.assert_not_called()


@pytest.mark.parametrize("code,expected", [(410, "closed"), (404, "unknown")])
def test_himalayas_only_gone_confirms_closure(code, expected):
    guid = "https://himalayas.app/companies/example/jobs/graduate"
    with patch("jobs.verification.request_json", side_effect=SourceError("Unavailable", status_code=code)):
        assert fetch_statuses("himalayas", [(guid, "")]) == {guid: expected}


@pytest.mark.parametrize("status,job_status", [("closed", "closed"), ("unknown", "open"), ("active", "open")])
def test_old_feed_jobs_are_verified_without_inferring_closure_from_absence(isolated, status, job_status):
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    client.post("/jobs/sources", json={"provider": "jobicy", "board": "public", "company": "Jobicy"})
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing("123")], False, scope="rolling_feed")):
        client.post("/jobs/refresh")
    with factory() as db:
        db.query(JobSourceOccurrence).one().last_seen_at = datetime.utcnow() - timedelta(days=9)
        db.commit()
    make_due(factory)
    with patch("api.jobs.fetch_source", return_value=Snapshot([], False, scope="rolling_feed")), patch("api.jobs.fetch_statuses", return_value={"123": status}) as check:
        result = client.post("/jobs/refresh").json()
        assert check.call_args.args[1][0][0] == "123"
        assert result["sources"][0]["status_checks"]["checked"] == 1
    with factory() as db:
        job = db.query(JobPosting).one()
        assert job.status == job_status
        assert next(iter(job.facts["source_status_checks"].values()))["status"] == status


def test_closing_one_feed_does_not_close_another_active_source(isolated):
    from jobs.verification import apply_statuses
    from jobs.schemas import SearchPreferences
    client, factory = isolated
    source = setup_source(client)
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing("123")])):
        client.post("/jobs/refresh")
    with factory() as db:
        original = db.query(JobSourceOccurrence).one()
        second = JobSource(user_id=db.query(JobSource).one().user_id, provider="jobicy", board="public", company="Jobicy")
        db.add(second); db.flush()
        db.add(JobSourceOccurrence(source_id=second.id, job_id=original.job_id, native_id="123", source_url=original.source_url, active=True))
        db.flush()
        assert apply_statuses(db, second, {"123": "closed"}, SearchPreferences(), ("", []))["closed"] == 0
        assert db.query(JobPosting).one().status == "open"


def test_successful_source_toggle_cannot_bypass_normal_poll_floor(isolated, monkeypatch):
    client, _ = isolated
    monkeypatch.setattr("jobs.scheduling.polling_floor", lambda provider: 3600)
    source = setup_source(client)
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing()])) as fetch:
        client.post("/jobs/refresh")
        for enabled in (False, True): client.patch(f"/jobs/sources/{source['id']}", json={"enabled": enabled})
        client.post("/jobs/refresh")
        assert fetch.call_count == 1


def test_company_directory_retains_only_supported_board_mappings(isolated):
    client, _ = isolated
    boards = client.get("/jobs/catalog").json()["company_boards"]
    assert len(boards) == 15
    new_boards = [row for row in boards if row["board"] in {"twilio", "cred", "ServiceNow", "microsoftcorporation"}]
    assert len(new_boards) == 4 and all(not row["verified_for_setup"] for row in new_boards)
    assert any(b["board"] == "gravitonresearchcapital" for b in boards)
    assert not any(b["board"] in {"phonepe", "postman"} for b in boards)


def test_experience_before_range_is_not_lost():
    from jobs.matching import experience_required
    assert experience_required("Experience: 2–5 years as a Software Engineer or Python Developer.") == 2
    assert experience_required("Preferred: Experience: 2–5 years as a Software Engineer.") is None


@pytest.mark.parametrize("jobs", [[], [{"id": 1, "status": "active"}, {"id": 1, "status": "closed"}]])
def test_incomplete_or_conflicting_batch_status_cannot_close_jobs(jobs):
    with patch("jobs.verification.request_json", return_value={"jobs": jobs}):
        with pytest.raises(SourceError): fetch_statuses("jobicy", [("1", "")])
