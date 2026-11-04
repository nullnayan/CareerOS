"""Isolated regression gates for free discovery expansion."""
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.request import Request
import pytest
from tests.test_job_discovery import isolated, listing, setup_source, DESCRIPTION
from jobs.connectors import Snapshot, SourceError, board_slug, _NoRedirect
from jobs.company_connectors import ashby, workable, smartrecruiters
from jobs.public_feeds import public_feed
from jobs.registry import source_register, EMPLOYERS
from db.models import JobPosting, JobMatch, JobSource, JobRefreshRun, JobDescriptionRevision


@pytest.mark.parametrize("provider,url,expected", [
    ("ashby", "https://jobs.ashbyhq.com/Example", "Example"),
    ("smartrecruiters", "https://careers.smartrecruiters.com/Example", "Example"),
    ("workable", "https://apply.workable.com/example/", "example"),
    ("lever", "https://jobs.eu.lever.co/example", "eu:example")])
def test_known_board_url_detection(provider, url, expected):
    assert board_slug(provider, url) == expected


@pytest.mark.parametrize("url", ["https://jobs.ashbyhq.com.evil.com/example", "https://u:p@jobs.ashbyhq.com/example",
    "https://jobs.ashbyhq.com:8000/example", "http://jobs.ashbyhq.com/example", "https://127.0.0.1/example"])
def test_board_url_boundaries(url):
    with pytest.raises(ValueError): board_slug("ashby", url)


def test_redirect_is_fixed_host_exact_path_only():
    handler = _NoRedirect()
    original = Request("https://www.workable.com/api/accounts/example?details=true")
    allowed = handler.redirect_request(original, None, 302, "", {}, "https://apply.workable.com/api/v1/widget/accounts/example?details=true")
    assert allowed.host == "apply.workable.com"
    for target in ["https://127.0.0.1/internal", "https://apply.workable.com/api/v1/widget/accounts/other?details=true", "http://apply.workable.com/api/v1/widget/accounts/example?details=true"]:
        with pytest.raises(SourceError): handler.redirect_request(original, None, 302, "", {}, target)


def test_ashby_full_empty_and_malformed_records():
    item = dict(title="Graduate Engineer", location="India", applyUrl="https://jobs.ashbyhq.com/example/one/apply",
        jobUrl="https://jobs.ashbyhq.com/example/one", descriptionPlain=DESCRIPTION, publishedAt="2026-10-31T00:00:00Z")
    with patch("jobs.company_connectors.request_json", return_value={"jobs": [item, None]}): result = ashby("example", "Example")
    assert len(result.jobs) == 1 and result.skipped == 1 and not result.complete
    assert result.jobs[0].published_at == datetime(2026, 10, 31)
    with patch("jobs.company_connectors.request_json", return_value={"jobs": []}): assert ashby("example", "Example").complete
    with patch("jobs.company_connectors.request_json", return_value={}):
        with pytest.raises(SourceError): ashby("example", "Example")


def test_workable_sections_are_complete_and_created_is_not_publication():
    item = dict(shortcode="one", title="Engineer", url="https://apply.workable.com/example/j/one", location={"city": "Bengaluru", "country": "India"},
        description=DESCRIPTION, requirements="Python required", benefits="Learning", created_at="2026-10-31")
    with patch("jobs.company_connectors.request_json", return_value={"jobs": [item]}): result = workable("example", "Example")
    assert result.complete and result.jobs[0].complete and "Learning" in result.jobs[0].description
    assert result.jobs[0].published_at is None


def test_smartrecruiters_paginates_budgets_and_detects_repeated_pages():
    detail = dict(name="Engineer", applyUrl="https://jobs.smartrecruiters.com/Example/1", location={"country": "in"},
        jobAd={"sections": {"jobDescription": {"text": DESCRIPTION}}})
    pages = [{"content": [{"id": "1"}], "totalFound": 2}, detail, {"content": [{"id": "2"}], "totalFound": 2}, detail]
    with patch("jobs.company_connectors.request_json", side_effect=pages): result = smartrecruiters("Example", "Example")
    assert result.complete and result.pages == 2 and len(result.jobs) == 2
    with patch("jobs.company_connectors.request_json", side_effect=pages[:2]): result = smartrecruiters("Example", "Example", max_pages=1)
    assert not result.complete and result.cursor == "1"
    with patch("jobs.company_connectors.request_json", side_effect=[pages[0], detail, pages[0]]): result = smartrecruiters("Example", "Example")
    assert not result.complete and "repeated" in result.truncation_reason.lower()


def test_public_window_and_attribution_do_not_claim_full_snapshot():
    item = dict(id=1, jobTitle="Graduate Engineer", companyName="Example", jobGeo="India", url="https://jobicy.com/jobs/1",
        jobDescription=DESCRIPTION, pubDate="2026-10-31T00:00:00Z")
    with patch("jobs.public_feeds.request_json", return_value={"jobs": [item], "nextCursor": "next"}): result = public_feed("jobicy")
    assert not result.complete and not result.metadata()["can_close_missing"] and result.cursor == "next"
    assert result.jobs[0].facts["attribution"] == "Jobicy" and result.jobs[0].complete
    with patch("jobs.public_feeds.request_json", return_value={"jobs": [item], "nextCursor": "next"}): repeated = public_feed("jobicy", "next")
    assert repeated.cursor is None and "Repeated" in repeated.warnings[-1]


def test_source_inventory_retains_all_groups_without_claiming_connections():
    names = {e["name"] for e in source_register()}
    assert {"Naukri.com", "Himalayas", "Oracle Recruiting", "Taleo", "SAP SuccessFactors", "Preplaced", "FreshersNow", "Adzuna"} <= names
    assert len(EMPLOYERS) == len(set(EMPLOYERS)) and {"Wipro", "Tekion", "Target", "Point72"} <= set(EMPLOYERS)
    assert next(e for e in source_register() if e["name"] == "Adzuna")["access"] == "excluded_paid"


def test_directory_no_twelve_source_limit_and_no_new_paid_sources(isolated):
    client, _ = isolated
    for index in range(14):
        response = client.post("/jobs/sources", json={"provider": "ashby", "board": f"example{index}", "company": "Example"})
        assert response.status_code == 200
    assert len(client.get("/jobs/sources").json()) == 14
    assert client.post("/jobs/sources", json={"provider": "adzuna", "board": "in", "company": "Adzuna"}).status_code == 422


def test_paginated_feed_cached_reads_filters_and_invalidation(isolated):
    client, factory = isolated
    setup_source(client)
    jobs = [listing(str(i), title=f"Graduate Software Engineer {i}", apply_url=f"https://example.com/{i}", description=DESCRIPTION + str(i)) for i in range(7)]
    with patch("api.jobs.fetch_source", return_value=Snapshot(jobs)): client.post("/jobs/refresh")
    with patch("jobs.service.evaluate", side_effect=AssertionError("Normal reads must reuse assessments")):
        first = client.get("/jobs?eligibility=all&limit=3&page=1").json()
        second = client.get("/jobs?eligibility=all&limit=3&page=2").json()
        assert first["total"] == 7 and first["has_next"] and len(first["items"]) == 3
        assert not {j["id"] for j in first["items"]} & {j["id"] for j in second["items"]}
        assert client.get("/jobs?eligibility=all&q=Engineer%206").json()["total"] == 1
    # Confirmed resume evidence changes invalidate existing cached assessments.
    from db.models import ConfirmedSkill
    owner = client.get("/workspace").json()["id"]
    with factory() as db:
        db.add(ConfirmedSkill(user_id=owner, name="Python", canonical="python", category="Languages")); db.commit()
    import jobs.service
    with patch("jobs.service.evaluate", wraps=jobs.service.evaluate) as evaluate:
        assert client.get("/jobs?eligibility=all&sort=newest").status_code == 200
        assert evaluate.call_count == 7
    assert client.get("/jobs?page=0").status_code == 422


def test_full_jd_survives_excerpt_and_keeps_revision(isolated):
    client, factory = isolated
    setup_source(client)
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing()])): client.post("/jobs/refresh")
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing(description="Excerpt only", complete=False)], False)): client.post("/jobs/refresh")
    with factory() as db:
        assert db.query(JobPosting).one().description == DESCRIPTION
        assert db.query(JobDescriptionRevision).count() == 2


def test_polling_and_retry_after_are_durable(isolated, monkeypatch):
    client, factory = isolated
    source = setup_source(client)
    monkeypatch.setattr("jobs.scheduling.polling_floor", lambda provider: 3600)
    with patch("api.jobs.fetch_source", side_effect=SourceError("Source rate limit reached (HTTP 429).", 7200)) as fetch:
        client.post("/jobs/refresh"); client.post("/jobs/refresh")
        assert fetch.call_count == 1
    state = client.get("/jobs/sources").json()[0]
    assert state["health"] == "rate_limited" and datetime.fromisoformat(state["retry_at"]) > datetime.utcnow() + timedelta(minutes=119)
    assert len(client.get("/jobs/refreshes").json()) == 2


def test_checkpoint_is_committed_and_used_without_closing_missing(isolated):
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    client.post("/jobs/sources", json={"provider": "smartrecruiters", "board": "Example", "company": "Example"})
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing()], False, cursor="8")):
        assert client.post("/jobs/refresh").json()["status"] == "partial"
    with factory() as db:
        state = db.query(JobRefreshRun).filter_by(status="source_state").one()
        state.summary = {**state.summary, "retry_at": datetime.utcnow().isoformat()}
        db.commit()
    with patch("api.jobs.fetch_source", return_value=Snapshot([], False, scope="continuation")) as fetch:
        client.post("/jobs/refresh")
        assert fetch.call_args.args[3]["_cursor"] == "8"
    assert client.get("/jobs?eligibility=all").json()["items"][0]["status"] == "open"


def test_himalayas_update_time_expiry_timezone_and_original_link(isolated):
    item = dict(title="Graduate Engineer", companyName="Example", applicationLink="https://himalayas.app/companies/example/jobs/one?utm_source=api",
        guid="https://himalayas.app/companies/example/jobs/one", description=DESCRIPTION, pubDate=1793318400,
        expiryDate=(datetime.utcnow() + timedelta(days=1)).timestamp(), locationRestrictions=["India"], timezoneRestrictions=[5.5])
    with patch("jobs.public_feeds.request_json", return_value={"jobs": [item], "nextCursor": "next"}): snapshot = public_feed("himalayas")
    assert snapshot.jobs[0].published_at is None and snapshot.jobs[0].facts["source_updated_at"] == item["pubDate"]
    from tests.test_job_discovery import posting
    from jobs.matching import evaluate
    from jobs.schemas import SearchPreferences
    assert not any("timezone" in reason for reason in evaluate(posting(facts=snapshot.jobs[0].facts), SearchPreferences(), "", [])["blocked_reasons"])
    snapshot.jobs[0].facts["timezone_restrictions"] = [-5]
    assert any("timezone" in reason for reason in evaluate(posting(facts=snapshot.jobs[0].facts), SearchPreferences(), "", [])["blocked_reasons"])
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    client.post("/jobs/sources", json={"provider": "himalayas", "board": "public", "company": "Himalayas"})
    with patch("api.jobs.fetch_source", return_value=snapshot): client.post("/jobs/refresh")
    result = client.get("/jobs?eligibility=all").json()["items"][0]
    assert result["apply_url"] == item["applicationLink"]
    with factory() as db:
        job = db.get(JobPosting, result["id"])
        job.facts = {**job.facts, "source_expiry_at": (datetime.utcnow() - timedelta(days=1)).isoformat()}; db.commit()
    assert client.get("/jobs?eligibility=all").json()["total"] == 0
    assert client.get("/jobs/" + result["id"]).status_code == 410


def test_auto_provider_detection_never_fetches_arbitrary_url(isolated):
    client, _ = isolated
    with patch("api.jobs.fetch_source", side_effect=AssertionError("Setup must not fetch")):
        response = client.post("/jobs/sources", json={"provider": "auto", "board": "https://jobs.ashbyhq.com/example", "company": "Example"})
        assert response.status_code == 200 and response.json()["provider"] == "ashby"
        assert client.post("/jobs/sources", json={"provider": "auto", "board": "https://127.0.0.1/internal", "company": "Example"}).status_code == 422


def test_resumable_ingestion_budget_has_no_lifetime_count_cap():
    from jobs.connectors import _bounded_board
    jobs = [listing(str(i)) for i in range(5)]
    first = _bounded_board(Snapshot(jobs), budget=3)
    second = _bounded_board(Snapshot(jobs), cursor=first.cursor, budget=3)
    assert [j.native_id for j in first.jobs + second.jobs] == [str(i) for i in range(5)]
    assert not first.complete and not second.complete and second.cursor is None


def test_request_size_and_destination_boundaries():
    from jobs.connectors import request_json, retry_after_seconds
    from unittest.mock import MagicMock
    with pytest.raises(SourceError): request_json("https://127.0.0.1/internal")
    response = MagicMock()
    response.__enter__.return_value = response
    response.read1.return_value = b"x" * 65536
    with patch("jobs.connectors.urlopen", return_value=response):
        with pytest.raises(SourceError, match="8 MB"): request_json("https://api.ashbyhq.com/test")
    assert retry_after_seconds("172800") == 172800


def test_repeated_manual_import_retains_occurrences_without_duplicate_dependents(isolated):
    client, factory = isolated
    data = dict(title="Graduate Software Engineer", company="Example", apply_url="https://example.com/jobs/one?ref=vacancy-1", description=DESCRIPTION)
    identifiers = [client.post("/jobs/import", json=data).json()["id"] for _ in range(3)]
    assert len(set(identifiers)) == 1
    from db.models import JobSourceOccurrence
    from jobs.connectors import canonical_url
    assert canonical_url(data["apply_url"]).endswith("ref=vacancy-1")
    with factory() as db:
        assert db.query(JobPosting).count() == db.query(JobMatch).count() == db.query(JobDescriptionRevision).count() == 1
        assert db.query(JobSourceOccurrence).count() == 3


def test_unauthorized_source_requires_explicit_reenable_before_retry(isolated):
    client, factory = isolated
    source = setup_source(client)
    with patch("api.jobs.fetch_source", side_effect=SourceError("Credential rejected (HTTP 401).")) as fetch:
        client.post("/jobs/refresh")
        with factory() as db:
            state = db.query(JobRefreshRun).filter_by(status="source_state").one()
            state.summary = {**state.summary, "retry_at": (datetime.utcnow() - timedelta(days=2)).isoformat()}; db.commit()
        client.post("/jobs/refresh")
        assert fetch.call_count == 1
        client.patch(f"/jobs/sources/{source['id']}", json={"enabled": True})
        client.post("/jobs/refresh")
        assert fetch.call_count == 2


def test_fresher_short_batch_notation_includes_2027():
    from jobs.matching import graduation_batches
    assert graduation_batches("Hiring AI Engineer - Freshers 2026/27 (Computer Science or AI Only)") == [2026, 2027]
    assert graduation_batches("Founded in 2026/27. Build services.") == []


def test_expired_jobicy_cursor_starts_a_fresh_traversal(isolated):
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    client.post("/jobs/sources", json={"provider": "jobicy", "board": "public", "company": "Jobicy"})
    with patch("api.jobs.fetch_source", return_value=Snapshot([], False, scope="rolling_feed", cursor="old")):
        client.post("/jobs/refresh")
    with factory() as db:
        state = db.query(JobRefreshRun).filter_by(status="source_state").one()
        state.summary = {**state.summary, "cursor_started_at": (datetime.utcnow() - timedelta(days=2)).isoformat(), "retry_at": datetime.utcnow().isoformat()}; db.commit()
    with patch("api.jobs.fetch_source", return_value=Snapshot([], False, scope="rolling_feed", cursor="fresh")) as fetch:
        client.post("/jobs/refresh")
        assert fetch.call_args.args[3]["_cursor"] is None
    with factory() as db:
        state = db.query(JobRefreshRun).filter_by(status="source_state").one()
        assert datetime.fromisoformat(state.summary["cursor_started_at"]) > datetime.utcnow() - timedelta(minutes=1)


def test_historical_adzuna_alone_is_not_a_free_discovery_connection(isolated):
    client, factory = isolated
    client.put("/jobs/preferences", json={})
    owner = client.get("/workspace").json()["id"]
    with factory() as db:
        db.add(JobSource(user_id=owner, provider="adzuna", board="in", company="Adzuna", enabled=True)); db.commit()
    assert client.post("/jobs/refresh").status_code == 409
    assert client.post("/automation/run").status_code == 409


def make_due(factory):
    with factory() as db:
        for row in db.query(JobRefreshRun).filter_by(status="source_state"):
            row.summary = {**row.summary, "retry_at": datetime.utcnow().isoformat()}
        db.commit()


def test_source_toggle_preserves_retry_after_and_polling_floor(isolated):
    client, _ = isolated
    source = setup_source(client)
    with patch("api.jobs.fetch_source", side_effect=SourceError("Rate limit (HTTP 429).", 7200)) as fetch:
        client.post("/jobs/refresh")
        deadline = client.get("/jobs/sources").json()[0]["retry_at"]
        for enabled in [False, True, True]:
            client.patch(f"/jobs/sources/{source['id']}", json={"enabled": enabled})
        client.post("/jobs/refresh")
        assert fetch.call_count == 1
        assert client.get("/jobs/sources").json()[0]["retry_at"] == deadline


def test_secondary_locations_match_without_overriding_country_restrictions():
    from tests.test_job_discovery import posting
    from jobs.matching import evaluate
    from jobs.schemas import SearchPreferences
    job = posting(location="London, UK", facts={"secondary_locations": [{"location": "Bengaluru, India"}]})
    assert "Location is outside your preferences." not in evaluate(job, SearchPreferences(), "Python", [])["blocked_reasons"]
    job.facts["work_mode"] = "remote"
    job.description += "\nCandidates must work from US only."
    assert any("restricted" in r for r in evaluate(job, SearchPreferences(), "", [])["blocked_reasons"])


@pytest.mark.parametrize("malformed,changed_board,repeated", [(False, False, False), (True, False, False), (False, True, False), (False, False, True)])
def test_full_traversal_closes_only_after_all_valid_pages(isolated, malformed, changed_board, repeated):
    client, factory = isolated
    source = setup_source(client)
    removed = listing("removed", apply_url="https://example.com/removed")
    first_job = listing("first", title="Graduate Backend Developer", apply_url="https://example.com/first")
    last_job = listing("last", title="Graduate Software Engineer II", apply_url="https://example.com/last")
    with patch("api.jobs.fetch_source", return_value=Snapshot([removed])):
        client.post("/jobs/refresh")
    make_due(factory)
    with patch("api.jobs.fetch_source", return_value=Snapshot([first_job], False, cursor="1", traversal_valid=not malformed, board_version="a")):
        client.post("/jobs/refresh")
    assert all(j["status"] == "open" for j in client.get("/jobs?eligibility=all").json()["items"])
    make_due(factory)
    # A failed continuation must retain the checkpoint and all existing jobs.
    with patch("api.jobs.fetch_source", side_effect=SourceError("Temporary failure")):
        client.post("/jobs/refresh")
    make_due(factory)
    with patch("api.jobs.fetch_source", return_value=Snapshot([first_job if repeated else last_job], False, scope="continuation", traversal_valid=True,
            traversal_end=True, board_version="b" if changed_board else "a")):
        client.post("/jobs/refresh")
    with factory() as db:
        statuses = {j.apply_url: j.status for j in db.query(JobPosting)}
        assert statuses[removed.apply_url] == ("open" if malformed or changed_board or repeated else "closed")
        assert statuses[first_job.apply_url] == "open"
        if not repeated: assert statuses[last_job.apply_url] == "open"


def test_smartrecruiters_final_continuation_reports_valid_end():
    from jobs.connectors import fetch_source
    detail = dict(name="Engineer", applyUrl="https://jobs.smartrecruiters.com/Example/9", location={"country": "in"},
        jobAd={"sections": {"jobDescription": {"text": DESCRIPTION}}})
    with patch("jobs.company_connectors.request_json", side_effect=[{"content": [{"id": "9"}], "totalFound": 9}, detail]):
        result = fetch_source("smartrecruiters", "Example", "Example", {"_cursor": "8"})
    assert result.traversal_end and result.traversal_valid and not result.complete and result.cursor is None
