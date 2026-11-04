"""Project imports, mappings, and preview/repair state transitions, isolated."""
from io import BytesIO
import os
import stat
from unittest.mock import patch as mocked
import zipfile
import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db.models import Base, LatexMaster
from db.session import get_db
from main import app
from tailoring.compatibility import unpack_project, proposal
from tailoring.latex import category_regions, patch

SOURCE = r"\documentclass{article}\begin{document}\section{Skills}\textbf{Languages}{: Python}\section{Projects}Protected experience\end{document}"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def database():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr("services.latex_compiler.DATA_ROOT", tmp_path)
    yield TestClient(app), factory, tmp_path
    app.dependency_overrides.clear(); engine.dispose()


def zipped(files):
    result = BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        for name, value in files.items(): archive.writestr(name, value)
    return result.getvalue()


def import_zip(client, files, **data):
    return client.post("/tailor/masters", data=data, files={"file": ("project.zip", zipped(files), "application/zip")})


@pytest.mark.parametrize("body", [
    r"\textbf{Languages}{: Python}",
    r"\textbf{Languages:} Python \\",
    r"\textbf{Languages}: Python \\",
    r"\begin{itemize}\item \textbf{Languages:} Python\end{itemize}",
    r"\cvskill{Languages}{Python}",
    "\\custom{Languages}{\n% CAREEROS_SKILL_START: Languages\nPython\n% CAREEROS_SKILL_END\n}",
])
def test_multiple_templates_patch_only_the_selected_value(body):
    source = "\\documentclass{article}\\begin{document}\\cvsection{Skills}\n" + body + "\n\\cvsection{Projects}Original project\\end{document}"
    mapping = category_regions(source)
    updated, changes = patch(source, [{"name": "Terraform", "category": "Languages"}])
    region = mapping["Languages"]
    assert updated[:region["start"]] == source[:region["start"]]
    assert updated.endswith(source[region["end"]:])
    assert changes[0]["added"] == ["Terraform"]


def test_empty_mapped_value_has_no_leading_comma():
    updated, _ = patch(SOURCE.replace(": Python", ": "), [{"name": "Rust", "category": "Languages"}])
    assert category_regions(updated)["Languages"]["value"].strip() == ": Rust"


@pytest.mark.parametrize("body", [
    "% CAREEROS_SKILL_START: Languages\nPython\n% CAREEROS_SKILL_START: Tools\nGit\n% CAREEROS_SKILL_END",
    "% CAREEROS_SKILL_END\nPython",
    "% CAREEROS_SKILL_START: Languages\nPython",
    "% CAREEROS_SKILL_START: Languages\n\\begin{itemize}Python\\end{itemize}\n% CAREEROS_SKILL_END",
])
def test_ambiguous_or_structural_markers_are_rejected(body):
    with pytest.raises(ValueError): category_regions("\\begin{document}\\section{Skills}\n" + body + "\n\\end{document}")


def test_imports_unmapped_template_for_preview_without_rewriting(isolated):
    client, _, _ = isolated
    source = SOURCE.replace(r"\textbf{Languages}{: Python}", "Python, SQL")
    response = client.post("/tailor/masters/paste", data={"source": source})
    assert response.status_code == 200, response.text
    assert response.json()["categories"] == []
    assert not response.json()["compatibility"]["mapping_supported"]
    assert client.get(f"/tailor/masters/{response.json()['id']}/source").text == source


def test_project_assets_survive_edit_and_download(isolated):
    client, _, _ = isolated
    response = import_zip(client, {"wrapper/main.tex": SOURCE, "wrapper/custom.cls": "original style"}, engine="xelatex")
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["compatibility"]["engine"] == "xelatex" and item["compatibility"]["main_file"] == "main.tex"
    assert item["compatibility"]["project_files"] == ["main.tex", "custom.cls"]
    edited = client.post("/tailor/masters/paste", data={"source": SOURCE + "\n% changed", "based_on": item["id"], "engine": "xelatex"})
    assert edited.status_code == 200, edited.text
    with zipfile.ZipFile(BytesIO(client.get(edited.json()["project_url"]).content)) as project:
        assert project.read("custom.cls") == b"original style"
        assert project.read("main.tex").decode().endswith("% changed")
    assert client.get(f"/tailor/masters/{item['id']}/source").text == SOURCE


def test_engine_detection_includes_custom_class_dependencies(isolated):
    client, _, _ = isolated
    response = import_zip(client, {"main.tex": SOURCE, "custom.cls": r"\RequirePackage{fontspec}"})
    assert response.status_code == 200
    assert response.json()["compatibility"]["detected_engine"] == "xelatex"


@pytest.mark.parametrize("name", ["../outside.tex", "/outside.tex", "C:/outside.tex", "folder\\..\\outside.tex", "NUL.tex", "folder/bad. "])
def test_zip_paths_are_bounded(name):
    with pytest.raises(ValueError): unpack_project(zipped({name: SOURCE}))


def test_zip_symlinks_duplicates_and_file_parent_conflicts_are_rejected():
    raw = BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        link = zipfile.ZipInfo("link.tex"); link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "../../private")
    with pytest.raises(ValueError): unpack_project(raw.getvalue())
    with pytest.raises(ValueError): unpack_project(zipped({"main.tex": SOURCE, "MAIN.tex": SOURCE}))
    with pytest.raises(ValueError): unpack_project(zipped({"file": "not a directory", "file/main.tex": SOURCE}))


def test_main_file_ambiguity_requires_choice(isolated):
    client, _, _ = isolated
    files = {"first.tex": SOURCE, "second.tex": SOURCE}
    assert import_zip(client, files).status_code == 422
    response = import_zip(client, files, main_file="second.tex")
    assert response.status_code == 200 and response.json()["compatibility"]["main_file"] == "second.tex"


def test_preview_never_becomes_a_baseline_and_does_not_bypass_overflow(isolated):
    client, _, _ = isolated
    identifier = client.post("/tailor/masters/paste", data={"source": SOURCE}).json()["id"]
    def compile_stub(master, source, path, recovery=False):
        with fitz.open() as pdf:
            pdf.new_page().insert_text((50, 50), "Preview content")
            pdf.save(path)
        return {"pages": 1, "text": "Preview content", "overflow": not recovery, "has_errors": recovery, "diagnostics": "source errors" if recovery else "Overfull"}
    with mocked("api.tailor.compile_for_master", side_effect=compile_stub):
        preview = client.post(f"/tailor/masters/{identifier}/preview")
        assert preview.status_code == 200 and preview.json()["status"] == "draft"
        assert preview.json()["pdf_url"] is None
        assert client.post(f"/tailor/masters/{identifier}/activate").status_code == 409
        assert client.post(f"/tailor/masters/{identifier}/compile").status_code == 200
        assert client.post(f"/tailor/masters/{identifier}/preview").status_code == 200
        assert client.post(f"/tailor/masters/{identifier}/activate").status_code == 409


def test_repairs_are_explicit_immutable_and_preserve_project_assets(isolated):
    client, _, _ = isolated
    broken = SOURCE.replace(r"\begin{document}", r"\newcommand{\resumeEduHeading}[4]{#1 #2 #3 #4}\begin{document}" )
    broken = broken.replace(r"\section{Skills}", "\\resumeEduHeading{College}{City}{Degree}\n\\resumeItemListStart\n\\section{Skills}")
    item = import_zip(client, {"main.tex": broken, "extra.sty": "style"}).json()
    suggested = client.post(f"/tailor/masters/{item['id']}/repair-proposal")
    assert suggested.status_code == 200 and len(suggested.json()["changes"]) == 1
    assert client.post(f"/tailor/masters/{item['id']}/repair", json={"accept": False}).status_code == 422
    fixed = client.post(f"/tailor/masters/{item['id']}/repair", json={"accept": True})
    assert fixed.status_code == 200 and fixed.json()["id"] != item["id"] and fixed.json()["status"] == "draft"
    assert "extra.sty" in fixed.json()["compatibility"]["project_files"]
    assert client.get(f"/tailor/masters/{item['id']}/source").text == broken
    assert not proposal(suggested.json()["source"])["changes"]


def test_asset_tampering_fails_closed(isolated):
    from api.tailor import compile_for_master
    from services.latex_compiler import CompileError
    client, factory, root = isolated
    item = import_zip(client, {"main.tex": SOURCE, "custom.cls": "style"}).json()
    (root / "masters" / item["id"] / "project" / "custom.cls").write_text("changed")
    with factory() as db:
        with pytest.raises(CompileError, match="integrity"):
            compile_for_master(db.get(LatexMaster, item["id"]), SOURCE, root / "out.pdf")


CUSTOM = r"""\documentclass{article}
\newcommand{\customsection}[1]{\par\bigskip\noindent\textbf{#1}\par}
\begin{document}
\customsection{Capabilities}
Languages:
% CAREEROS_SKILL_START: Languages
Python
% CAREEROS_SKILL_END
\par
\customsection{Work}
Built reliable services.
\end{document}
"""


def test_explicit_mappings_support_custom_headings_and_preserve_full_pdf_text():
    from api.tailor import validate_pdf_content
    from services.latex_compiler import CompileError
    result, changes = patch(CUSTOM, [{"name": "Rust", "category": "Languages"}])
    assert "Python, Rust" in result
    validate_pdf_content("Capabilities\nLanguages: Python, Rust\nWork\nBuilt reliable services.", "Capabilities\nLanguages: Python\nWork\nBuilt reliable services.", CUSTOM, changes)
    with pytest.raises(CompileError, match="Original PDF text changed"):
        validate_pdf_content("Capabilities\nLanguages: Python, Rust\nWork\nChanged claims.", "Capabilities\nLanguages: Python\nWork\nBuilt reliable services.", CUSTOM, changes)


def test_markers_cannot_change_preamble_or_unbalance_command_braces():
    with pytest.raises(ValueError):
        category_regions(CUSTOM.replace("\\begin{document}", "").replace("\\customsection{Work}", "\\begin{document}\\customsection{Work}"))
    with pytest.raises(ValueError):
        category_regions(CUSTOM.replace("Python\n", "Python}\n"))


def test_repair_does_not_rewrite_optional_arguments_or_commented_calls():
    optional = r"\newcommand{\resumeHeading}[4][default]{#1#2#3#4}\begin{document}\resumeHeading{A}{B}{C}\resumeItemListStart\end{document}"
    assert not proposal(optional)["changes"]
    commented = r"\newcommand{\resumeHeading}[4]{#1#2#3#4}\begin{document}" + "\n% \\resumeHeading{A}{B}{C}\\resumeItemListStart\n\\end{document}"
    assert not proposal(commented)["changes"]


@pytest.mark.skipif(os.getenv("CAREEROS_TEST_COMPAT_LATEX") != "1", reason="Set CAREEROS_TEST_COMPAT_LATEX=1 for actual marked-template compilation")
def test_real_custom_heading_pdf_validation(tmp_path):
    from services.latex_compiler import compile_source
    from api.tailor import validate_pdf_content
    baseline = compile_source(CUSTOM, tmp_path / "baseline.pdf")
    source, changes = patch(CUSTOM, [{"name": "Rust", "category": "Languages"}])
    generated = compile_source(source, tmp_path / "tailored.pdf")
    validate_pdf_content(generated["text"], baseline["text"], CUSTOM, changes)
    assert not baseline["has_errors"] and not generated["has_errors"]
