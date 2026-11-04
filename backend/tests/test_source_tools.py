"""Fixture-only source integration and large-catalogue safety gates."""
import json
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy import event
from tests.test_job_discovery import isolated, DESCRIPTION
from db.models import JobPosting, JobSource, AutomationTask, JobRefreshRun, AutomationSettings
from jobs.enterprise import workday, workday_site, fetch
from jobs.connectors import SourceError
from jobs.reviewed_exports import preview, SITES

SITE = "https://example.wd5.myworkdayjobs.com/External"


def workday_request(url, payload=None):
    if payload is not None:
        offset = payload["offset"]
        return json.dumps({"total": 10000, "jobPostings": [{"title": "Engineer", "externalPath": f"/job/India/Engineer_R{i}", "postedOn": "Posted 30+ Days Ago"} for i in range(offset, offset + 8)]}).encode()
    native = url.rsplit("_", 1)[-1]
    return json.dumps({"jobPostingInfo": {"jobReqId": native, "title": "Graduate Engineer", "jobDescription": DESCRIPTION, "location": "India", "timeType": "Full time", "startDate": "2026-11-01"}}).encode()


@pytest.mark.parametrize("url", ["https://evil.myworkdayjobs.com/External", "https://example.wd5.myworkdayjobs.com.evil.com/External", "https://example.wd5.myworkdayjobs.com/External/job/a", "https://example.wd5.myworkdayjobs.com/External?token=secret", "http://example.wd5.myworkdayjobs.com/External", "https://u:p@example.wd5.myworkdayjobs.com/External", "https://example.wd5.myworkdayjobs.com/../External"])
def test_workday_destination_contract(url):
    with pytest.raises(ValueError): workday_site(url)


def test_workday_large_catalogue_is_bounded_and_recovers_cursor():
    with patch("jobs.enterprise.request_public", side_effect=workday_request) as request:
        first = workday("Employer", {"site_url": SITE})
        assert request.call_count == 9
        second = workday("Employer", {"site_url": SITE}, first.cursor)
        assert request.call_count == 18
    assert first.jobs[0].native_id == "R0" and second.jobs[0].native_id == "R8"
    assert not first.complete and first.cursor and not first.traversal_valid
    assert all(j.complete and j.published_at is None and j.facts["publication_date_unknown"] for j in first.jobs)
    assert first.jobs[0].facts["source_url"].startswith(SITE)


def test_workday_slow_details_keep_progress_and_resume_without_loss():
    clock = [0]
    def slow_request(url, payload=None):
        clock[0] += 10
        return workday_request(url, payload)
    with patch("jobs.enterprise.time.monotonic", side_effect=lambda: clock[0]), patch("jobs.enterprise.request_public", side_effect=slow_request):
        first = workday("Employer", {"site_url": SITE})
        state = json.loads(first.cursor)
        assert state["offset"] == 7 and len(state["pages"]) == 1
        second = workday("Employer", {"site_url": SITE}, first.cursor)
    assert [job.native_id for job in first.jobs + second.jobs] == [f"R{i}" for i in range(14)]
    assert json.loads(second.cursor)["offset"] == 14
    assert not first.metadata()["can_close_missing"]


def test_workday_partial_page_still_detects_ignored_offset():
    clock = [0]
    def ignored_offset(url, payload=None):
        clock[0] += 10
        return workday_request(url, {**payload, "offset": 0} if payload else None)
    with patch("jobs.enterprise.time.monotonic", side_effect=lambda: clock[0]), patch("jobs.enterprise.request_public", side_effect=ignored_offset):
        first = workday("Employer", {"site_url": SITE})
        with pytest.raises(SourceError, match="Repeated"):
            workday("Employer", {"site_url": SITE}, first.cursor)


def test_workday_search_using_entire_budget_retains_initial_offset():
    clock = [0]
    def slow_search(url, payload=None):
        clock[0] += 80
        return workday_request(url, payload)
    with patch("jobs.enterprise.time.monotonic", side_effect=lambda: clock[0]), patch("jobs.enterprise.request_public", side_effect=slow_search) as request:
        result = workday("Employer", {"site_url": SITE})
    assert not result.jobs and request.call_count == 1
    assert json.loads(result.cursor)["offset"] == 0


@pytest.mark.parametrize("response", [{}, {"total": "0", "jobPostings": []}, {"total": -1, "jobPostings": []}, {"total": 1, "jobPostings": [{"externalPath": "https://evil.com"}]}])
def test_workday_schema_changes_are_not_empty_success(response):
    with patch("jobs.enterprise.request_public", return_value=json.dumps(response).encode()):
        with pytest.raises(SourceError): workday("Employer", {"site_url": SITE})


def test_workday_empty_and_repeated_pages_do_not_close_jobs():
    with patch("jobs.enterprise.request_public", return_value=b'{"total":0,"jobPostings":[]}'):
        result = workday("Employer", {"site_url": SITE})
        assert not result.complete and result.warnings and not result.metadata()["can_close_missing"]
    with patch("jobs.enterprise.request_public", side_effect=workday_request):
        first = workday("Employer", {"site_url": SITE})
        state = json.loads(first.cursor); state["offset"] = 0
        with pytest.raises(SourceError, match="Repeated"): workday("Employer", {"site_url": SITE}, json.dumps(state))


def test_workday_checkpoint_has_no_fixed_catalogue_quota_and_keeps_reported_total():
    checkpoint = {"offset": 8000, "pages": [str(i) for i in range(100)], "total": 10000}
    def response(url, payload=None):
        value = json.loads(workday_request(url, payload))
        if payload is not None: value["total"] = 0
        return json.dumps(value).encode()
    with patch("jobs.enterprise.request_public", side_effect=response):
        result = workday("Employer", {"site_url": SITE}, json.dumps(checkpoint))
    state = json.loads(result.cursor)
    assert state["offset"] == 8008 and state["total"] == 10000 and len(state["pages"]) == 100
    assert state["pages"][0] == "0"


@pytest.mark.parametrize("status", [401, 403, 429])
def test_workday_failures_preserve_retry_status(status):
    with patch("jobs.enterprise.request_public", side_effect=SourceError("Provider failure", 120, status)):
        with pytest.raises(SourceError) as error: workday("Employer", {"site_url": SITE})
    assert error.value.status_code == status and error.value.retry_after_seconds == 120


def test_employer_setup_does_not_search_or_change_pause(isolated):
    client, factory = isolated
    from jobs.search_control import set_control
    client.get("/jobs/sources")
    with factory() as db:
        from db.models import User
        owner = db.query(User).one()
        set_control(db, owner.id, {"paused": True, "generation": "fixture"}); db.commit()
    payload = {"provider": "workday", "company": "Employer", "url": SITE, "access_reviewed": True}
    with patch("jobs.enterprise.request_public") as request:
        assert client.post("/jobs/sources/employer", json={**payload, "access_reviewed": False}).status_code == 422
        result = client.post("/jobs/sources/employer", json=payload)
        assert result.status_code == 200, result.text
        assert client.post("/jobs/sources/employer", json=payload).json()["id"] == result.json()["id"]
        assert client.get("/jobs/sources").json()[0]["health"] == "never_checked"
        assert not request.called
    with factory() as db:
        assert db.query(JobPosting).count() == db.query(AutomationTask).count() == 0
        state = db.query(JobRefreshRun).filter_by(status="search_control").one()
        assert state.summary["paused"]
    entries = client.get("/jobs/connections").json()["platforms"]
    assert len(entries) == 45
    assert next(e for e in entries if e["name"] == "Workday")["connection_state"] == "connected"


@pytest.mark.parametrize("provider", ["taleo", "sap_successfactors", "oracle_recruiting", "icims"])
def test_enterprise_feeds_reuse_scheduler_without_claiming_native_api(provider, isolated):
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    config = {"provider": provider, "company": "Employer", "url": "https://example.com/feed", "full_descriptions": True, "access_reviewed": True}
    assert client.post("/jobs/sources/employer", json=config).status_code == 200
    body = f'<rss><channel><item><guid>one</guid><title>Graduate Engineer</title><link>https://example.com/job/one</link><description>{DESCRIPTION}</description></item></channel></rss>'.encode()
    with patch("jobs.enterprise.fetch_public_feed", return_value=body):
        response = client.post("/jobs/refresh")
    assert not response.json()["errors"], response.text
    with factory() as db:
        job = db.query(JobPosting).one()
        assert job.description_complete == (provider != "taleo")
        assert job.facts["source_family"] == provider
        assert db.query(JobRefreshRun).filter_by(status="source_state").one().summary["configuration"]["feed_url"] == config["url"]


def export_row(site="naukri", **changes):
    return {"site": site, "title": "Graduate Engineer", "company": "Employer", "location": "India",
            "job_url": "https://www." + SITES[site][0] + "/jobs/one", "description": DESCRIPTION, **changes}


@pytest.mark.parametrize("site", list(SITES))
def test_source_specific_community_exports_are_offline(site):
    result = preview(json.dumps([export_row(site)]), "json")
    assert len(result["items"]) == 1 and not result["items"][0]["description_complete"]
    assert not preview(json.dumps([export_row(site, job_url="https://evil.com/job")]), "json")["items"]


def test_reviewed_import_requires_selection_is_idempotent_and_never_schedules(isolated):
    client, factory = isolated
    payload = {"format": "json", "content": json.dumps([export_row(), export_row("bdjobs")])}
    assert len(client.post("/jobs/imports/preview", json=payload).json()["items"]) == 2
    assert client.post("/jobs/imports/commit", json={**payload, "rows": [0]}).status_code == 422
    for _ in range(2):
        result = client.post("/jobs/imports/commit", json={**payload, "rows": [0], "confirmed": True})
        assert result.status_code == 200, result.text
    with factory() as db:
        job = db.query(JobPosting).one()
        assert not job.description_complete and job.facts["access_route"] == "reviewed_export"
        assert db.query(JobSource).one().board == "reviewed:naukri"
        assert db.query(AutomationTask).count() == 0
    assert client.post("/jobs/imports/commit", json={**payload, "rows": [1, 1], "confirmed": True}).status_code == 422


def test_export_limits_malformed_duplicate_and_salary_estimates():
    from jobs.reviewed_exports import normalized
    with pytest.raises(ValueError): preview(json.dumps([export_row()] * 201), "json")
    with pytest.raises(ValueError): preview("x" * 2000001, "csv")
    result = preview(json.dumps([export_row(), export_row(), None, export_row(title="")]), "json")
    assert len(result["items"]) == 1 and len(result["errors"]) == 3
    job = normalized(export_row(salary_source="description", min_amount=900000, currency="INR", interval="yearly"))
    assert "salary_min" not in job.facts
    job = normalized(export_row(salary_source="direct_data", min_amount=900000, currency="INR", interval="yearly"))
    assert job.facts["salary_min"] == 900000


@pytest.mark.parametrize("route,extra", [("preview", {}), ("commit", {"rows": [0], "confirmed": True})])
def test_nested_export_is_validation_error(isolated, route, extra):
    client, _ = isolated
    response = client.post(f"/jobs/imports/{route}", json={"format": "json", "content": "[" * 1100 + "0" + "]" * 1100, **extra})
    assert response.status_code == 422


@pytest.mark.parametrize("salary_source,description,evidence", [
    ("estimated", DESCRIPTION + "\nEstimated salary: 8-12 LPA.", None),
    ("", DESCRIPTION + "\nEstimated salary: 8-12 LPA.", None),
    ("description", DESCRIPTION + "\nSalary: 8-12 LPA.", "description"),
    ("direct_data", DESCRIPTION, "source_fields"),
])
def test_import_salary_provenance_survives_ingestion_and_reassessment(isolated, salary_source, description, evidence):
    from jobs.salary import salary_facts
    client, factory = isolated
    row = export_row(salary_source=salary_source, description=description, min_amount=800000,
                     max_amount=1200000, currency="INR", interval="yearly")
    result = client.post("/jobs/imports/commit", json={"content": json.dumps([row]), "format": "json", "rows": [0], "confirmed": True})
    assert result.status_code == 200, result.text
    with factory() as db:
        job = db.query(JobPosting).one()
        assert job.facts["original_salary_source"] == salary_source
        assert job.facts.get("salary_evidence") == evidence
        assert job.facts.get("annual_salary_min_inr") == (800000 if evidence else None)
        assert salary_facts(job.description, job.facts) == job.facts


def test_pinned_transport_handles_rate_limits_and_cache():
    from jobs.feed_transport import request_public
    from jobs import http_cache
    http_cache.clear()
    connection, response = MagicMock(), MagicMock()
    connection.getresponse.return_value = response
    response.status = 429; response.getheader.side_effect = lambda key, default=None: "120" if key == "Retry-After" else default
    with patch("jobs.feed_transport.public_addresses", return_value=["8.8.8.8"]), patch("jobs.feed_transport.PinnedHTTPS", return_value=connection):
        with pytest.raises(SourceError) as error: request_public("https://example.com/feed")
        assert error.value.retry_after_seconds == 120 and error.value.status_code == 429
        http_cache.put("https://example.com/feed", b"cached", {"ETag": '"v1"'})
        response.status = 304
        assert request_public("https://example.com/feed") == b"cached"
        assert connection.request.call_args.kwargs["headers"]["If-None-Match"] == '"v1"'
    http_cache.clear()


def test_large_ingestion_bulk_reads_and_paused_catalogue_skips_reassessment(isolated):
    from tests.test_job_discovery import setup_source, listing
    from jobs.service import ingest, preferences_for
    from jobs.connectors import Snapshot
    from jobs.search_control import set_control
    from db.models import JobMatch, JobDescriptionRevision, JobSourceOccurrence
    client, factory = isolated
    identifier = setup_source(client)["id"]
    engine = factory.kw["bind"]
    reads = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("select"): reads.append(statement)
    records = [listing(str(i), title=f"Graduate Engineer {i}", description=DESCRIPTION + str(i), apply_url=f"https://example.com/{i}") for i in range(1200)]
    with factory() as db:
        source = db.get(JobSource, identifier)
        prefs, _ = preferences_for(db, source.user_id)
        from sqlalchemy import text
        db.execute(text("PRAGMA foreign_keys=ON"))
        for _ in range(2):
            reads.clear(); event.listen(engine, "before_cursor_execute", capture)
            try: result = ingest(db, source, Snapshot(records, False), prefs, ("", []))
            finally: event.remove(engine, "before_cursor_execute", capture)
            assert result["listed"] == 1200 and len(reads) <= 30, len(reads)
            db.commit()
        assert db.query(JobPosting).count() == db.query(JobMatch).count() == db.query(JobDescriptionRevision).count() == db.query(JobSourceOccurrence).count() == 1200
        set_control(db, source.user_id, {"paused": True}); db.commit()
    with patch("api.jobs.assess", side_effect=AssertionError("Paused catalogue must not reassess")):
        result = client.get("/jobs").json()
        assert result["paused"] and result["stored"] == 1200 and not result["items"]


def test_register_and_employer_review_retain_every_named_candidate():
    from jobs.registry import source_register, EMPLOYERS
    from jobs.employer_review import employer_reviews
    rows = source_register()
    assert len(rows) == 45 and len({r["id"] for r in rows}) == 45
    assert all(r.get("required_prerequisite") for r in rows if r["implementation"] in {"researching", "fixture_tested"})
    assert {row["company"] for row in employer_reviews()} == set(EMPLOYERS)
