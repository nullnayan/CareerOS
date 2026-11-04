"""Browser bridge security and import contracts; isolated DB, no remote requests."""
from datetime import datetime, timedelta
import hashlib
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db.models import (Base, ExtensionPairing, ExtensionCredential, WorkspaceSettings,
                       User, LatexMaster, LatexTailoringRun, JobPosting)
from db.session import get_db
from main import app

ORIGIN = "chrome-extension://" + "a" * 32
HEADERS = {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site", "X-CareerOS-Extension": "a" * 32}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def database():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr("services.latex_compiler.DATA_ROOT", tmp_path)
    client = TestClient(app, raise_server_exceptions=True)
    yield client, factory, tmp_path
    app.dependency_overrides.clear(); engine.dispose()


def paired(client):
    code = client.post("/autofill/pairings", json={}).json()["code"]
    response = client.post("/autofill/pair", json={"code": code}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json(), {**HEADERS, "Authorization": "Bearer " + response.json()["token"]}


def test_profile_is_explicit_and_validated(isolated):
    client, _, _ = isolated
    assert client.get("/autofill/profile").json()["email"] == ""
    response = client.put("/autofill/profile", json={"full_name": " Nayan Kumar ", "first_name": "Nayan", "email": "nayan@example.com", "github": "https://github.com/example"})
    assert response.status_code == 200 and response.json()["full_name"] == "Nayan Kumar"
    assert client.put("/autofill/profile", json={"email": "invalid"}).status_code == 422
    assert client.put("/autofill/profile", json={"portfolio": "javascript:alert(1)"}).status_code == 422
    assert client.put("/autofill/profile", json={"visa": "yes"}).status_code == 422


def test_pairing_is_single_use_and_only_hashes_are_stored(isolated):
    client, factory, _ = isolated
    code = client.post("/autofill/pairings", json={}).json()["code"]
    response = client.post("/autofill/pair", json={"code": code}, headers=HEADERS)
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    assert client.post("/autofill/pair", json={"code": code}, headers=HEADERS).status_code == 401
    with factory() as db:
        invitation = db.query(ExtensionPairing).one()
        credential = db.query(ExtensionCredential).one()
        assert invitation.code_hash == hashlib.sha256(code.encode()).hexdigest() and invitation.consumed_at
        assert credential.token_hash == hashlib.sha256((ORIGIN + "|" + token).encode()).hexdigest()
        assert token not in str(client.get("/autofill/credentials").json())


def test_pairing_expiry_and_replacement(isolated):
    client, factory, _ = isolated
    first = client.post("/autofill/pairings", json={}).json()["code"]
    second = client.post("/autofill/pairings", json={}).json()["code"]
    assert first != second
    assert client.post("/autofill/pair", json={"code": first}, headers=HEADERS).status_code == 401
    with factory() as db:
        invitation = db.query(ExtensionPairing).filter_by(code_hash=hashlib.sha256(second.encode()).hexdigest()).one()
        invitation.expires_at = datetime.utcnow() - timedelta(seconds=1); db.commit()
    assert client.post("/autofill/pair", json={"code": second}, headers=HEADERS).status_code == 401


def test_extension_origins_cannot_access_unpaired_local_apis(isolated):
    client, _, _ = isolated
    code = client.post("/autofill/pairings", json={}).json()["code"]
    assert client.post("/autofill/pair", json={"code": code}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/autofill/pair", json={"code": code}).status_code == 403
    assert client.get("/autofill/profile", headers=HEADERS).status_code == 403
    assert client.get("/jobs", headers=HEADERS).status_code == 403
    assert client.get("/autofill/extension/profile", headers=HEADERS).status_code == 401
    _, headers = paired(client)
    assert client.get("/autofill/extension/profile", headers=headers).status_code == 200
    assert client.get("/autofill/extension/profile", headers={"Authorization": headers["Authorization"]}).status_code == 403
    # Chromium's privileged GET can omit Origin: the explicit id + bound bearer
    # are required and authenticated even in that case.
    without_origin = {key: value for key, value in headers.items() if key != "Origin"}
    assert client.get("/autofill/extension/profile", headers=without_origin).status_code == 200
    wrong_extension = {**without_origin, "X-CareerOS-Extension": "b" * 32}
    assert client.get("/autofill/extension/profile", headers=wrong_extension).status_code == 401
    assert client.get("/autofill/extension/profile", headers={**headers, "Origin": "chrome-extension://" + "b" * 32}).status_code == 403


def test_credential_revocation_and_workspace_change(isolated):
    client, factory, _ = isolated
    credential, headers = paired(client)
    assert client.delete("/autofill/credentials/" + credential["credential_id"]).status_code == 200
    assert client.get("/autofill/extension/profile", headers=headers).status_code == 401
    _, headers = paired(client)
    with factory() as db:
        other = User(email="other@example.com"); db.add(other); db.flush()
        db.get(WorkspaceSettings, 1).owner_id = other.id; db.commit()
    assert client.get("/autofill/extension/profile", headers=headers).status_code == 401


def test_extension_import_preserves_full_description_gate(isolated):
    client, factory, _ = isolated
    _, headers = paired(client)
    payload = {"title": "Graduate Software Engineer", "company": "Example", "apply_url": "https://example.com/jobs/one", "description": "Graduate role using Python and FastAPI. Requirements: no prior professional experience.", "description_complete": False}
    response = client.post("/autofill/extension/import", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    identifier = response.json()["id"]
    assert not response.json()["description_complete"]
    assert client.post(f"/jobs/{identifier}/tailor").status_code == 409
    payload["description_complete"] = True
    assert client.post("/autofill/extension/import", json=payload, headers=headers).json()["id"] == identifier
    with factory() as db: assert db.query(JobPosting).count() == 1


def test_only_owned_ready_pdfs_can_be_downloaded(isolated):
    client, factory, root = isolated
    _, headers = paired(client)
    owner = client.get("/workspace").json()["id"]
    with factory() as db:
        master = LatexMaster(user_id=owner, filename="test.tex", source="test", source_hash="hash", categories=[], status="active")
        db.add(master); db.flush()
        ready = LatexTailoringRun(user_id=owner, master_id=master.id, job_description="test", label="Ready", candidates=[], status="ready")
        pending = LatexTailoringRun(user_id=owner, master_id=master.id, job_description="test", label="Pending", candidates=[], status="analyzed")
        other = User(email="other@example.com"); db.add(other); db.flush()
        foreign = LatexTailoringRun(user_id=other.id, master_id=master.id, job_description="test", label="Other", candidates=[], status="ready")
        db.add_all([ready, pending, foreign]); db.commit()
        ready_id, pending_id, foreign_id = ready.id, pending.id, foreign.id
    directory = root / "runs" / ready_id; directory.mkdir(parents=True); (directory / "resume.pdf").write_bytes(b"%PDF-test")
    assert [row["id"] for row in client.get("/autofill/extension/resumes", headers=headers).json()] == [ready_id]
    assert client.get("/autofill/extension/resumes/" + ready_id, headers=headers).content == b"%PDF-test"
    assert client.get("/autofill/extension/resumes/" + pending_id, headers=headers).status_code == 409
    assert client.get("/autofill/extension/resumes/" + foreign_id, headers=headers).status_code == 404
