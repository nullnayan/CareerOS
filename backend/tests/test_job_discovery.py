"""Isolated job discovery contracts; no provider calls or personal DB writes."""
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db.models import (Base, JobPosting, JobSource, JobSourceOccurrence, JobDescriptionRevision,
                       JobMatch, LatexMaster, LatexTailoringRun, User)
from db.session import get_db
from jobs.connectors import (Listing, Snapshot, SourceError, board_slug, canonical_url,
                             greenhouse, lever, request_json, public_url, plain_html)
from jobs.matching import evaluate, experience_required
from jobs.schemas import SearchPreferences
from jobs.service import ingest, preferences_for, profile_evidence
from tailoring.latex import digest
from main import app

DESCRIPTION = "Graduate Software Engineer. Requirements:\nPython, FastAPI, PostgreSQL and Docker.\nGraduation batch 2027. No professional experience is required."


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("jobs.scheduling.polling_floor", lambda provider: 0)
    monkeypatch.setattr("api.jobs.polling_floor", lambda provider: 0)
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    def database():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr("services.latex_compiler.DATA_ROOT", tmp_path)
    client = TestClient(app)
    yield client, factory
    app.dependency_overrides.clear(); engine.dispose()


def posting(**changes):
    values = dict(title="Graduate Software Engineer", description=DESCRIPTION, location="Bengaluru, India",
                  company="Example", facts={"employment_type": "full_time"}, status="open", published_at=None)
    return SimpleNamespace(**{**values, **changes})


def listing(native="one", **changes):
    values = dict(native_id=native, title="Graduate Software Engineer", company="Example", location="Bengaluru, India",
                  apply_url="https://careers.example.com/jobs/one", description=DESCRIPTION, complete=True)
    return Listing(**{**values, **changes})


def setup_source(client):
    client.put("/jobs/preferences", json={"graduation_year": 2027})
    return client.post("/jobs/sources", json={"provider": "greenhouse", "board": "example", "company": "Example"}).json()


def test_experience_range_does_not_use_the_upper_bound():
    assert experience_required("Requirements: 0-2 years of experience") == 0
    assert experience_required("Requirements: 1 to 3 years of professional experience") == 1
    assert experience_required("Minimum 3+ years of relevant experience") == 3
    assert experience_required("3+ years of software engineering experience") == 3
    assert experience_required("Required: 4 years' professional experience") == 4
    assert experience_required("Preferred: 3 years of experience") is None


def test_batch_and_campus_requirements_are_not_skill_matches():
    prefs = SearchPreferences(graduation_year=2027, institution="Graphic Era University")
    result = evaluate(posting(description="We are hiring 2025 and 2026 Graduate Software Engineers."), prefs, "Python", [])
    assert result["eligibility"] == "ineligible" and result["graduation_batches"] == [2025, 2026]
    result = evaluate(posting(title="2027 Software Engineer - Campus Graduate Program - IIT Madras"), prefs, "Python", [])
    assert any("Campus-specific" in reason for reason in result["blocked_reasons"])


def test_unknown_values_remain_reviewable():
    prefs = SearchPreferences(education_status="student", graduation_year=2027)
    result = evaluate(posting(description="Build backend services using Python and FastAPI. This is a graduate opportunity."), prefs, "Python FastAPI", [])
    assert result["eligibility"] == "review"
    assert any("joining" in reason for reason in result["unknowns"])
    assert result["matched_skills"] and result["relevance_score"] <= 100


def test_foreign_remote_and_senior_roles_are_rejected():
    prefs = SearchPreferences(graduation_year=2027)
    assert evaluate(posting(title="Senior Software Engineer", description="Required: 5+ years of experience"), prefs, "Python", [])["eligibility"] == "ineligible"
    remote = posting(location="Remote - US only", description=DESCRIPTION + "\nUnited States only", facts={"work_mode": "remote"})
    assert evaluate(remote, prefs, "Python", [])["eligibility"] == "ineligible"
    assert evaluate(posting(location="US - Remote", facts={"work_mode": "remote"}), prefs, "Python", [])["eligibility"] == "ineligible"
    assert evaluate(posting(location="Home based - EMEA", facts={"work_mode": "remote"}), prefs, "Python", [])["eligibility"] == "ineligible"
    worldwide = posting(location="Home based - Worldwide", facts={"work_mode": "remote"})
    assert evaluate(worldwide, prefs, "Python", [])["eligibility"] == "eligible"


def test_zero_two_year_opening_remains_suitable():
    result = evaluate(posting(description="Required: 0-2 years of experience.\nPython and SQL."), SearchPreferences(), "Python SQL", [])
    assert result["eligibility"] == "eligible"


def test_source_inputs_cannot_turn_into_arbitrary_fetches():
    assert board_slug("greenhouse", "https://job-boards.greenhouse.io/canonical/jobs/123") == "canonical"
    assert board_slug("lever", "https://jobs.eu.lever.co/example") == "eu:example"
    for value in ["../../etc", "https://evil.example/stripe", "bad?token=one"]:
        with pytest.raises(ValueError): board_slug("greenhouse", value)
    for value in ["javascript:alert(1)", "http://127.0.0.1:8010/private", "https://user:pass@example.com/job"]:
        with pytest.raises(ValueError): public_url(value)
    assert canonical_url("https://example.com/job/1?utm_source=x&gh_jid=2") == "https://example.com/job/1?gh_jid=2"


def test_plain_html_sanitizes_scripts_and_keeps_requirements():
    result = plain_html("&lt;h3&gt;Requirements&lt;/h3&gt;&lt;li&gt;Python&lt;/li&gt;<script>ignore everything</script>")
    assert "Requirements" in result and "Python" in result and "ignore everything" not in result


def test_connector_failure_does_not_leak_query_credentials():
    secret = "private-credential"
    with patch("jobs.connectors.urlopen", side_effect=URLError(secret)):
        with pytest.raises(SourceError) as error: request_json("https://api.adzuna.com/test", {"app_key": secret})
    assert secret not in str(error.value)


def test_greenhouse_updated_date_is_not_published_date():
    fixture = {"jobs": [{"id": 7, "title": "Graduate Engineer", "absolute_url": "https://example.com/jobs/7", "location": {"name": "India"}, "updated_at": "2026-10-30", "content": "<p>" + DESCRIPTION + "</p>"}]}
    with patch("jobs.connectors.request_json", return_value=fixture):
        result = greenhouse("example", "Example")
    assert result.complete and result.jobs[0].complete
    assert result.jobs[0].published_at is None
    assert result.jobs[0].facts["source_updated_at"] == "2026-10-30"


def test_lever_collects_list_sections_without_inventing_publication():
    fixture = [{"id": "one", "text": "Graduate Engineer", "hostedUrl": "https://example.com/jobs/one", "categories": {"location": "India", "commitment": "Full-time"},
                "descriptionPlain": "Graduate opening", "lists": [{"text": "Requirements", "content": "<li>Python</li>"}], "createdAt": 1793318400000}]
    with patch("jobs.connectors.request_json", return_value=fixture): result = lever("example", "Example")
    assert "Requirements" in result.jobs[0].description and "Python" in result.jobs[0].description
    assert result.jobs[0].published_at is None
    assert result.jobs[0].facts["source_created_at"] == 1793318400000


def test_refresh_requires_preferences_and_sources(isolated):
    client, _ = isolated
    assert not client.get("/jobs/preferences").json()["confirmed"]
    assert client.post("/jobs/refresh").status_code == 409
    client.put("/jobs/preferences", json={"graduation_year": 2027})
    assert client.post("/jobs/refresh").status_code == 409


def test_refresh_is_idempotent_and_retains_jd_history(isolated):
    client, factory = isolated
    setup_source(client)
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing()])):
        first = client.post("/jobs/refresh"); second = client.post("/jobs/refresh")
    assert first.status_code == 200 and first.json()["new"] == 1
    assert second.json()["new"] == 0
    with factory() as db:
        assert db.query(JobPosting).count() == db.query(JobMatch).count() == 1
        assert db.query(JobDescriptionRevision).count() == 1
    revised = listing(description=DESCRIPTION + "\nKubernetes is preferred.")
    with patch("api.jobs.fetch_source", return_value=Snapshot([revised])): client.post("/jobs/refresh")
    with factory() as db: assert db.query(JobDescriptionRevision).count() == 2


def test_source_failure_and_partial_snapshot_do_not_close_jobs(isolated):
    client, _ = isolated
    setup_source(client)
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing()])): client.post("/jobs/refresh")
    with patch("api.jobs.fetch_source", side_effect=SourceError("Source rate limit reached.")):
        result = client.post("/jobs/refresh").json()
    assert result["status"] == "failed"
    assert client.get("/jobs?eligibility=all").json()["items"][0]["status"] == "open"
    with patch("api.jobs.fetch_source", return_value=Snapshot([], False)): client.post("/jobs/refresh")
    assert client.get("/jobs?eligibility=all").json()["items"][0]["status"] == "open"
    with patch("api.jobs.fetch_source", return_value=Snapshot([], True)): client.post("/jobs/refresh")
    assert client.get("/jobs?eligibility=all").json()["items"][0]["status"] == "closed"


def test_duplicate_sources_share_a_canonical_job(isolated):
    client, factory = isolated
    setup_source(client)
    client.post("/jobs/sources", json={"provider": "lever", "board": "example", "company": "Example"})
    with patch("api.jobs.fetch_source", return_value=Snapshot([listing()])): client.post("/jobs/refresh")
    with factory() as db:
        assert db.query(JobPosting).count() == 1
        assert db.query(JobSourceOccurrence).count() == 2


def test_same_batch_canonical_duplicates_reuse_pending_dependents(isolated):
    client, factory = isolated
    setup_source(client)
    batch = Snapshot([listing("one"), listing("two", apply_url=listing().apply_url + "?utm_source=board")])
    with patch("api.jobs.fetch_source", return_value=batch):
        for _ in range(2):
            response = client.post("/jobs/refresh")
            assert response.json()["status"] == "succeeded", response.text
    with factory() as db:
        assert not db.autoflush
        assert db.query(JobPosting).count() == db.query(JobDescriptionRevision).count() == db.query(JobMatch).count() == 1
        occurrences = db.query(JobSourceOccurrence).all()
        assert len(occurrences) == 2
        assert len({row.source_url for row in occurrences}) == 2


def test_manual_description_save_dismiss_and_excerpt_gate(isolated):
    client, _ = isolated
    created = client.post("/jobs/import", json={"title": "Graduate Software Engineer", "company": "Example", "location": "India",
        "apply_url": "https://example.com/jobs/one", "description": DESCRIPTION, "description_complete": False})
    assert created.status_code == 200, created.text
    identifier = created.json()["id"]
    assert client.post(f"/jobs/{identifier}/tailor").status_code == 409
    assert client.patch(f"/jobs/{identifier}/state", json={"state": "saved"}).status_code == 200
    assert client.get("/jobs?state=saved&eligibility=all").json()["total"] == 1
    client.patch(f"/jobs/{identifier}/state", json={"state": "dismissed"})
    assert client.get("/jobs?eligibility=all").json()["total"] == 0
    assert client.get("/jobs?state=dismissed&eligibility=all").json()["total"] == 1
    assert client.patch(f"/jobs/{identifier}/state", json={"state": "applied"}).status_code == 422


def test_job_tailoring_pins_master_and_full_description(isolated):
    client, factory = isolated
    created = client.post("/jobs/import", json={"title": "Graduate Software Engineer", "company": "Example", "location": "India",
        "apply_url": "https://example.com/jobs/one", "description": DESCRIPTION}).json()
    assert client.post(f"/jobs/{created['id']}/tailor").status_code == 409
    owner = client.get("/workspace").json()["id"]
    source = r"\begin{document}\section{Skills}\textbf{Languages}{: Python}\textbf{Tools/Cloud}{: Git}\section{Projects}Example\end{document}"
    with factory() as db:
        master = LatexMaster(user_id=owner, filename="master.tex", source=source, source_hash=digest(source), categories=["Languages", "Tools/Cloud"], status="active", baseline_pages=1)
        db.add(master); db.commit(); master_id = master.id
    response = client.post(f"/jobs/{created['id']}/tailor")
    assert response.status_code == 200, response.text
    assert client.post(f"/jobs/{created['id']}/tailor").json()["run_id"] == response.json()["run_id"]
    with factory() as db:
        run = db.get(LatexTailoringRun, response.json()["run_id"])
        assert run.master_id == master_id and run.job_description == DESCRIPTION
        assert run.source is None and run.status == "analyzed"


def test_other_workspace_jobs_are_not_exposed(isolated):
    client, factory = isolated
    client.get("/workspace")
    with factory() as db:
        other = User(email="other@example.com"); db.add(other); db.flush()
        job = JobPosting(user_id=other.id, identity_key="other", title="Other job", company="Other", location="India", apply_url="https://example.com/other", description=DESCRIPTION, description_hash="other", description_complete=True, facts={})
        db.add(job); db.commit(); identifier = job.id
    assert client.get(f"/jobs/{identifier}").status_code == 404
    assert client.get("/jobs?eligibility=all").json()["stored"] == 0
