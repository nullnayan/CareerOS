"""Opt-in real compiler test of discovery -> durable task -> partial draft."""
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db.models import Base, AutomationTask, ConfirmedSkill, LatexTailoringRun, LatexMaster
from db.session import get_db
from automation.service import process_one
from main import app


@pytest.mark.skipif(os.getenv("CAREEROS_TEST_LATEX") != "1", reason="Set CAREEROS_TEST_LATEX=1 for Docker PDF coverage")
def test_background_partial_pdf_and_fresh_review(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def database():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr("services.latex_compiler.DATA_ROOT", tmp_path)
    try:
        client = TestClient(app)
        source = Path(__file__).resolve().parents[2] / "scratch" / "NAYAN_KUMAR_RESUME_compile_candidate.tex"
        imported = client.post("/tailor/masters", files={"file": ("qa.tex", source.read_bytes(), "text/plain")})
        assert imported.status_code == 200, imported.text
        master_id = imported.json()["id"]
        baseline = client.post(f"/tailor/masters/{master_id}/compile")
        assert baseline.status_code == 200, baseline.text
        assert client.post(f"/tailor/masters/{master_id}/activate").status_code == 200
        owner_id = client.get("/workspace").json()["id"]
        # Confirm just one skill; another explicit requirement must stay omitted.
        category = next((c for c in imported.json()["categories"] if "tool" in c.lower()), imported.json()["categories"][0])
        with factory() as db:
            db.add(ConfirmedSkill(user_id=owner_id, canonical="kubernetes", name="Kubernetes", category=category)); db.commit()
            original = db.get(LatexMaster, master_id).source
        job = client.post("/jobs/import", json={"title": "Graduate Software Engineer", "company": "QA only", "location": "India", "apply_url": "https://example.com/qa", "description": "Required: Kubernetes, Terraform. Graduate Software Engineer, no experience required. Full time in India."}).json()
        queued = client.post(f"/automation/prepare/{job['id']}")
        assert queued.status_code == 200, queued.text
        assert process_one(factory, "qa-worker")
        task = client.get("/automation").json()["tasks"][0]
        assert task["status"] == "succeeded", task
        assert task["result"]["awaiting_confirmation"] == ["Terraform"]
        pdf = client.get(task["result"]["pdf_url"])
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        with factory() as db:
            run = db.get(LatexTailoringRun, task["result"]["run_id"])
            assert "Kubernetes" in run.source and "Terraform" not in run.source
            assert db.get(LatexMaster, master_id).source == original
            assert db.query(ConfirmedSkill).count() == 1
        fresh = client.post(f"/tailor/runs/{run.id}/reanalyze")
        assert fresh.status_code == 200 and fresh.json()["status"] == "analyzed"
        assert fresh.json()["id"] != run.id
        assert client.post(f"/automation/prepare/{job['id']}").json()["id"] == queued.json()["id"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
