"""Bounded LaTeX project import and reviewable compatibility diagnostics."""
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile
from tailoring.latex import category_regions, group_end, uncomment, digest

ENGINES = {"auto", "pdflatex", "xelatex", "lualatex"}


def safe_path(name):
    if len(name) > 300 or any(ord(char) < 32 for char in name) or "\\" in name:
        raise ValueError("Project paths must use forward slashes.")
    path = PurePosixPath(name)
    if not name or path.is_absolute() or any(p in {".", ".."} or ":" in p or p.endswith((".", " ")) for p in path.parts):
        raise ValueError("Project contains an unsafe file path.")
    if any(re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p) for p in path.parts):
        raise ValueError("Project contains a reserved filename.")
    return path.as_posix()


def unpack_project(raw, requested=""):
    files = {}
    try:
        archive = zipfile.ZipFile(BytesIO(raw))
        entries = archive.infolist()
        if len(entries) > 150: raise ValueError("Project supports up to 150 files.")
        total, seen = 0, set()
        for entry in entries:
            name = safe_path(entry.filename.rstrip("/"))
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise ValueError("Project links and encrypted files are not supported.")
            if entry.is_dir(): continue
            if name.casefold() in seen: raise ValueError("Project has duplicate file paths.")
            seen.add(name.casefold())
            total += entry.file_size
            if entry.file_size > 10000000 or total > 20000000:
                raise ValueError("Project exceeds the 20 MB extracted limit or 10 MB file limit.")
            data = archive.read(entry)
            if len(data) != entry.file_size: raise ValueError("Invalid project file size.")
            files[name] = data
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError("Upload a readable, unencrypted LaTeX project ZIP.") from exc
    if not files: raise ValueError("Project ZIP is empty.")
    folded = {name.casefold() for name in files}
    if any(parent.as_posix().casefold() in folded for name in files for parent in PurePosixPath(name).parents if str(parent) != "."):
        raise ValueError("Project has a file where a parent directory is required.")
    candidates = []
    for name, data in files.items():
        if name.lower().endswith(".tex"):
            try:
                if re.search(r"\\documentclass\b", uncomment(data.decode("utf-8-sig"))): candidates.append(name)
            except UnicodeError: pass
    if requested:
        main = safe_path(requested)
        if main not in files: raise ValueError("The selected main .tex file is not in the project.")
    elif len(candidates) == 1: main = candidates[0]
    elif "main.tex" in candidates: main = "main.tex"
    else: raise ValueError("Specify the main .tex file path. Candidates: " + ", ".join(candidates[:8]))
    if not main.lower().endswith(".tex"): raise ValueError("The main file must end in .tex.")
    if len(files[main]) > 512000: raise ValueError("Main source exceeds 500 KB.")
    source = files[main].decode("utf-8-sig")
    # Exports commonly wrap the whole project in one directory. Preserve paths
    # relative to its actual root so \input{skills} and local fonts still resolve.
    prefixes = {name.split("/", 1)[0] for name in files}
    if len(prefixes) == 1 and all("/" in name for name in files):
        prefix = next(iter(prefixes)) + "/"
        files = {name[len(prefix):]: data for name, data in files.items()}
        main = main[len(prefix):]
    return source, main, files


def load_options(root):
    path = root / "project.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"engine": "auto", "main_file": "main.tex", "files": []}


def store_options(root, engine="auto", main_file="main.tex", files=None):
    if engine not in ENGINES: raise ValueError("Choose auto, pdfLaTeX, XeLaTeX, or LuaLaTeX.")
    manifest = {}
    for name, data in (files or {}).items():
        name = safe_path(name)
        path = root / "project" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest[name] = digest(data.decode("latin1"))
    (root / "project.json").write_text(json.dumps({"engine": engine, "main_file": safe_path(main_file), "files": list(manifest), "hashes": manifest}), encoding="utf-8")


def project_files(root):
    options = load_options(root)
    result = {}
    for name in options["files"]:
        name = safe_path(name)
        path = root / "project" / name
        if path.is_symlink(): raise ValueError("Project symlinks are not supported.")
        data = path.read_bytes()
        if digest(data.decode("latin1")) != options.get("hashes", {}).get(name):
            raise ValueError("Project asset integrity check failed. Import the project again.")
        result[name] = data
    return result


def proposal(source):
    result, changes, issues = source, [], []
    masked = re.sub(r"(?<!\\)%[^\r\n]*", lambda m: " " * len(m[0]), source)
    body = masked.find(r"\begin{document}")
    definitions = re.finditer(r"\\(?:newcommand|renewcommand|providecommand)\*?\s*\{\\([A-Za-z]+)\}\s*\[(\d)\]", masked)
    edits = []
    for definition in definitions:
        name, count = definition[1], int(definition[2])
        if not re.search(r"heading", name, re.I) or not 1 <= count <= 8: continue
        if re.match(r"\s*\[", masked[definition.end():]): continue  # Optional first argument.
        for call in re.finditer(r"\\" + re.escape(name) + r"\b", masked[max(0, body):]):
            cursor = max(0, body) + call.end()
            supplied, last = 0, cursor
            try:
                while supplied < count:
                    whitespace = re.match(r"\s*", masked[cursor:])[0]
                    cursor += len(whitespace)
                    if masked[cursor:cursor + 1] != "{": break
                    cursor = group_end(source, cursor) + 1
                    supplied += 1; last = cursor
            except ValueError: continue
            if supplied == count - 1 and re.match(r"\s*\\(?:resumeItemListStart|begin\s*\{itemize\})", masked[last:]):
                line = source.count("\n", 0, last) + 1
                reason = f"\\{name} requires {count} arguments; this call provides {supplied}. An empty final argument preserves the existing text."
                edits.append((last, last, "\n  {}", line, reason))
                issues.append({"line": line, "message": reason, "suggestion": "Review the missing field, or accept an empty final argument."})
    pattern = re.compile(r"(\\section\*?\{Certifications[^\n]*\}\s*\\resumeSubHeadingListStart\s*)(\\resumeItemListStart)")
    for match in pattern.finditer(masked):
        line = source.count("\n", 0, match.start(2)) + 1
        edits.append((match.start(2), match.start(2), "\\item[]\n", line, "The nested Certifications list needs a parent item."))
        issues.append({"line": line, "message": "The nested Certifications list needs a parent item.", "suggestion": "Review the proposed empty parent item before importing a repaired revision."})
    for left, right, replacement, line, reason in sorted(edits, reverse=True):
        result = result[:left] + replacement + result[right:]
        changes.append({"line": line, "before": source[max(0, left - 100):right + 80], "after": source[max(0, left - 100):left] + replacement + source[right:right + 80], "reason": reason})
    return {"source": result, "changes": list(reversed(changes)), "issues": issues}


def compatibility(source, options, root=None):
    from services.latex_compiler import detect_engine
    try:
        categories = list(category_regions(source)); error = None
    except ValueError as exc:
        categories, error = [], str(exc)
    detection = source
    if root:
        for name in options["files"]:
            if name != options["main_file"] and Path(name).suffix.lower() in {".tex", ".sty", ".cls", ".ltx"}:
                path = root / "project" / safe_path(name)
                if path.is_file() and not path.is_symlink():
                    detection += "\n" + path.read_text(encoding="utf-8", errors="replace")
    return {"engine": options["engine"], "detected_engine": detect_engine(detection), "main_file": options["main_file"],
            "project_files": options["files"], "mapping_supported": bool(categories), "mapping_error": error,
            "issues": proposal(source)["issues"]}
