"""Application ledger contracts, isolated from live data and external services."""
from datetime import datetime, timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from api.applications import router
from core.workspace import get_workspace_owner
from db.session import get_db
from db.models import Base, User, JobPosting, JobApplication, ApplicationEvent, LatexMaster, LatexTailoringRun


@pytest.fixture
def ledger():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        owner = User(email="qa@example.com"); other = User(email="other@example.com")
        db.add_all([owner, other]); db.flush()
        job = JobPosting(user_id=owner.id, identity_key="one", title="Graduate Engineer", company="Example", location="India", apply_url="https://example.com/job/one", description="Required Python, Docker and SQL.", description_hash="hash", description_complete=True, facts={})
        foreign = JobPosting(user_id=other.id, identity_key="two", title="Other job", company="Other", location="India", apply_url="https://example.com/job/two", description="Other", description_hash="other", description_complete=True, facts={})
        db.add_all([job, foreign]); db.commit()
    app = FastAPI(); app.include_router(router)
    def database():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_workspace_owner] = lambda: owner
    yield TestClient(app), factory, owner, other, job, foreign
    engine.dispose()


def test_create_is_idempotent_and_never_marks_applied(ledger):
    client, factory, _, _, job, _ = ledger
    first = client.post("/applications", json={"job_id": job.id})
    second = client.post("/applications", json={"job_id": job.id})
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == "planned" and first.json()["applied_at"] is None
    with factory() as db:
        assert db.query(JobApplication).count() == db.query(ApplicationEvent).count() == 1


def test_marking_applied_requires_explicit_confirmation(ledger):
    client, factory, _, _, job, _ = ledger
    row = client.post("/applications", json={"job_id": job.id}).json()
    assert client.patch(f"/applications/{row['id']}", json={"status": "applied"}).status_code == 409
    with factory() as db: assert db.query(JobApplication).one().status == "planned"
    updated = client.patch(f"/applications/{row['id']}", json={"status": "applied", "confirmed_submitted": True}).json()
    assert updated["status"] == "applied" and updated["applied_at"]
    assert len(updated["history"]) == 2 and updated["history"][-1]["detail"]["submission_confirmed"]


def test_notes_and_status_history_is_append_only_and_noops_are_ignored(ledger):
    client, factory, _, _, job, _ = ledger
    row = client.post("/applications", json={"job_id": job.id}).json(); url = f"/applications/{row['id']}"
    client.patch(url, json={"notes": "Interview preparation", "status": "interview", "next_action_at": "2026-11-03T09:00:00+05:30"})
    result = client.patch(url, json={"notes": "Interview preparation", "status": "interview"}).json()
    assert result["next_action_at"] == "2026-11-03T03:30:00"
    assert result["status"] == "interview" and result["applied_at"] is None
    assert len(result["history"]) == 2
    assert result["history"][0]["event_type"] == "created"
    assert client.delete(url).status_code == 405
    with factory() as db: assert db.query(ApplicationEvent).count() == 2


def test_application_ownership_is_enforced(ledger):
    client, factory, _, other, job, foreign = ledger
    assert client.post("/applications", json={"job_id": foreign.id}).status_code == 404
    with factory() as db:
        row = JobApplication(user_id=other.id, job_id=foreign.id, notes="Private", status="planned")
        db.add(row); db.commit(); identifier = row.id
    assert client.get(f"/applications/{identifier}").status_code == 404
    assert client.patch(f"/applications/{identifier}", json={"notes": "changed"}).status_code == 404
    assert client.get("/applications").json()["items"] == []


def test_resume_must_be_owned_ready_and_match_job_description(ledger):
    client, factory, owner, other, job, _ = ledger
    with factory() as db:
        master = LatexMaster(user_id=owner.id, filename="qa.tex", source="qa", source_hash="master", categories=[], status="active")
        db.add(master); db.flush()
        runs = [LatexTailoringRun(user_id=user, master_id=master.id, job_description=description, label="QA", candidates=[], status=status)
                for user, description, status in [(owner.id, job.description, "ready"), (owner.id, "Different JD", "ready"), (owner.id, job.description, "analyzed"), (other.id, job.description, "ready")]]
        db.add_all(runs); db.commit()
    for run in runs[1:]:
        assert client.post("/applications", json={"job_id": job.id, "tailoring_run_id": run.id}).status_code in (409, 422)
    row = client.post("/applications", json={"job_id": job.id, "tailoring_run_id": runs[0].id}).json()
    assert row["resume_pdf_url"].endswith(f"/{runs[0].id}/pdf")
    result = client.patch(f"/applications/{row['id']}", json={"tailoring_run_id": None}).json()
    assert result["tailoring_run_id"] is None


def test_date_and_status_validation(ledger):
    client, _, _, _, job, _ = ledger
    row = client.post("/applications", json={"job_id": job.id}).json(); url = f"/applications/{row['id']}"
    assert client.patch(url, json={"status": "unknown"}).status_code == 422
    assert client.patch(url, json={"status": None}).status_code == 422
    assert client.patch(url, json={"notes": None}).status_code == 422
    assert client.patch(url, json={"applied_at": "2026-01-01T00:00:00Z"}).status_code == 409
    future = (datetime.utcnow() + timedelta(days=365)).isoformat()
    assert client.patch(url, json={"applied_at": future, "confirmed_submitted": True}).status_code == 422


def test_search_and_status_counts(ledger):
    client, _, _, _, job, _ = ledger
    row = client.post("/applications", json={"job_id": job.id}).json()
    client.patch(f"/applications/{row['id']}", json={"status": "offer"})
    result = client.get("/applications?status=offer&q=example").json()
    assert result["total"] == result["counts"]["offer"] == 1
    assert client.get("/applications?status=planned").json()["total"] == 0
    assert client.get("/applications?status=invalid").status_code == 422
