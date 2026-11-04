"""Container-command contracts and optional real multi-engine compilation."""
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch
import fitz
import pytest
from services import latex_compiler as compiler

SOURCE = r"\documentclass{article}\begin{document}Compiler compatibility test.\end{document}"
FONT_SOURCE = r"\documentclass{article}\usepackage{fontspec}\setmainfont{Liberation Serif}\begin{document}Unicode compatibility test.\end{document}"
FINGERPRINT = "sha256:" + "a" * 64


def pdf_bytes():
    with fitz.open() as pdf:
        pdf.new_page().insert_text((50, 50), "Compiler compatibility test.")
        return pdf.tobytes()


@pytest.fixture
def docker(monkeypatch):
    monkeypatch.setattr(compiler, "compiler_status", lambda: {"ready": True, "engines": list(compiler.ENGINES), "image": compiler.IMAGE})
    calls = []
    def run(command, **options):
        calls.append((command, options))
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, FINGERPRINT.encode(), b"")
        if command[:2] == ["docker", "run"]:
            mount = command[command.index("--mount") + 1]
            work = Path(mount.split("source=", 1)[1].rsplit(",target=", 1)[0])
            name = next(value.split("=", 1)[1] for value in command if value.startswith("-jobname="))
            (work / f"{name}.pdf").write_bytes(pdf_bytes())
            return subprocess.CompletedProcess(command, 0, b"Output written on careeros-output.pdf", b"")
        return subprocess.CompletedProcess(command, 0, b"", b"")
    monkeypatch.setattr(compiler.subprocess, "run", run)
    return calls, run


def test_auto_detection_ignores_commented_packages_and_supports_requirepackage():
    assert compiler.detect_engine(SOURCE) == "pdflatex"
    assert compiler.detect_engine(r"%\usepackage{fontspec}" + "\n" + SOURCE) == "pdflatex"
    assert compiler.detect_engine(r"\\%\usepackage{fontspec}" + "\n" + SOURCE) == "pdflatex"
    assert compiler.detect_engine(r"\RequirePackage[quiet]{fontspec}") == "xelatex"
    assert compiler.detect_engine("% !TeX program = lualatex\n" + FONT_SOURCE) == "lualatex"
    assert compiler.detect_engine(r"\directlua{tex.print('test')}") == "lualatex"
    assert compiler.detect_engine("% !TeX program = /bin/sh\n" + SOURCE) == "pdflatex"
    assert compiler.detect_engine(r"\usepackage{amsmath,unicode-math}") == "xelatex"


@pytest.mark.parametrize("engine", ["pdflatex", "xelatex", "lualatex"])
def test_whitelisted_engines_run_two_strict_passes_with_same_isolation(tmp_path, docker, engine):
    calls, _ = docker
    info = compiler.compile_source(SOURCE, tmp_path / "resume.pdf", engine=engine)
    runs = [command for command, options in calls if command[:2] == ["docker", "run"]]
    assert len(runs) == 2
    for command in runs:
        assert command[command.index("--entrypoint") + 1] == engine
        assert "--network=none" in command and "--read-only" in command and "--cap-drop=ALL" in command
        assert "--security-opt=no-new-privileges" in command and "--memory=384m" in command
        assert "--pids-limit=64" in command and "-no-shell-escape" in command
        assert "-no-parse-first-line" in command and "-interaction=nonstopmode" in command
        assert "-file-line-error" in command and "-halt-on-error" in command
        assert FINGERPRINT in command and command[-1] == "./main.tex"
    assert info["engine"] == engine and info["has_errors"] is False and info["pages"] == 1
    metadata = json.loads((tmp_path / "resume.build.json").read_text())
    assert metadata["engine"] == engine and metadata["image"] == FINGERPRINT and not metadata["has_errors"]


def test_unknown_engine_and_escaping_main_file_are_rejected(tmp_path):
    with pytest.raises(compiler.CompileError): compiler.compile_source(SOURCE, tmp_path / "resume.pdf", engine="bash")
    for main in ("../outside.tex", "/main.tex", "C:/main.tex", r"src\main.tex", "main.pdf"):
        with pytest.raises(compiler.CompileError): compiler.compile_source(SOURCE, tmp_path / "resume.pdf", main_file=main)


def test_project_includes_assets_and_detects_fontspec_in_class_without_source_edits(tmp_path, docker):
    calls, original_run = docker
    project = tmp_path / "project"; project.mkdir()
    (project / "assets").mkdir(); (project / "assets" / "logo.png").write_bytes(b"image")
    (project / "resume.cls").write_text(r"\RequirePackage{fontspec}")
    (project / "cv.tex").write_text("Original stored source")
    def run(command, **options):
        if command[:2] == ["docker", "run"]:
            work = Path(command[command.index("--mount") + 1].split("source=", 1)[1].rsplit(",target=", 1)[0])
            assert (work / "assets" / "logo.png").read_bytes() == b"image"
            assert (work / "cv.tex").read_text() == SOURCE
            assert command[-1] == "./cv.tex"
        return original_run(command, **options)
    with patch.object(compiler.subprocess, "run", side_effect=run):
        result = compiler.compile_source(SOURCE, tmp_path / "resume.pdf", project=project, main_file="cv.tex")
    assert result["engine"] == "xelatex"
    assert (project / "cv.tex").read_text() == "Original stored source"


def test_symlink_project_files_are_not_copied(tmp_path):
    project = tmp_path / "project"; project.mkdir()
    outside = tmp_path / "outside.tex"; outside.write_text("outside")
    try:
        (project / "linked.tex").symlink_to(outside)
    except OSError:
        pytest.skip("Windows symlink permission unavailable")
    with pytest.raises(compiler.CompileError, match="Symbolic links"):
        compiler.copy_project(project, tmp_path / "work")


def test_project_copy_is_bounded(tmp_path, monkeypatch):
    project = tmp_path / "project"; project.mkdir(); (project / "main.tex").write_bytes(b"x" * 20)
    monkeypatch.setattr(compiler, "MAX_PROJECT_BYTES", 10)
    with pytest.raises(compiler.CompileError, match="limit"):
        compiler.copy_project(project, tmp_path / "work")


def test_recovery_accepts_error_pdf_but_marks_build_and_omits_halt(tmp_path, docker):
    calls, original_run = docker
    def run(command, **options):
        result = original_run(command, **options)
        if command[:2] == ["docker", "run"]:
            result.returncode = 1
            result.stdout = b"./main.tex:2: Undefined control sequence.\nOutput written on careeros-output.pdf"
        return result
    with patch.object(compiler.subprocess, "run", side_effect=run):
        result = compiler.compile_source(SOURCE, tmp_path / "recovery.pdf", recovery=True)
    assert result["has_errors"] and result["recovery"] and result["warnings"]
    assert all("-halt-on-error" not in command for command, _ in calls if command[:2] == ["docker", "run"])
    assert json.loads((tmp_path / "recovery.build.json").read_text())["has_errors"] is True


def test_strict_failure_never_copies_existing_or_error_pdf(tmp_path, docker):
    _, original_run = docker
    def run(command, **options):
        result = original_run(command, **options)
        if command[:2] == ["docker", "run"]:
            result.returncode = 1; result.stdout = b"./custom.tex:7: Undefined control sequence."
        return result
    with patch.object(compiler.subprocess, "run", side_effect=run), pytest.raises(compiler.CompileError, match="line 7"):
        compiler.compile_source(SOURCE, tmp_path / "strict.pdf", main_file="custom.tex")
    assert not (tmp_path / "strict.pdf").exists()


def test_supplied_pdf_cannot_masquerade_as_compiler_output(tmp_path, docker):
    _, original_run = docker
    project = tmp_path / "project"; project.mkdir(); (project / "careeros-output.pdf").write_bytes(pdf_bytes())
    def run(command, **options):
        if command[:2] == ["docker", "run"]:
            return subprocess.CompletedProcess(command, 0, b"No PDF output", b"")
        return original_run(command, **options)
    with patch.object(compiler.subprocess, "run", side_effect=run), pytest.raises(compiler.CompileError):
        compiler.compile_source(SOURCE, tmp_path / "resume.pdf", project=project, recovery=True)
    assert not (tmp_path / "resume.pdf").exists()


def test_timeout_kills_only_named_compiler_container(tmp_path, docker):
    calls, original_run = docker
    def run(command, **options):
        if command[:2] == ["docker", "run"]:
            calls.append((command, options))
            raise subprocess.TimeoutExpired(command, options["timeout"])
        return original_run(command, **options)
    with patch.object(compiler.subprocess, "run", side_effect=run), pytest.raises(compiler.CompileError, match="60-second"):
        compiler.compile_source(SOURCE, tmp_path / "resume.pdf")
    kills = [command for command, _ in calls if command[:2] == ["docker", "kill"]]
    assert len(kills) == 1 and kills[0][2].startswith("careeros-tex-")


def test_legacy_image_reports_pdf_only_and_blocks_xelatex(tmp_path, monkeypatch):
    monkeypatch.setattr(compiler.shutil, "which", lambda name: "docker")
    def inspect(command, **kwargs):
        return subprocess.CompletedProcess(command, 0 if command[-1] == compiler.LEGACY_IMAGE else 1, b"", b"")
    with patch.object(compiler.subprocess, "run", side_effect=inspect):
        status = compiler.compiler_status()
        assert status["ready"] and status["engines"] == ["pdflatex"] and not status["compatibility_ready"]
        with pytest.raises(compiler.CompileError, match="compatibility compiler image"):
            compiler.compile_source(FONT_SOURCE, tmp_path / "resume.pdf")


def test_missing_fonts_have_actionable_diagnostics():
    error = compiler.compilation_failure('Package fontspec Error: The font "Proprietary Font" cannot be found.')
    assert "Proprietary Font" in str(error) and "Liberation" in str(error)
    assert "fontspec Error" in error.diagnostics


def test_bibliography_processing_limit_is_reported(tmp_path, docker):
    info = compiler.compile_source(SOURCE + r"\bibliography{references}", tmp_path / "resume.pdf")
    assert any("BibTeX" in warning for warning in info["warnings"])


@pytest.mark.skipif(os.getenv("CAREEROS_TEST_COMPAT_LATEX") != "1", reason="Set CAREEROS_TEST_COMPAT_LATEX=1 with the compatibility image built")
@pytest.mark.parametrize("engine", ["pdflatex", "xelatex", "lualatex"])
def test_real_compiler_engine(tmp_path, engine):
    source = SOURCE if engine == "pdflatex" else FONT_SOURCE
    result = compiler.compile_source(source, tmp_path / f"{engine}.pdf", engine=engine)
    assert result["pages"] == 1 and not result["has_errors"] and "compatibility test" in result["text"]


@pytest.mark.skipif(os.getenv("CAREEROS_TEST_COMPAT_LATEX") != "1", reason="Set CAREEROS_TEST_COMPAT_LATEX=1 with Docker available")
def test_real_recovery_preview_has_errors(tmp_path):
    source = r"\documentclass{article}\begin{document}Readable recovery output.\undefinedCareerOSCommand\end{document}"
    with pytest.raises(compiler.CompileError):
        compiler.compile_source(source, tmp_path / "strict.pdf")
    recovered = compiler.compile_source(source, tmp_path / "recovered.pdf", recovery=True)
    assert recovered["has_errors"] and recovered["pages"] == 1
