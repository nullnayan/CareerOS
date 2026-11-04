"""Full-source syntax repair and single compile API; all providers mocked."""
from io import BytesIO
import json
from unittest.mock import Mock, patch
import zipfile
import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db.models import Base, LatexMaster
from db.session import get_db
from main import app, _rate_store
from tailoring.ai_repair import corrected_source, repair
from services.latex_compiler import CompileError
from agents.llm_client import GroqRateLimitError

SOURCE = r"\documentclass{article}\begin{document}\section{Skills}\textbf{Languages}{: Python, C++}\section{Projects}\badbold{Nayan Kumar} built 3 services.\end{document}"


def response(old=r"\badbold{", new=r"\textbf{"):
    return SOURCE.replace(old, new)


def compile_stub(source, destination):
    if r"\badbold" in source:
        raise CompileError("Undefined control sequence.", "./main.tex:1: Undefined control sequence. \\badbold")
    if r"\textit{" in source:
        raise CompileError("First correction still fails.", "./main.tex:2: Error: \\textit remains invalid in this fixture")
    with fitz.open() as pdf:
        pdf.new_page().insert_text((50, 50), "Nayan Kumar built 3 services.")
        pdf.save(destination)
    return {"pages": 1, "text": "Nayan Kumar built 3 services.", "overflow": False, "has_errors": False, "diagnostics": "Valid syntax"}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def database():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr("services.latex_compiler.DATA_ROOT", tmp_path)
    _rate_store.clear()
    yield TestClient(app), factory, tmp_path
    app.dependency_overrides.clear(); _rate_store.clear(); engine.dispose()


def test_valid_source_never_calls_groq(tmp_path):
    with patch("tailoring.ai_repair.LLMClient") as client:
        report, candidate, _ = repair(SOURCE.replace(r"\badbold", r"\textbf"), compile_stub, tmp_path)
    assert report["status"] == "not_needed" and candidate is None
    client.assert_not_called()


def test_success_requires_minimal_preserved_text_and_real_compilation(tmp_path):
    with patch("tailoring.ai_repair.LLMClient") as client:
        client.return_value.generate.return_value = response()
        report, candidate, info = repair(SOURCE, compile_stub, tmp_path)
    assert report["status"] == "repaired" and len(report["attempts"]) == 1
    assert candidate == SOURCE.replace(r"\badbold", r"\textbf") + "\n" and info["pages"] == 1
    assert "original.tex" in report["diff"] and "ai-repaired.tex" in report["diff"]
    assert (tmp_path / "candidate.pdf").read_bytes().startswith(b"%PDF")
    client.assert_called_once_with("latex_repair")


def test_second_attempt_uses_latest_error_and_no_third_attempt(tmp_path):
    with patch("tailoring.ai_repair.LLMClient") as client:
        client.return_value.generate.side_effect = [response(new=r"\textit{"), response()]
        report, candidate, _ = repair(SOURCE, compile_stub, tmp_path)
    assert report["status"] == "repaired" and len(report["attempts"]) == 2
    assert report["attempts"][0]["status"] == "compile_failed"
    second = client.return_value.generate.call_args_list[1].args[1]
    assert response(new=r"\textit{") in second and "Repair attempt 2" in second
    assert "textit remains invalid" in second and "The corrected source still fails" in second


def test_bad_content_edits_are_rejected_and_stop_after_two_attempts(tmp_path):
    with patch("tailoring.ai_repair.LLMClient") as client:
        client.return_value.generate.return_value = response("Nayan Kumar", "Different Person")
        report, candidate, info = repair(SOURCE, compile_stub, tmp_path)
    assert candidate is None and info is None and report["status"] == "failed"
    assert client.return_value.generate.call_count == 2
    assert all(a["status"] == "rejected" for a in report["attempts"])


@pytest.mark.parametrize("old,new", [("C++", "C#"), ("3 services", "5 services"), ("Nayan Kumar", "Kumar Nayan"), ("Python", "Rust")])
def test_names_numbers_skills_and_order_are_protected(old, new):
    with pytest.raises(ValueError, match="words, numbers"):
        corrected_source(SOURCE, response(old, new))


@pytest.mark.parametrize("command", [r"\phantom", r"\input", r"\include", r"\write", r"\directlua", r"\iffalse"])
def test_unsafe_new_commands_are_rejected(command):
    with pytest.raises(ValueError, match="commands"):
        corrected_source(SOURCE, SOURCE.replace(r"\badbold", command))


@pytest.mark.parametrize("answer", [None, {}, "", r"\textbf{Nayan Kumar}", SOURCE])
def test_same_incomplete_or_non_text_source_is_rejected(answer):
    with pytest.raises(ValueError): corrected_source(SOURCE, answer)


@pytest.mark.parametrize("prefix,suffix", [("", ""), ("```latex\n", "\n```"), ("```tex\n", "\n```"), ("```\n", "\n```")])
def test_complete_source_and_optional_fences_are_accepted(prefix, suffix):
    assert corrected_source(SOURCE, prefix + response() + suffix) == response() + "\n"


def test_windows_pasted_source_accepts_complete_unix_response_without_content_changes():
    source = SOURCE.replace(r"\section{Projects}", "\\section{Projects}\r\n")
    answer = source.replace("\r\n", "\n").replace(r"\badbold", r"\textbf")
    assert corrected_source(source, answer) == answer + "\n"
    assert "\r\n" in source and r"\badbold" in source


def test_windows_line_ending_matching_still_rejects_changed_content():
    source = SOURCE.replace(r"\section{Projects}", "\\section{Projects}\r\n")
    with pytest.raises(ValueError, match="words, numbers"):
        corrected_source(source, source.replace("\r\n", "\n").replace("Nayan Kumar", "Different Person"))


@pytest.mark.parametrize("diagnostic", ["Docker is unavailable.", "Build the compatibility compiler image.", "Font Example cannot be found", "File custom.sty not found", "Font Example not available"])
def test_missing_dependencies_do_not_trigger_ai(tmp_path, diagnostic):
    def unavailable(*args): raise CompileError(diagnostic)
    with patch("tailoring.ai_repair.LLMClient") as client:
        report, source, _ = repair(SOURCE, unavailable, tmp_path)
    assert report["status"] == "unavailable" and source is None
    client.assert_not_called()


def test_provider_rate_limit_stops_without_key_switch_or_second_attempt(tmp_path):
    with patch("tailoring.ai_repair.LLMClient") as client:
        client.return_value.generate.side_effect = GroqRateLimitError(60)
        report, source, _ = repair(SOURCE, compile_stub, tmp_path)
    assert report["status"] == "unavailable" and report["retry_after"] == 60 and source is None
    assert client.return_value.generate.call_count == 1


def test_short_explicit_rate_limit_is_respected_once_with_same_request(tmp_path):
    with patch("tailoring.ai_repair.LLMClient") as client, patch("tailoring.ai_repair.time.sleep") as sleep:
        client.return_value.generate.side_effect = [GroqRateLimitError(1), response()]
        report, candidate, _ = repair(SOURCE, compile_stub, tmp_path)
    assert report["status"] == "repaired" and candidate
    assert len(report["attempts"]) == 1 and client.return_value.generate.call_count == 2
    sleep.assert_called_once_with(2)
    assert client.return_value.generate.call_args_list[0] == client.return_value.generate.call_args_list[1]


def test_entire_source_is_sent_without_truncation_and_without_json_mode(tmp_path):
    source = SOURCE.replace(r"\section{Projects}", "\\section{Projects}\n" + "% source comment\n" * 4000)
    fixed = source.replace(r"\badbold", r"\textbf")
    with patch("tailoring.ai_repair.LLMClient") as client:
        client.return_value.generate.return_value = fixed
        report, candidate, _ = repair(source, compile_stub, tmp_path)
    assert report["status"] == "repaired" and candidate == fixed + "\n"
    call = client.return_value.generate.call_args
    payload = call.args[1]
    assert source in payload and len(source) > 36500
    assert "<compiler_error>" in payload and "<previous_feedback>\n\n</previous_feedback>" in payload
    assert call.kwargs == {"json_mode": False}


def test_api_creates_separate_compiled_revision_and_preserves_original(isolated):
    client, factory, root = isolated
    original = client.post("/tailor/masters/paste", data={"source": SOURCE, "filename": "original.tex"}).json()
    with factory() as db:
        db.get(LatexMaster, original["id"]).status = "active"; db.commit()
    with patch("tailoring.ai_repair.LLMClient") as provider, patch("api.tailor.compile_for_master", side_effect=lambda master, source, dest: compile_stub(source, dest)):
        provider.return_value.generate.return_value = response()
        result = client.post(f"/tailor/masters/{original['id']}/ai-repair")
        repeated = client.post(f"/tailor/masters/{original['id']}/ai-repair")
        assert repeated.json()["master"]["id"] == result.json()["master"]["id"]
        assert repeated.json()["cached"] and provider.return_value.generate.call_count == 1
    assert result.status_code == 200, result.text
    report = result.json(); fixed = report["master"]
    assert report["status"] == "repaired" and fixed["status"] == "compiled" and fixed["id"] != original["id"]
    assert fixed["ai_repair"]["original_id"] == original["id"] and fixed["ai_repair"]["diff"]
    assert client.get(fixed["pdf_url"]).content.startswith(b"%PDF")
    with factory() as db:
        original_row = db.get(LatexMaster, original["id"])
        assert original_row.source == SOURCE and original_row.status == "active"
        assert db.get(LatexMaster, fixed["id"]).status != "active"
    assert not (root / "masters" / original["id"] / "baseline.pdf").exists()


def test_failed_ai_output_never_creates_a_revision(isolated):
    client, factory, _ = isolated
    original = client.post("/tailor/masters/paste", data={"source": SOURCE}).json()
    with patch("tailoring.ai_repair.LLMClient") as provider, patch("api.tailor.compile_for_master", side_effect=lambda master, source, dest: compile_stub(source, dest)):
        provider.return_value.generate.return_value = response("Nayan", "Changed")
        result = client.post(f"/tailor/masters/{original['id']}/ai-repair").json()
    assert result["status"] == "failed" and result["master"] is None
    with factory() as db: assert db.query(LatexMaster).count() == 1


def test_ai_repair_preserves_project_assets_and_engine(isolated):
    client, _, _ = isolated
    raw = BytesIO()
    with zipfile.ZipFile(raw, "w") as project:
        project.writestr("resume.tex", SOURCE); project.writestr("custom.sty", "unchanged style")
    reference = reference_pdf()
    original = client.post("/tailor/masters", data={"engine": "xelatex"}, files={"file": ("project.zip", raw.getvalue(), "application/zip"), "reference": ("reference.pdf", reference, "application/pdf")}).json()
    with patch("tailoring.ai_repair.LLMClient") as provider, patch("api.tailor.compile_for_master", side_effect=lambda master, source, dest: compile_stub(source, dest)):
        provider.return_value.generate.return_value = response()
        report = client.post(f"/tailor/masters/{original['id']}/ai-repair").json()
    assert report["master"]["compatibility"]["engine"] == "xelatex"
    assert client.get(report["master"]["reference_pdf_url"]).content == reference
    with zipfile.ZipFile(BytesIO(client.get(report["master"]["project_url"]).content)) as project:
        assert project.read("custom.sty") == b"unchanged style"
        assert project.read("resume.tex").decode() == response() + "\n"


def test_initial_diagnostics_skip_a_duplicate_failed_compile(tmp_path):
    compiler = Mock(side_effect=compile_stub)
    with patch("tailoring.ai_repair.LLMClient") as provider:
        provider.return_value.generate.return_value = response()
        report, candidate, _ = repair(SOURCE, compiler, tmp_path, initial_diagnostics="./main.tex:1: Undefined control sequence. \\badbold")
    assert report["status"] == "repaired" and candidate == response() + "\n"
    compiler.assert_called_once_with(candidate, tmp_path / "candidate.pdf")


def test_two_failed_recompilations_never_return_a_candidate(tmp_path):
    compiler = Mock(side_effect=compile_stub)
    with patch("tailoring.ai_repair.LLMClient") as provider:
        provider.return_value.generate.return_value = response(new=r"\textit{")
        report, candidate, info = repair(SOURCE, compiler, tmp_path)
    assert report["status"] == "failed" and candidate is None and info is None
    assert [attempt["status"] for attempt in report["attempts"]] == ["compile_failed", "compile_failed"]
    assert compiler.call_count == 3 and provider.return_value.generate.call_count == 2


def reference_pdf():
    with fitz.open() as pdf:
        pdf.new_page().insert_text((50, 50), "Nayan Kumar built 3 services.")
        return pdf.tobytes()


@pytest.mark.parametrize("mode", ["paste", "file"])
def test_single_compile_valid_source_reference_no_ai_and_explicit_activation(isolated, mode):
    client, factory, _ = isolated
    fixed, reference = response(), reference_pdf()
    files = {"reference": ("reference.pdf", reference, "application/pdf")}
    data = {"source": fixed} if mode == "paste" else {}
    if mode == "file": files["file"] = ("resume.tex", fixed.encode(), "text/plain")
    with patch("tailoring.ai_repair.LLMClient") as provider, patch("api.tailor.compile_for_master", side_effect=lambda master, source, destination: compile_stub(source, destination)):
        result = client.post("/tailor/compile-resume", data=data, files=files)
    assert result.status_code == 200, result.text
    body, master = result.json(), result.json()["master"]
    assert not body["repaired"] and master["status"] == "compiled"
    assert client.get(master["pdf_url"]).content.startswith(b"%PDF")
    assert client.get(master["reference_pdf_url"]).content == reference
    assert client.get(f"/tailor/masters/{master['id']}/source").text == fixed
    assert client.get("/tailor/master").json()["id"] == master["id"]
    with factory() as db: assert db.query(LatexMaster).filter_by(status="active").count() == 0
    provider.assert_not_called()
    assert client.post(f"/tailor/masters/{master['id']}/activate").status_code == 200


def test_single_compile_ai_recompiles_without_mutating_or_activating_original(isolated):
    client, factory, root = isolated
    compiler = Mock(side_effect=lambda master, source, destination: compile_stub(source, destination))
    with patch("tailoring.ai_repair.LLMClient") as provider, patch("api.tailor.compile_for_master", compiler):
        provider.return_value.generate.return_value = response()
        result = client.post("/tailor/compile-resume", data={"source": SOURCE})
    assert result.status_code == 200, result.text
    body, fixed = result.json(), result.json()["master"]
    assert body["repaired"] and fixed["status"] == "compiled" and compiler.call_count == 2
    assert client.get(fixed["pdf_url"]).content.startswith(b"%PDF")
    with factory() as db:
        original = db.query(LatexMaster).filter_by(status="draft").one()
        assert original.source == SOURCE and original.id != fixed["id"]
        assert db.get(LatexMaster, fixed["id"]).source == response() + "\n"
        assert db.query(LatexMaster).filter_by(status="active").count() == 0
        assert not (root / "masters" / original.id / "baseline.pdf").exists()


def test_failed_single_compile_returns_error_and_no_pdf(isolated):
    client, factory, root = isolated
    with patch("tailoring.ai_repair.LLMClient") as provider, patch("api.tailor.compile_for_master", side_effect=lambda master, source, destination: compile_stub(source, destination)):
        provider.return_value.generate.return_value = response("Nayan Kumar", "Changed Person")
        result = client.post("/tailor/compile-resume", data={"source": SOURCE})
    assert result.status_code == 422 and "changed resume words" in result.json()["detail"]
    assert "pdf_url" not in result.json() and client.get("/tailor/master").json() is None
    with factory() as db:
        original = db.query(LatexMaster).one()
        assert original.source == SOURCE and original.status == "draft" and original.baseline_pages is None
        assert not (root / "masters" / original.id / "baseline.pdf").exists()


@pytest.mark.parametrize("data,files", [({}, {}), ({"source": "   "}, {}), ({"source": SOURCE}, {"file": ("resume.tex", SOURCE.encode(), "text/plain")})])
def test_single_compile_rejects_both_or_neither_input(isolated, data, files):
    client, factory, _ = isolated
    assert client.post("/tailor/compile-resume", data=data, files=files).status_code == 422
    with factory() as db: assert db.query(LatexMaster).count() == 0


def test_current_master_prefers_active_then_latest_compiled_never_draft(isolated):
    client, _, _ = isolated
    assert client.get("/tailor/master").json() is None
    draft = client.post("/tailor/masters/paste", data={"source": SOURCE}).json()
    assert client.get("/tailor/master").json() is None
    with patch("api.tailor.compile_for_master", side_effect=lambda master, source, destination: compile_stub(source, destination)):
        first = client.post("/tailor/compile-resume", data={"source": response()}).json()["master"]
        second = client.post("/tailor/compile-resume", data={"source": response()}).json()["master"]
    assert client.get("/tailor/master").json()["id"] == second["id"] != draft["id"]
    assert client.post(f"/tailor/masters/{first['id']}/activate").status_code == 200
    assert client.get("/tailor/master").json()["id"] == first["id"]
