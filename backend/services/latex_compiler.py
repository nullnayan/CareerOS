"""Offline, resource-limited container compilation; never execute TeX on the host."""
import json
import re
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import uuid
import fitz

IMAGE = "careeros-latex:2026-10-compat"
LEGACY_IMAGE = "careeros-latex:2026-10"
ENGINES = ("pdflatex", "xelatex", "lualatex")
MAX_PROJECT_FILES = 1000
MAX_PROJECT_BYTES = 25 * 1024 * 1024
DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "latex"


class CompileError(Exception):
    def __init__(self, message: str, diagnostics: str | None = None):
        self.diagnostics = diagnostics or message
        super().__init__(message)


def compilation_failure(diagnostics: str) -> CompileError:
    missing_font = re.search(r'(?:font\s+["\']([^"\']+)["\']\s+cannot be found|fontspec Error:\s*The font\s+["\']([^"\']+))', diagnostics, re.I)
    if missing_font or ("fontspec" in diagnostics.lower() and "cannot be found" in diagnostics.lower()):
        name = next((value for value in missing_font.groups() if value), "requested font") if missing_font else "requested font"
        return CompileError(f"The font {name!r} is not available in the offline compiler. Include licensed font files in the project and use a relative Path, or choose an installed font such as Liberation Serif, Liberation Sans, or Latin Modern Roman.", diagnostics)
    match = re.search(r"(?m)^[^:\r\n]+\.(?:tex|sty|cls):(\d+):\s*(?!\s*==>)(.+)$", diagnostics)
    if match:
        line, detail = match.groups()
        if "missing \\item" in detail:
            message = f"LaTeX error on line {line}: a nested list has no parent item. Add \\item[] before that nested list, or use a corrected source revision."
        elif "Paragraph ended before" in detail:
            message = f"LaTeX error near line {line}: {detail} Check the preceding command for a missing argument or a blank line inside a text command."
        else:
            message = f"LaTeX error on line {line}: {detail}"
    else:
        fatal = re.search(r"(?m)^!\s*(.+)", diagnostics)
        message = "LaTeX compilation failed: " + (fatal[1] if fatal else "see Compiler diagnostics below for details.")
    return CompileError(message, diagnostics)


def directory(kind: str, identifier: str) -> Path:
    if kind not in {"masters", "runs"}:
        raise ValueError("Invalid artifact kind.")
    uuid.UUID(identifier)
    root = DATA_ROOT / kind / identifier
    root.mkdir(parents=True, exist_ok=True)
    return root


def compiler_status() -> dict:
    if not shutil.which("docker"):
        return {"ready": False, "engines": [], "compatibility_ready": False, "message": "Install and start Docker Desktop, then build the compiler image."}
    try:
        result = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=10)
        if result.returncode == 0:
            return {"ready": True, "engines": list(ENGINES), "compatibility_ready": True, "image": IMAGE, "message": "PDF, XeLaTeX, and LuaLaTeX compilers ready"}
        legacy = subprocess.run(["docker", "image", "inspect", LEGACY_IMAGE], capture_output=True, timeout=10)
        if legacy.returncode == 0:
            return {"ready": True, "engines": ["pdflatex"], "compatibility_ready": False, "image": LEGACY_IMAGE,
                    "message": f"pdfLaTeX ready. Build compiler/Dockerfile as {IMAGE} to enable XeLaTeX and LuaLaTeX."}
        return {"ready": False, "engines": [], "compatibility_ready": False, "message": f"Start Docker and build compiler/Dockerfile as {IMAGE}."}
    except (OSError, subprocess.TimeoutExpired):
        return {"ready": False, "engines": [], "compatibility_ready": False, "message": "Docker is unavailable. Start Docker Desktop."}


def without_comments(source: str) -> str:
    # A percent after an even backslash count starts a TeX comment (\\% is
    # a line break followed by a comment; \% is a literal percent).
    lines = []
    for line in source.splitlines():
        for index, char in enumerate(line):
            if char == "%" and (index - len(line[:index].rstrip("\\"))) % 2 == 0:
                line = line[:index]
                break
        lines.append(line)
    return "\n".join(lines)


def detect_engine(source: str) -> str:
    hint = re.search(r"(?im)^\s*%\s*!\s*TeX\s+program\s*=\s*(pdflatex|xelatex|lualatex)\s*$", source)
    if hint: return hint[1].lower()
    clean = without_comments(source)
    packages = re.findall(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\]\s*)?\{([^{}]+)\}", clean)
    if re.search(r"\\directlua\b", clean) or any(package.strip() in {"luacode", "luatextra", "luaotfload"} for group in packages for package in group.split(",")):
        return "lualatex"
    if any(package.strip() in {"fontspec", "unicode-math"} for group in packages for package in group.split(",")):
        return "xelatex"
    return "pdflatex"


def safe_main_file(value: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise CompileError("Choose a relative .tex main file inside the project.")
    path = Path(value)
    if path.anchor or path.is_absolute() or any(part in {"..", "."} for part in path.parts) or path.suffix.lower() != ".tex" or any(ord(char) < 32 for char in value):
        raise CompileError("Choose a relative .tex main file inside the project.")
    return path


def copy_project(project: Path, work: Path) -> None:
    root = Path(project)
    if not root.is_dir() or root.is_symlink() or getattr(root.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
        raise CompileError("The LaTeX project must be a regular directory without symbolic links.")
    resolved = root.resolve()
    count = total = 0
    for item in root.rglob("*"):
        metadata = item.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
            raise CompileError("Symbolic links and junctions are not supported in LaTeX projects.")
        if not item.resolve().is_relative_to(resolved):
            raise CompileError("A project file escapes its project directory.")
        relative = item.relative_to(root)
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise CompileError("Only regular project files are supported.")
        count += 1; total += metadata.st_size
        if count > MAX_PROJECT_FILES or total > MAX_PROJECT_BYTES:
            raise CompileError("Project exceeds the 1,000-file or 25 MB compiler limit.")
        target = work / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)


def compile_source(source: str, destination: Path, *, engine: str = "auto", project: Path | None = None,
                   main_file: str = "main.tex", recovery: bool = False) -> dict:
    if engine not in {"auto", *ENGINES}:
        raise CompileError("Choose auto, pdflatex, xelatex, or lualatex as the compiler engine.")
    main = safe_main_file(main_file)
    status = compiler_status()
    if not status["ready"]:
        raise CompileError(status["message"])
    # Per-run isolated input/output only. TeX cannot mount the application or secrets.
    with tempfile.TemporaryDirectory(prefix="careeros-tex-") as temporary:
        work = Path(temporary)
        if project is not None:
            copy_project(project, work)
        (work / main).parent.mkdir(parents=True, exist_ok=True)
        (work / main).write_bytes(source.encode("utf-8"))
        detection_source = source
        for candidate in work.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in {".tex", ".sty", ".cls", ".ltx"} and candidate != work / main:
                detection_source += "\n" + candidate.read_text(encoding="utf-8", errors="replace")
        selected = detect_engine(detection_source) if engine == "auto" else engine
        if selected not in status.get("engines", ["pdflatex"]):
            raise CompileError(f"{selected} requires the compatibility compiler image. Build compiler/Dockerfile as {IMAGE}.")
        image = status.get("image", LEGACY_IMAGE)
        try:
            inspected = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image], capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CompileError("Cannot resolve the compiler image fingerprint. Start Docker Desktop.") from exc
        image_id = inspected.stdout.decode().strip()
        if inspected.returncode or not image_id.startswith("sha256:"):
            raise CompileError("Cannot resolve the compiler image fingerprint.")
        # A random output name prevents an uploaded PDF from masquerading as a
        # compiler result while preserving all original project assets.
        job_name = "careeros-output-" + uuid.uuid4().hex
        output_pdf = work / f"{job_name}.pdf"
        diagnostics = ""
        has_errors = False
        for pass_number in (1, 2):
            container_name = "careeros-tex-" + uuid.uuid4().hex
            command = ["docker", "run", "--rm", "--name", container_name, "--network=none", "--read-only",
                       "--cap-drop=ALL", "--security-opt=no-new-privileges", "--memory=384m", "--cpus=1", "--pids-limit=64",
                       "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m", "--mount", f"type=bind,source={work},target=/work",
                       "--env", "openin_any=p", "--env", "openout_any=p", "--env", "TEXMFVAR=/tmp/texmf-var",
                       "--env", "TEXMFCACHE=/tmp/texmf-cache:/var/lib/texmf", "--entrypoint", selected, image_id,
                       "-no-shell-escape", "-no-parse-first-line", "-interaction=nonstopmode", "-file-line-error",
                       f"-jobname={job_name}"]
            if not recovery:
                command.append("-halt-on-error")
            command.append("./" + main.as_posix())
            try:
                result = subprocess.run(command, capture_output=True, timeout=60)
            except subprocess.TimeoutExpired as exc:
                try:
                    subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                raise CompileError("Compilation exceeded the 60-second limit for a pass (two passes maximum).") from exc
            except OSError as exc:
                raise CompileError("Docker could not start the compiler container.") from exc
            output = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
            diagnostics = (diagnostics + f"\n--- Pass {pass_number} ({selected}) ---\n" + output)[-20000:]
            has_errors = has_errors or result.returncode != 0 or bool(re.search(r"(?m)^!\s|^.*\.tex:\d+:.*(?:Error|Undefined control sequence|Paragraph ended before|Missing )", output))
            if (result.returncode and not recovery) or not output_pdf.exists():
                raise compilation_failure(diagnostics)
        try:
            with fitz.open(output_pdf) as pdf:
                text = "\n".join(page.get_text() for page in pdf)
                if not len(pdf) or not text.strip():
                    raise CompileError("Compiler produced an empty or unreadable PDF.", diagnostics)
                clipped = any(b[0] < -1 or b[1] < -1 or b[2] > page.rect.width + 1 or b[3] > page.rect.height + 1
                              for page in pdf for b in page.get_text("blocks"))
                info = {"pages": len(pdf), "text": text, "overflow": clipped or "Overfull \\hbox" in diagnostics or "Overfull \\vbox" in diagnostics,
                        "diagnostics": diagnostics, "engine": selected, "image": image_id, "has_errors": has_errors, "recovery": recovery, "warnings": []}
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            raise CompileError("Compiler produced an unreadable PDF.", diagnostics) from exc
        if re.search(r"\\(?:bibliography|addbibresource)\b", without_comments(detection_source)):
            info["warnings"].append("BibTeX and Biber are not run automatically. Include the generated .bbl file for a project that requires bibliography processing.")
        if has_errors:
            info["warnings"].append("Recovery PDF contains LaTeX errors and is for preview only; it must not be activated as a resume baseline.")
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output_pdf, destination)
        destination.with_suffix(".build.json").write_text(json.dumps({key: info[key] for key in ("image", "engine", "pages", "overflow", "has_errors", "recovery", "warnings")}), encoding="utf-8")
        return info
