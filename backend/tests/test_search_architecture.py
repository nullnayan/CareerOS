"""Explicit-search, feed transport and connection lifecycle regression gates."""
import io
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import pytest
from tests.test_job_discovery import isolated, setup_source, listing, DESCRIPTION
from db.models import (JobPosting, JobMatch, JobSource, JobSearchPreferences, JobRefreshRun,
    JobApplication, LatexMaster, AutomationSettings, AutomationTask, User)
from jobs.connectors import Snapshot, SourceError
from jobs.structured_feeds import parse_feed
from jobs.feed_transport import feed_url, public_addresses, fetch_public_feed
from jobs.salary import salary_facts


def rss():
    return f'<rss version="2.0"><channel><title>Employer jobs</title><item><guid>one</guid><title>Graduate Software Engineer</title><link>https://example.com/one</link><description>{DESCRIPTION}</description><pubDate>Mon, 02 Nov 2026 00:00:00 GMT</pubDate></item></channel></rss>'.encode()


@pytest.mark.parametrize("body", [rss(),
    f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>one</id><title>Graduate Engineer</title><link href="https://example.com/one"/><content>{DESCRIPTION}</content></entry></feed>'.encode(),
    f'<jobs><job><id>one</id><title>Graduate Engineer</title><url>https://example.com/one</url><description>{DESCRIPTION}</description></job></jobs>'.encode(),
    json.dumps({"jobs": [{"id": "one", "title": "Graduate Engineer", "url": "https://example.com/one", "description": DESCRIPTION}]}).encode(),
    ('<html><script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@type": "JobPosting", "title": "Graduate Engineer", "url": "https://example.com/one", "description": DESCRIPTION, "jobLocation": {"address": {"addressLocality": "Bengaluru", "addressCountry": "India"}}}) + '</script></html>').encode()])
def test_feed_formats_are_normalized_without_closing_missing_jobs(body):
    result = parse_feed(body, "Employer", {})
    assert len(result.jobs) == 1 and not result.complete and result.scope == "rolling_feed"
    assert not result.jobs[0].complete
    assert parse_feed(body, "Employer", {"full_descriptions": True}).jobs[0].complete


def test_feed_checkpoint_restarts_safely_on_changes_and_rejects_entities():
    body = json.dumps({"jobs": [{"id": str(i), "title": "Engineer", "url": f"https://example.com/{i}", "description": DESCRIPTION} for i in range(3)]}).encode()
    first = parse_feed(body, "Employer", {}, budget=2)
    last = parse_feed(body, "Employer", {}, cursor=first.cursor, budget=2)
    assert len(first.jobs) == 2 and len(last.jobs) == 1 and not last.cursor
    changed = parse_feed(body + b" ", "Employer", {}, cursor=first.cursor, budget=2)
    assert changed.warnings and changed.jobs[0].native_id == "0"
    with pytest.raises(SourceError): parse_feed(b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss/>', "Employer", {})


@pytest.mark.parametrize("url", ["https://localhost/feed", "https://127.0.0.1/feed", "http://example.com/feed", "https://example.com:8443/feed", "https://a:b@example.com/feed", "https://example.com/feed?api_key=secret"])
def test_feed_setup_rejects_private_or_credentialed_urls(url):
    with pytest.raises(ValueError): feed_url(url)


def test_dns_rebinding_and_redirects_do_not_reach_private_destinations():
    with patch("jobs.feed_transport.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
        with pytest.raises(SourceError): public_addresses("public.example.com")
    connection = MagicMock()
    connection.getresponse.return_value.status = 302
    with patch("jobs.feed_transport.public_addresses", return_value=["8.8.8.8"]), patch("jobs.feed_transport.PinnedHTTPS", return_value=connection):
        with pytest.raises(SourceError, match="redirect"): fetch_public_feed("https://example.com/feed")
        connection.close.assert_called_once()


def test_free_connections_are_idempotent_and_preserve_disabled_sources(isolated):
    client, factory = isolated
    original = client.post("/jobs/sources", json={"provider": "greenhouse", "board": "canonical", "company": "Canonical", "enabled": False}).json()
    result = client.post("/jobs/connections/free").json()
    assert result["added"]
    assert client.post("/jobs/connections/free").json()["added"] == []
    source = next(s for s in client.get("/jobs/sources").json() if s["id"] == original["id"])
    assert source["enabled"] is False
    connections = client.get("/jobs/connections").json()["platforms"]
    assert len(connections) == 45
    assert next(c for c in connections if c["name"] == "LinkedIn")["collects_automatically"] is False
    assert next(c for c in connections if c["name"] == "Workday")["connection_state"] == "feed_required"
    with factory() as db:
        assert db.query(JobPosting).count() == db.query(AutomationTask).count() == 0


def test_feed_configuration_survives_ingestion_and_checkpoint_updates(isolated):
    client, _ = isolated
    client.put("/jobs/preferences", json={})
    data = {"company": "Employer", "feed_url": "https://example.com/jobs.xml", "full_descriptions": True}
    first = client.post("/jobs/sources/feed", json=data).json()
    assert client.post("/jobs/sources/feed", json=data).json()["id"] == first["id"]
    with patch("jobs.structured_feeds.fetch_public_feed", return_value=rss()):
        result = client.post("/jobs/refresh").json()
    assert not result["errors"]
    assert client.get("/jobs/sources").json()[0]["configuration"]["feed_url"] == data["feed_url"]
    assert client.get("/jobs?eligibility=all").json()["total"] == 1


@pytest.mark.parametrize("text,expected", [("Salary: 6-10 LPA", 600000), ("CTC: INR 6,00,000 - 10,00,000 per annum", 600000),
    ("Salary: Rs 60,000 per month", 720000), ("Salary: up to 12 LPA", None), ("Project budget INR 12,00,000 per year", None), ("Salary: USD 100000 per year", None)])
def test_salary_normalization_does_not_invent_guaranteed_pay(text, expected):
    assert salary_facts(text, {}).get("annual_salary_min_inr") == expected


def active_master(db, owner):
    master = LatexMaster(user_id=owner, filename="master.tex", source="B.Tech Computer Science Python FastAPI PostgreSQL Docker", source_hash="a" * 64, categories={}, status="active")
    db.add(master); db.commit()
    return master


def test_explicit_search_runs_only_on_worker_and_does_not_prepare_pdfs(isolated):
    client, factory = isolated
    setup_source(client)
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing()])) as fetch:
        # Page data reads never discover. Search queues work; the worker fetches.
        client.get("/jobs?eligibility=all")
        assert fetch.call_count == 0
        started = client.post("/jobs/search").json()
        assert fetch.call_count == 0
        assert client.post("/jobs/search").json()["search_id"] == started["search_id"]
        from automation.service import process_one
        assert process_one(factory, "search-test")
        assert fetch.call_count == 1
    assert client.get("/jobs/search/" + started["search_id"]).json()["status"] == "completed"
    with factory() as db: assert db.query(AutomationTask).filter_by(kind="prepare").count() == 0


def test_clear_deletes_listings_preserves_applications_and_pauses_discovery(isolated):
    client, factory = isolated
    setup_source(client)
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing("one"), listing("two", title="Backend Developer", apply_url="https://example.com/two")])):
        client.post("/jobs/refresh")
    with factory() as db:
        owner = db.query(JobSource).one().user_id
        job = db.query(JobPosting).order_by(JobPosting.id).first()
        db.add(JobApplication(user_id=owner, job_id=job.id, status="planned"))
        db.add(AutomationSettings(user_id=owner, data={"enabled": True}))
        master = active_master(db, owner)
        master_id = master.id
    result = client.post("/jobs/clear").json()
    assert result["cleared"] == 2 and result["deleted"] == result["retained_for_applications"] == 1
    assert client.get("/jobs?eligibility=all").json()["items"] == []
    assert client.post("/jobs/refresh").status_code == 409
    with factory() as db:
        assert db.get(LatexMaster, master_id).status == "active"
        assert db.query(JobApplication).count() == 1
        assert db.query(JobPosting).one().status == "cleared"
        assert db.get(AutomationSettings, owner).data["enabled"] is False
    assert client.post("/jobs/search").status_code == 200


def test_results_require_known_minimum_and_rank_wfh_then_salary(isolated):
    client, factory = isolated
    setup_source(client)
    with factory() as db: active_master(db, db.query(JobSource).one().user_id)
    records = []
    for native, mode, low, high in [("remote-high", "remote", 800000, 1000000), ("remote-low", "remote", 600000, 900000),
        ("hybrid", "hybrid", 1200000, 1500000), ("onsite", "onsite", 2000000, 3000000),
        ("too-low", "remote", 550000, 1200000), ("upper-only", "remote", None, 2000000)]:
        records.append(listing(native, title="Graduate Software Engineer " + native, apply_url=f"https://example.com/{native}",
            facts={"work_mode": mode, "salary_min": low, "salary_max": high, "salary_currency": "INR", "salary_period": "annual"}))
    records.append(listing("weak", title="Graduate Software Engineer weak", apply_url="https://example.com/weak", description="Graduate Software Engineer. No experience required. We require Java, Scala and C++ programming skills to build production services.",
        facts={"work_mode": "remote", "salary_min": 900000, "salary_max": 2000000, "salary_currency": "INR", "salary_period": "annual"}))
    with patch("api.jobs.fetch_source", return_value=Snapshot(records)): client.post("/jobs/refresh")
    query = "/jobs?minimum_score=60&salary_floor=550000&sort=best&include_unverified_salary=false"
    result = client.get(query).json()
    assert [j["title"].split()[-1] for j in result["items"]] == ["weak", "remote-high", "remote-low", "hybrid", "onsite"]
    assert all("relevance_score" not in j["assessment"] for j in result["items"])
    assert client.get(query + "&work_mode=remote").json()["total"] == 3
    assert client.get(query.replace("sort=best", "sort=salary_desc")).json()["items"][0]["title"].endswith("onsite")
    assert client.get(query.replace("sort=best", "sort=onsite_first")).json()["items"][0]["title"].endswith("onsite")
    client.put("/jobs/preferences", json={"graduation_year": 2027, "minimum_salary_annual_inr": 1000000})
    assert client.get(query).json()["total"] == 5  # Per-search controls can override the saved default.
    assert client.get(query.replace("salary_floor=550000", "salary_floor=1000000")).json()["total"] == 2
    flexible = query.replace("include_unverified_salary=false", "include_unverified_salary=true")
    result = client.get(flexible).json()
    assert result["total"] == 6 and result["diagnostics"]["salary_unverified_matches"] == 1
    assert any(j["title"].endswith("upper-only") for j in result["items"])
    assert client.get(flexible.replace("minimum_score=60", "minimum_score=50")).json()["total"] == 6
    assert client.get(flexible.replace("minimum_score=60", "minimum_score=40")).json()["total"] == 6
    assert client.get(flexible.replace("minimum_score=60", "minimum_score=0").replace("salary_floor=550000", "salary_floor=0")).json()["total"] == 7


def test_search_with_unvisited_ready_sources_cannot_report_completed(isolated):
    client, factory = isolated
    setup_source(client)
    started = client.post("/jobs/search").json()
    with factory() as db:
        task = db.query(AutomationTask).one()
        source = db.query(JobSource).one()
        task.status = "succeeded"
        task.result = {"sources": [], "deferred": [{"source_id": source.id, "company": source.company, "ready": True}]}
        db.commit()
    result = client.get("/jobs/search/" + started["search_id"]).json()
    assert result["status"] == "incomplete"
    assert result["coverage"]["checked_sources"] == 0 and result["coverage"]["enabled_sources"] == 1


def test_paused_catalogue_does_not_reassess_stale_jobs(isolated):
    from jobs.search_control import set_control
    client, factory = isolated
    setup_source(client)
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing()])): client.post("/jobs/refresh")
    with factory() as db:
        source = db.query(JobSource).one()
        set_control(db, source.user_id, {"paused": True})
        db.query(JobMatch).one().assessment = {}
        db.commit()
    with patch("api.jobs.assess", side_effect=AssertionError("Paused searches must skip assessment")):
        result = client.get("/jobs").json()
    assert result["paused"] and result["items"] == [] and result["stored"] == 1


def test_stale_assessment_loads_matches_in_bulk_instead_of_one_lookup_per_job(isolated):
    from sqlalchemy import event
    client, factory = isolated
    setup_source(client)
    records = [listing(str(i), title=f"Graduate Software Engineer {i}", apply_url=f"https://example.com/{i}") for i in range(60)]
    with patch("api.jobs.fetch_source", return_value=Snapshot(records)): client.post("/jobs/refresh")
    with factory() as db:
        for match in db.query(JobMatch): match.assessment = {**match.assessment, "evidence_version": "old"}
        db.commit()
    selects = []
    engine = factory.kw["bind"]
    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lower().lstrip().startswith("select") and "from job_matches" in statement.lower(): selects.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try: result = client.get("/jobs?eligibility=all").json()
    finally: event.remove(engine, "before_cursor_execute", capture)
    assert result["total"] == 60 and not selects


def test_explicit_search_continues_partial_batches_while_recurring_automation_is_off(isolated):
    from automation.service import process_one
    client, factory = isolated
    setup_source(client)
    search = client.post("/jobs/search").json()
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing()], False, cursor="next")):
        assert process_one(factory, "search-test")
    with factory() as db:
        queued = db.query(AutomationTask).filter_by(status="queued").one()
        assert queued.payload["search_id"] == search["search_id"] and queued.payload["automatic"] is False
        assert queued.payload["search_only"] is True
    assert client.get("/jobs/search/" + search["search_id"]).json()["pending"] == 1
    client.post("/jobs/clear")
    assert client.get("/jobs/search/" + search["search_id"]).json()["pending"] == 0


def test_clear_during_network_work_cannot_repopulate_the_catalogue(isolated):
    client, factory = isolated
    setup_source(client)
    def interrupted(*args):
        client.post("/jobs/clear")
        return Snapshot([listing()])
    with patch("api.jobs.fetch_source", side_effect=interrupted):
        result = client.post("/jobs/refresh").json()
    assert result["new"] == 0
    with factory() as db: assert db.query(JobPosting).count() == 0


def test_structured_job_salary_and_country_restrictions_are_retained():
    from jobs.matching import evaluate
    from jobs.schemas import SearchPreferences
    from tests.test_job_discovery import posting
    body = json.dumps({"@type": "JobPosting", "title": "Graduate Engineer", "url": "https://example.com/one", "description": DESCRIPTION,
        "jobLocationType": "TELECOMMUTE", "applicantLocationRequirements": {"name": "United States"},
        "baseSalary": {"currency": "INR", "value": {"unitText": "YEAR", "minValue": 800000, "maxValue": 1000000}}}).encode()
    record = parse_feed(body, "Employer", {}).jobs[0]
    assert salary_facts(record.description, record.facts)["annual_salary_min_inr"] == 800000
    assessed = evaluate(posting(facts=record.facts), SearchPreferences(), "B.Tech Computer Science Python", [])
    assert any("applicant-country" in reason for reason in assessed["blocked_reasons"])


def test_ashby_requests_and_normalizes_published_compensation():
    from jobs.company_connectors import ashby
    item = {"title": "Graduate Software Engineer", "location": "India", "jobUrl": "https://jobs.ashbyhq.com/example/one", "descriptionPlain": DESCRIPTION,
        "compensation": {"summaryComponents": [{"compensationType": "Salary", "currencyCode": "INR", "interval": "1 YEAR", "minValue": 800000, "maxValue": 1000000}]}}
    with patch("jobs.company_connectors.request_json", return_value={"jobs": [item]}) as request:
        result = ashby("example", "Example")
    assert request.call_args.args[1] == {"includeCompensation": "true"}
    assert salary_facts(result.jobs[0].description, result.jobs[0].facts)["annual_salary_min_inr"] == 800000
