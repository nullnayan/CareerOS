"""Document invariants and no-login API behavior, isolated from personal data."""
from pathlib import Path
import os
import uuid
from unittest.mock import patch as mock_patch
import pytest
import fitz
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Base, User, WorkspaceSettings, LatexMaster, LatexTailoringRun
from db.session import get_db
from core.workspace import get_workspace_owner
from tailoring.latex import category_regions, patch, plain_text, digest, escape_latex
from tailoring.selection import select, contains
from main import app

SOURCE = Path(__file__).resolve().parents[2] / "NAYAN_KUMAR_RESUME.tex"
JD = "Required: Kubernetes, Terraform, Redis, Django, AWS.\nPreferred: MongoDB, Rust.\nFresh graduate backend role."


@pytest.fixture
def source():
    return SOURCE.read_bytes().decode("utf-8")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def dependency():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = dependency
    monkeypatch.setattr("services.latex_compiler.DATA_ROOT", tmp_path)
    client = TestClient(app)
    yield client, factory, tmp_path
    app.dependency_overrides.clear()
    engine.dispose()


def test_master_mapping_and_append_only(source):
    regions = category_regions(source)
    assert list(regions) == ["Languages", "Web Development", "Databases", "Tools/Cloud", "AI/ML"]
    result, changes = patch(source, [{"name": "Terraform", "category": "Tools/Cloud"}])
    position = regions["Tools/Cloud"]["end"]
    assert result == source[:position] + ", Terraform" + source[position:]
    assert changes[0]["added"] == ["Terraform"]
    assert source == SOURCE.read_bytes().decode("utf-8")


def test_missing_skill_selection_is_grounded_and_capped(source):
    candidates, mode = select(JD, plain_text(source), list(category_regions(source)), {})
    assert mode == "local_dictionary"
    assert len(candidates) == 5
    assert [c["name"] for c in candidates] == ["Kubernetes", "Terraform", "Redis", "Django", "AWS"]
    assert all(not c["confirmed"] for c in candidates)
    assert all(contains(JD, c["name"]) for c in candidates)


def test_existing_skills_and_aliases_do_not_consume_slots(source):
    assert contains("K8s, PostgreSQL and JavaScript", "Kubernetes")
    assert not contains("JavaScript and C++", "Java")
    assert not contains("JavaScript and C++", "C")
    terms, _ = select("Required Python, JS, PostgreSQL, GDB and Terraform. Graduate engineer.", plain_text(source), list(category_regions(source)), {})
    assert [c["name"] for c in terms] == ["Terraform"]


def test_requirement_headings_rank_skills_and_ignore_benefits():
    jd = "Preferred skills:\nRust\nRequirements:\nTerraform\nBenefits:\nAWS credits and Kubernetes courses"
    terms, _ = select(jd, "", ["Languages", "Tools/Cloud"], {})
    assert [c["name"] for c in terms] == ["Terraform", "Rust"]
    assert terms[0]["importance"] == "required"


def test_duplicates_unknown_categories_and_over_limit_rejected(source):
    with pytest.raises(ValueError):
        patch(source, [{"name": "Python", "category": "Languages"}])
    with pytest.raises(ValueError):
        patch(source, [{"name": "Terraform", "category": "Made up"}])
    with pytest.raises(ValueError):
        patch(source, [{"name": "Terraform", "category": "Tools/Cloud"}] * 6)
    with pytest.raises(ValueError):
        category_regions(source.replace(r"\section{Projects}", r"\section{Skills}"))
    assert escape_latex("C# & 100%_ready") == r"C\# \& 100\%\_ready"


def test_workspace_requires_no_login_and_preserves_owner(isolated):
    client, factory, _ = isolated
    with factory() as db:
        user = User(email="existing@example.com")
        db.add(user); db.commit(); identifier = user.id
    assert client.get("/workspace").json()["id"] == identifier
    assert client.get("/workspace").json()["id"] == identifier
    assert client.post("/auth/login", json={}).status_code == 404
    assert client.post("/resumes/tailor", json={}).status_code == 410
    assert client.post("/workspace/owner", json={"owner_id": identifier}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/workspace", headers={"Host": "evil.example"}).status_code == 400


def test_multiple_existing_accounts_require_selection(isolated):
    client, factory, _ = isolated
    with factory() as db:
        db.add_all([User(email="a@example.com"), User(email="b@example.com")]); db.commit()
    assert client.get("/workspace").status_code == 409
    owners = client.get("/workspace/owners").json()
    assert len(owners) == 2
    assert client.post("/workspace/owner", json={"owner_id": owners[1]["id"]}).status_code == 200
    assert client.get("/workspace").json()["id"] == owners[1]["id"]


def test_fresh_workspace_preserves_existing_accounts(isolated):
    client, factory, _ = isolated
    with factory() as db:
        db.add_all([User(email="old-a@example.com"), User(email="old-b@example.com")]); db.commit()
    assert client.post("/workspace/owner", json={"create_new": True}).status_code == 200
    assert client.get("/workspace").json()["email"] == "personal@careeros.local"
    with factory() as db:
        assert db.query(User).count() == 3


def test_github_requires_single_use_connection_state(isolated, monkeypatch):
    client, _, _ = isolated
    from api import github
    monkeypatch.setattr(github, "GITHUB_CLIENT_ID", "test-client")
    monkeypatch.setattr(github, "GITHUB_CLIENT_SECRET", "test-secret")
    with mock_patch("api.github.exchange_code_for_token", side_effect=RuntimeError("offline test")) as exchange:
        assert client.get("/github/callback?code=code&state=unknown").status_code == 400
        exchange.assert_not_called()
        state = client.get("/github/connect").json()["state"]
        assert client.get(f"/github/callback?code=code&state={state}").status_code == 500
        assert client.get(f"/github/callback?code=code&state={state}").status_code == 400
        assert exchange.call_count == 1


def test_master_activation_requires_real_baseline(isolated, source):
    client, _, _ = isolated
    item = client.post("/tailor/masters", files={"file": ("resume.tex", source.encode(), "text/plain")}).json()
    assert item["status"] == "draft"
    assert client.post(f"/tailor/masters/{item['id']}/activate").status_code == 409
    assert client.get(f"/tailor/masters/{item['id']}/source").content == source.encode()


def test_prepare_rejects_unselected_injection(isolated, source):
    client, factory, root = isolated
    owner = client.get("/workspace").json()["id"]
    with factory() as db:
        master = LatexMaster(user_id=owner, filename="resume.tex", source=source, source_hash=digest(source), categories=list(category_regions(source)), status="active", baseline_pages=1)
        db.add(master); db.commit(); master_id = master.id
    response = client.post("/tailor/analyze", json={"master_id": master_id, "job_description": JD})
    assert response.status_code == 200
    run = response.json()
    assert len(run["candidates"]) == 5
    response = client.post(f"/tailor/runs/{run['id']}/prepare", json={"confirmed_skills": [{"canonical": "invented", "category": "Languages"}]})
    assert response.status_code == 422
    with factory() as db:
        assert db.get(LatexTailoringRun, run["id"]).source is None
        assert db.get(LatexMaster, master_id).source == source


@pytest.mark.skipif(os.getenv("CAREEROS_TEST_LATEX") != "1", reason="Set CAREEROS_TEST_LATEX=1 to exercise the Docker compiler")
def test_real_compiler_end_to_end(isolated):
    client, factory, root = isolated
    candidate = SOURCE.parent / "scratch" / "NAYAN_KUMAR_RESUME_compile_candidate.tex"
    source = candidate.read_bytes()
    imported = client.post("/tailor/masters", files={"file": ("compile-candidate.tex", source, "text/plain")})
    assert imported.status_code == 200, imported.text
    master_id = imported.json()["id"]
    baseline = client.post(f"/tailor/masters/{master_id}/compile")
    assert baseline.status_code == 200, baseline.text
    assert baseline.json()["baseline_pages"] == 1
    assert client.post(f"/tailor/masters/{master_id}/activate").status_code == 200
    analyzed = client.post("/tailor/analyze", json={"master_id": master_id, "job_description": JD, "label": "Compiler integration test"})
    assert analyzed.status_code == 200
    run = analyzed.json()
    selected = [{"canonical": c["canonical"], "category": c["category"]} for c in run["candidates"][:2]]
    prepared = client.post(f"/tailor/runs/{run['id']}/prepare", json={"confirmed_skills": selected})
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["status"] == "ready"
    assert prepared.json()["changes"], prepared.json()
    assert client.get(prepared.json()["pdf_url"]).content.startswith(b"%PDF")
    result = client.get(prepared.json()["source_url"]).content.decode()
    expected, _ = patch(source.decode(), [{"name": c["name"], "category": c["category"]} for c in run["candidates"][:2]])
    assert result == expected
    assert client.get(f"/tailor/masters/{master_id}/source").content == source
    assert client.post(f"/tailor/runs/{run['id']}/prepare", json={"confirmed_skills": []}).status_code == 409


def test_paste_matches_uploaded_source_without_changing_active_master(isolated, source):
    client, factory, _ = isolated
    uploaded = client.post("/tailor/masters", files={"file": ("original.tex", source.encode(), "text/plain")}).json()
    with factory() as db:
        db.get(LatexMaster, uploaded["id"]).status = "active"; db.commit()
    pasted = client.post("/tailor/masters/paste", data={"source": source, "filename": "edited.tex"})
    assert pasted.status_code == 200, pasted.text
    assert pasted.json()["status"] == "draft" and pasted.json()["id"] != uploaded["id"]
    assert client.get(f"/tailor/masters/{pasted.json()['id']}/source").content == source.encode()
    with factory() as db:
        assert db.get(LatexMaster, uploaded["id"]).status == "active"


def test_paste_accepts_optional_reference_pdf(isolated, source):
    client, _, _ = isolated
    with fitz.open() as pdf:
        pdf.new_page().insert_text((50, 50), "Reference resume")
        reference = pdf.tobytes()
    response = client.post("/tailor/masters/paste", data={"source": source}, files={"reference": ("reference.pdf", reference, "application/pdf")})
    assert response.status_code == 200, response.text
    assert client.get(response.json()["reference_pdf_url"]).content == reference


@pytest.mark.parametrize("data", [{"source": "   "}, {"source": "not a supported resume"}, {"source": "x" * 512001}, {"source": "text", "filename": "bad.pdf"}])
def test_paste_rejects_invalid_or_oversized_sources(isolated, data):
    client, factory, _ = isolated
    assert client.post("/tailor/masters/paste", data=data).status_code in {413, 422}
    with factory() as db: assert db.query(LatexMaster).count() == 0


def test_runaway_argument_diagnostic_identifies_source_line():
    from services.latex_compiler import compilation_failure
    error = compilation_failure("Runaway argument?\n{\\small\n./main.tex:123: Paragraph ended before \\text@command was complete.\n<to be read again> \\par\n./main.tex:123: ==> Fatal error occurred")
    assert "line 123" in str(error) and "missing argument" in str(error)
    assert "Runaway argument" in error.diagnostics
