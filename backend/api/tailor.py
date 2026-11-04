"""Single skills-only LaTeX tailoring API. No whole-resume rewrite fallback."""
import re
import json
from io import BytesIO
from collections import Counter
import zipfile
import shutil
import tempfile
from pathlib import Path
import fitz
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text
from core.workspace import get_workspace_owner
from db.models import LatexMaster, LatexTailoringRun, ConfirmedSkill, WorkspaceSettings
from db.session import get_db
from services.latex_compiler import compile_source, compiler_status, directory, CompileError
from tailoring.latex import category_regions, digest, plain_text, patch, uncomment, skill_section
from tailoring.selection import select, contains
from tailoring.compatibility import ENGINES, unpack_project, load_options, store_options, project_files, compatibility, proposal

router = APIRouter(prefix="/tailor", tags=["LaTeX tailor"])


def owned(db, model, identifier, owner):
    item = db.query(model).filter_by(id=identifier, user_id=owner.id).first()
    if not item:
        raise HTTPException(404, "Resume revision or tailoring run not found.")
    return item


def master_json(item):
    root = directory("masters", item.id)
    options = load_options(root)
    comparison = root / "comparison.json"
    ai_report = root / "ai-repair.json"
    if not ai_report.exists(): ai_report = root / "ai-repair-last.json"
    return {"id": item.id, "filename": item.filename, "source_hash": item.source_hash,
            "categories": item.categories, "status": item.status, "baseline_pages": item.baseline_pages,
            "diagnostics": item.diagnostics, "created_at": item.created_at.isoformat(),
            "pdf_url": f"/tailor/masters/{item.id}/pdf" if item.baseline_pages else None,
            "reference_pdf_url": f"/tailor/masters/{item.id}/reference" if (root / "reference.pdf").exists() else None,
            "recovery_pdf_url": f"/tailor/masters/{item.id}/preview" if (root / "recovery.pdf").exists() else None,
            "project_url": f"/tailor/masters/{item.id}/project" if options["files"] else None,
            "compatibility": compatibility(item.source, options, root),
            "ai_repair": json.loads(ai_report.read_text(encoding="utf-8")) if ai_report.exists() else None,
            "comparison": json.loads(comparison.read_text(encoding="utf-8")) if comparison.exists() else None}


def compile_for_master(master, source, destination, recovery=False):
    root = directory("masters", master.id)
    options = load_options(root)
    kwargs = {}
    if options["engine"] != "auto": kwargs["engine"] = options["engine"]
    if options["files"]:
        try: project_files(root)
        except (ValueError, OSError) as exc: raise CompileError(str(exc)) from exc
        kwargs.update(project=root / "project", main_file=options["main_file"])
    if recovery: kwargs["recovery"] = True
    return compile_source(source, destination, **kwargs)


def save_master(source, filename, reference_bytes, engine, main_file, files, db, owner):
    if engine not in ENGINES: raise HTTPException(422, "Choose auto, pdflatex, xelatex, or lualatex.")
    if len(source.encode("utf-8")) > 512000: raise HTTPException(413, "Master source exceeds 500 KB.")
    if not re.search(r"\\(?:documentclass\b|begin\s*\{document\}|input\b|include\b)", source):
        raise HTTPException(422, "Provide the complete LaTeX document, including its preamble, or upload a full project ZIP.")
    try:
        categories = list(category_regions(source))
    except ValueError:
        categories = []  # Import and preview unfamiliar templates before mapping.
    if reference_bytes:
        if len(reference_bytes) > 10000000: raise HTTPException(413, "Reference PDF exceeds 10 MB.")
        try:
            with fitz.open(stream=reference_bytes, filetype="pdf") as pdf:
                if not len(pdf) or pdf.needs_pass: raise ValueError("Empty or password-protected PDF")
        except Exception as exc: raise HTTPException(422, "Reference must be a readable PDF.") from exc
    item = LatexMaster(user_id=owner.id, filename=Path(filename.replace("\\", "/")).name,
        source=source, source_hash=digest(source), categories=categories, status="draft")
    db.add(item); db.flush()
    root = directory("masters", item.id)
    (root / "master.tex").write_bytes(source.encode("utf-8"))
    store_options(root, engine, main_file, files)
    if reference_bytes: (root / "reference.pdf").write_bytes(reference_bytes)
    db.commit()
    return master_json(item)


def project_download(master, source):
    root = directory("masters", master.id)
    options = load_options(root)
    files = project_files(root)
    files[options["main_file"]] = source.encode("utf-8")
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items(): archive.writestr(name, raw)
    return Response(stream.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="resume-project.zip"'})


@router.get("/masters/{identifier}/compatibility")
def inspect_compatibility(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    item = owned(db, LatexMaster, identifier, owner)
    root = directory("masters", item.id)
    return compatibility(item.source, load_options(root), root)


@router.post("/masters/{identifier}/preview")
def preview_master(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    item = owned(db, LatexMaster, identifier, owner)
    root = directory("masters", item.id)
    try:
        info = compile_for_master(item, item.source, root / "recovery.pdf", recovery=True)
    except CompileError as exc:
        (root / "recovery.pdf").unlink(missing_ok=True)
        item.diagnostics = exc.diagnostics; db.commit()
        raise HTTPException(422, "Recovery could not produce a readable PDF. Use Suggest repairs or Edit as new revision. " + str(exc)) from exc
    item.diagnostics = "Recovery preview only — not approved for activation. " + ("Source errors remain.\n" if info.get("has_errors") else "Run Compile baseline for validation.\n") + info["diagnostics"]
    db.commit()
    return master_json(item)


@router.post("/masters/{identifier}/repair-proposal")
def repair_proposal(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    item = owned(db, LatexMaster, identifier, owner)
    return proposal(item.source)


class RepairDecision(BaseModel):
    accept: bool = False


@router.post("/masters/{identifier}/repair")
def accept_repair(identifier: str, request: RepairDecision, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    if not request.accept: raise HTTPException(422, "Review and explicitly accept the proposed changes first.")
    item = owned(db, LatexMaster, identifier, owner)
    suggestion = proposal(item.source)
    if not suggestion["changes"]: raise HTTPException(409, "No automatic repair is available. Use Edit as new revision to review the source manually.")
    root = directory("masters", item.id)
    options = load_options(root)
    reference = (root / "reference.pdf").read_bytes() if (root / "reference.pdf").exists() else None
    return save_master(suggestion["source"], item.filename.removesuffix(".tex") + "-repaired.tex", reference,
                       options["engine"], options["main_file"], project_files(root), db, owner)


@router.post("/masters/{identifier}/ai-repair")
def ai_repair_master(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    item = owned(db, LatexMaster, identifier, owner)
    if db.get_bind().dialect.name == "postgresql":
        locked = db.execute(text("SELECT pg_try_advisory_xact_lock(hashtext(:scope))"), {"scope": "latex-ai-repair:" + identifier}).scalar()
        if not locked: raise HTTPException(409, "A Groq repair is already running for this revision.")
    if digest(item.source) != item.source_hash:
        raise HTTPException(409, "Master source integrity check failed.")
    root = directory("masters", item.id)
    try: project_files(root)
    except (ValueError, OSError) as exc: raise HTTPException(409, str(exc)) from exc
    # Repeated compilation of the same original should reopen its verified
    # repair instead of spending more tokens or creating duplicate revisions.
    for candidate in db.query(LatexMaster).filter(LatexMaster.user_id == owner.id, LatexMaster.status.in_(["compiled", "active"])).order_by(LatexMaster.created_at.desc()).limit(100):
        candidate_root = directory("masters", candidate.id)
        audit = candidate_root / "ai-repair.json"
        validation = candidate_root / "baseline.validation.json"
        if not audit.exists() or not validation.exists() or not (candidate_root / "baseline.pdf").exists(): continue
        try:
            cached = json.loads(audit.read_text(encoding="utf-8"))
            validated = json.loads(validation.read_text(encoding="utf-8"))
        except (ValueError, OSError): continue
        if validated.get("has_errors") or validated.get("recovery") or validated.get("source_hash") != candidate.source_hash or digest(candidate.source) != candidate.source_hash: continue
        if cached.get("original_id") != item.id:
            prior = db.query(LatexMaster).filter_by(id=cached.get("original_id"), user_id=owner.id).first()
            if not prior or digest(prior.source) != prior.source_hash or prior.source.replace("\r\n", "\n") != item.source.replace("\r\n", "\n"): continue
            prior_root = directory("masters", prior.id)
            try:
                if load_options(prior_root) != load_options(root) or project_files(prior_root) != project_files(root): continue
                def reference_bytes(folder):
                    path = folder / "reference.pdf"
                    return path.read_bytes() if path.exists() else None
                if reference_bytes(prior_root) != reference_bytes(root): continue
            except (ValueError, OSError): continue
        project_files(candidate_root)
        return {**cached, "cached": True, "message": "Reused the verified compiled correction for the same source. No new Groq request was needed.", "master": master_json(candidate)}
    from tailoring.ai_repair import repair
    root = directory("masters", item.id)
    with tempfile.TemporaryDirectory(prefix="careeros-ai-repair-") as temporary:
        work = Path(temporary)
        report, source, info = repair(item.source, lambda value, destination: compile_for_master(item, value, destination), work,
            initial_diagnostics=item.diagnostics if item.status == "draft" and item.diagnostics else None)
        report["original_id"] = item.id
        audit_root = root / "repair-attempts"
        audit_root.mkdir(exist_ok=True)
        for artifact in work.glob("attempt-*"):
            if artifact.is_file(): shutil.copyfile(artifact, audit_root / artifact.name)
        if source is None:
            (root / "ai-repair-last.json").write_text(json.dumps(report), encoding="utf-8")
            return {**report, "master": None}
        options = load_options(root)
        reference = (root / "reference.pdf").read_bytes() if (root / "reference.pdf").exists() else None
        filename = item.filename.removesuffix(".tex") + "-ai-repaired.tex"
        imported = save_master(source, filename, reference, options["engine"], options["main_file"], project_files(root), db, owner)
        repaired = owned(db, LatexMaster, imported["id"], owner)
        target = directory("masters", repaired.id)
        shutil.copyfile(work / "candidate.pdf", target / "baseline.pdf")
        metadata = work / "candidate.build.json"
        if metadata.exists(): shutil.copyfile(metadata, target / "baseline.build.json")
        (target / "baseline.validation.json").write_text(json.dumps({"overflow": info["overflow"], "has_errors": info.get("has_errors", False), "source_hash": repaired.source_hash}), encoding="utf-8")
        (target / "ai-repair.json").write_text(json.dumps(report), encoding="utf-8")
        repaired.status, repaired.baseline_pages = "compiled", info["pages"]
        repaired.diagnostics = ("Overflow warning: review the baseline.\n" if info["overflow"] else "") + "Groq-assisted syntax repair; review the source diff and PDF before activation.\n" + info["diagnostics"]
        db.commit()
        return {**report, "master": master_json(repaired)}


def run_json(item):
    # A complete project download is useful even for a single-file resume.
    return {"id": item.id, "master_id": item.master_id, "label": item.label,
            "candidates": item.candidates, "status": item.status, "changes": item.changes,
            "job_description": item.job_description,
            "diagnostics": item.diagnostics, "created_at": item.created_at.isoformat(),
            "pdf_url": f"/tailor/runs/{item.id}/pdf" if item.status == "ready" else None,
            "source_url": f"/tailor/runs/{item.id}/source" if item.source is not None else None,
            "project_url": f"/tailor/runs/{item.id}/project" if item.status == "ready" else None}


@router.get("/status")
def status(owner=Depends(get_workspace_owner)):
    return compiler_status()


@router.get("/masters")
def masters(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    return [master_json(m) for m in db.query(LatexMaster).filter_by(user_id=owner.id).order_by(LatexMaster.created_at.desc())]


@router.post("/masters/paste")
def paste_master(source: str = Form(...), filename: str = Form("pasted-resume.tex"),
                 reference: UploadFile | None = File(None), db: Session = Depends(get_db),
                 owner=Depends(get_workspace_owner), engine: str = Form("auto"), based_on: str | None = Form(None)):
    if not source.strip():
        raise HTTPException(422, "Paste your complete LaTeX source first.")
    if len(source.encode("utf-8")) > 512000:
        raise HTTPException(413, "Master source exceeds 500 KB.")
    if not filename.lower().endswith(".tex"):
        raise HTTPException(422, "Use a revision filename ending in .tex.")
    files, main_file, reference_bytes = {}, "main.tex", reference.file.read(10000001) if reference else None
    if based_on:
        original = owned(db, LatexMaster, based_on, owner)
        root = directory("masters", original.id)
        options = load_options(root)
        files, main_file = project_files(root), options["main_file"]
        if not reference_bytes and (root / "reference.pdf").exists(): reference_bytes = (root / "reference.pdf").read_bytes()
    return save_master(source, filename, reference_bytes, engine, main_file, files, db, owner)


@router.post("/masters")
def import_master(file: UploadFile = File(...), reference: UploadFile | None = File(None),
                  db: Session = Depends(get_db), owner=Depends(get_workspace_owner),
                  engine: str = Form("auto"), main_file: str = Form("")):
    name = file.filename or ""
    if not name.lower().endswith((".tex", ".zip")):
        raise HTTPException(422, "Upload a UTF-8 .tex file or a complete LaTeX project ZIP.")
    limit = 10000000 if name.lower().endswith(".zip") else 512000
    raw = file.file.read(limit + 1)
    if len(raw) > limit: raise HTTPException(413, "Source exceeds the 500 KB .tex or 10 MB ZIP limit.")
    files, entry = {}, "main.tex"
    try:
        if name.lower().endswith(".zip"):
            source, entry, files = unpack_project(raw, main_file)
            name = Path(entry).name
        else: source = raw.decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return save_master(source, name, reference.file.read(10000001) if reference else None, engine, entry, files, db, owner)


@router.post("/masters/{identifier}/compile")
def compile_master(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    item = owned(db, LatexMaster, identifier, owner)
    if item.status == "active":
        return master_json(item)
    try:
        info = compile_for_master(item, item.source, directory("masters", item.id) / "baseline.pdf")
        if info.get("has_errors"): raise CompileError("The baseline still has source errors. Use the recovery preview to review them.", info["diagnostics"])
        item.baseline_pages, item.status = info["pages"], "compiled"
        item.diagnostics = ("Overflow warning: review the baseline.\n" if info["overflow"] else "") + info["diagnostics"]
        root = directory("masters", item.id)
        (root / "baseline.validation.json").write_text(json.dumps({"overflow": info["overflow"], "has_errors": info.get("has_errors", False), "source_hash": item.source_hash}), encoding="utf-8")
        if (root / "reference.pdf").exists():
            with fitz.open(root / "reference.pdf") as reference:
                text = "\n".join(reference.load_page(i).get_text() for i in range(min(20, len(reference))))
                words = Counter(re.findall(r"\w+", text.casefold()))
                generated = Counter(re.findall(r"\w+", info["text"].casefold()))
                missing = list((words - generated).elements())
                comparison = {"reference_pages": len(reference), "baseline_pages": info["pages"],
                    "reference_text_coverage": sum((words & generated).values()) / sum(words.values()) if words else None,
                    "missing_reference_excerpt": " ".join(missing[:60]),
                    "note": "Text coverage only (up to 20 reference pages); compare the side-by-side PDFs for layout and ordering."}
            (root / "comparison.json").write_text(json.dumps(comparison), encoding="utf-8")
    except CompileError as exc:
        item.diagnostics = exc.diagnostics
        item.status, item.baseline_pages = "draft", None
        db.commit()
        raise HTTPException(503, str(exc)) from exc
    db.commit()
    return master_json(item)


@router.get("/master")
def current_master(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    query = db.query(LatexMaster).filter_by(user_id=owner.id)
    item = query.filter_by(status="active").order_by(LatexMaster.created_at.desc()).first()
    if not item:
        item = query.filter_by(status="compiled").order_by(LatexMaster.created_at.desc()).first()
    return master_json(item) if item else None


@router.post("/compile-resume")
def compile_resume(file: UploadFile | None = File(None), source: str | None = Form(None),
                   reference: UploadFile | None = File(None), db: Session = Depends(get_db),
                   owner=Depends(get_workspace_owner)):
    if (file is not None) == bool(source and source.strip()):
        raise HTTPException(422, "Upload a LaTeX file or paste its complete code, then compile.")
    if file is not None:
        imported = import_master(file, reference, db, owner, engine="auto", main_file="")
    else:
        imported = paste_master(source, "master-resume.tex", reference, db, owner, engine="auto", based_on=None)
    try:
        compiled = compile_master(imported["id"], db, owner)
        return {"master": compiled, "repaired": False, "message": "Resume compiled."}
    except HTTPException as error:
        if error.status_code != 503: raise
    result = ai_repair_master(imported["id"], db, owner)
    if result.get("master"):
        return {"master": result["master"], "repaired": True, "message": "Resume compiled after automatic LaTeX correction."}
    if result["status"] == "not_needed":
        return {"master": compile_master(imported["id"], db, owner), "repaired": False, "message": "Resume compiled."}
    raise HTTPException(503 if result["status"] == "unavailable" else 422, result["message"])


@router.post("/masters/{identifier}/activate")
def activate_master(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    db.query(WorkspaceSettings).filter_by(id=1).with_for_update().first()
    item = owned(db, LatexMaster, identifier, owner)
    if item.status not in {"compiled", "active"} or not item.categories:
        raise HTTPException(409, "This PDF is ready to download, but its Skills categories could not be read for automatic tailoring. Use clearly labeled categories in the Skills section.")
    try: category_regions(item.source)
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc
    if not item.baseline_pages or not (directory("masters", item.id) / "baseline.pdf").exists():
        raise HTTPException(409, "Compile and review the baseline PDF before activating this master.")
    root = directory("masters", item.id)
    validation_path = root / "baseline.validation.json"
    if not validation_path.exists(): validation_path = root / "baseline.build.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8")) if validation_path.exists() else {}
    if validation.get("has_errors") or validation.get("recovery") or digest(item.source) != item.source_hash:
        raise HTTPException(409, "This baseline has not passed validation. Compile it again before activation.")
    if validation.get("overflow") or (item.diagnostics or "").startswith("Overflow warning:"):
        raise HTTPException(409, "Correct baseline overflow before activating this source for automatic tailoring.")
    db.query(LatexMaster).filter_by(user_id=owner.id, status="active").update({"status": "archived"})
    item.status = "active"
    db.commit()
    return master_json(item)


@router.get("/masters/{identifier}/{kind}")
def master_file(identifier: str, kind: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    item = owned(db, LatexMaster, identifier, owner)
    if kind == "source":
        return Response(item.source, media_type="text/plain", headers={"Content-Disposition": 'attachment; filename="master.tex"'})
    if kind == "project": return project_download(item, item.source)
    filenames = {"pdf": "baseline.pdf", "reference": "reference.pdf", "preview": "recovery.pdf"}
    if kind not in filenames:
        raise HTTPException(404)
    path = directory("masters", item.id) / filenames[kind]
    if not path.exists():
        raise HTTPException(404, "PDF is not available yet.")
    return FileResponse(path, media_type="application/pdf")


class AnalyzeRequest(BaseModel):
    master_id: str
    job_description: str = Field(min_length=50, max_length=50000)
    label: str = Field(default="Tailored resume", min_length=1, max_length=150)
    use_ai: bool = False


@router.post("/analyze")
def analyze(request: AnalyzeRequest, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    master = owned(db, LatexMaster, request.master_id, owner)
    if master.status != "active":
        raise HTTPException(409, "Activate the reviewed master first.")
    known = {s.canonical: {"name": s.name, "category": s.category} for s in db.query(ConfirmedSkill).filter_by(user_id=owner.id)}
    try:
        candidates, mode = select(request.job_description, plain_text(master.source), master.categories, known, request.use_ai)
    except Exception:
        raise HTTPException(503, "AI extraction is unavailable. Retry with the local dictionary; no paid fallback was used.")
    item = LatexTailoringRun(user_id=owner.id, master_id=master.id, job_description=request.job_description,
                             label=request.label, candidates=candidates, diagnostics=f"Extraction: {mode}")
    db.add(item)
    db.commit()
    return run_json(item)


class SkillDecision(BaseModel):
    canonical: str = Field(max_length=80)
    category: str = Field(max_length=100)


@router.post("/runs/{identifier}/reanalyze")
def reanalyze(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    previous = owned(db, LatexTailoringRun, identifier, owner)
    master = db.query(LatexMaster).filter_by(user_id=owner.id, status="active").first()
    if not master:
        raise HTTPException(409, "Activate your reviewed master first.")
    return analyze(AnalyzeRequest(master_id=master.id, job_description=previous.job_description, label=previous.label), db, owner)


class PrepareRequest(BaseModel):
    confirmed_skills: list[SkillDecision] = Field(default_factory=list, max_length=5)


def protected_text(text: str, source: str) -> str:
    _, _, title, heading, _ = skill_section(source)
    def title_pattern(value):
        return r"\s+".join(re.escape(word) for word in plain_text(value).strip().split())
    start = re.search(r"(?im)^\s*" + title_pattern(title) + r"\s*$", text)
    if not start:
        raise CompileError("Cannot validate the Skills boundary in the PDF text.")
    end = re.search(r"(?im)^\s*" + title_pattern(heading) + r"\s*$", text[start.end():]) if heading else None
    if heading and not end:
        raise CompileError("Cannot validate the protected PDF section boundary.")
    return re.sub(r"\s+", "", text[:start.start()] + (text[start.end() + end.start():] if end else ""))


def validate_pdf_content(generated, baseline, source, changes):
    try:
        skill_section(source)
    except ValueError:
        # For custom headings, preserve the entire PDF text and subtract only
        # exact inserted values. Ambiguous extraction requires manual review.
        if not category_regions(source): raise CompileError("Skills mapping is unavailable.")
        normalized = re.sub(r"\s+", "", generated)
        for change in changes:
            before, after = change["before"].rstrip(), change["after"].rstrip()
            if not after.startswith(before): raise CompileError("Unexpected mapped value edit.")
            inserted = re.sub(r"\s+", "", plain_text(after[len(before):]))
            if not inserted or len(re.findall(re.escape(inserted), normalized, re.I)) != 1:
                raise CompileError("Cannot uniquely verify mapped skill additions in the PDF. Review this template manually.")
            normalized = re.sub(re.escape(inserted), "", normalized, count=1, flags=re.I)
        if normalized != re.sub(r"\s+", "", baseline):
            raise CompileError("Original PDF text changed outside the explicit additions. Output was not published.")
        return
    if protected_text(generated, source) != protected_text(baseline, source):
        raise CompileError("Protected PDF content differs from baseline. Output was not published.")


@router.post("/runs/{identifier}/prepare")
def prepare(identifier: str, request: PrepareRequest, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    item = owned(db, LatexTailoringRun, identifier, owner)
    db.refresh(item, with_for_update=True)
    if item.status == "ready":
        raise HTTPException(409, "Already prepared. Create another analysis for different additions.")
    master = owned(db, LatexMaster, item.master_id, owner)
    if digest(master.source) != master.source_hash:
        raise HTTPException(409, "Master source integrity check failed.")
    candidates = {s["canonical"]: s for s in item.candidates}
    additions, seen = [], set()
    for decision in request.confirmed_skills:
        if decision.canonical not in candidates or decision.canonical in seen or decision.category not in master.categories:
            raise HTTPException(422, "Confirm only unique selected skills and existing categories.")
        seen.add(decision.canonical)
        additions.append({"name": candidates[decision.canonical]["name"], "category": decision.category})
    try:
        baseline_path = directory("masters", master.id) / "baseline.pdf"
        if not baseline_path.exists():
            raise CompileError("Master baseline PDF is missing. Recompile it.")
        with fitz.open(baseline_path) as baseline:
            baseline_text = "\n".join(page.get_text() for page in baseline)
        omitted = []
        while True:
            source, changes = patch(master.source, additions)
            root = directory("runs", item.id)
            info = compile_for_master(master, source, root / "candidate.pdf")
            if info.get("has_errors"):
                raise CompileError("Tailored output has source errors and cannot be published.", info["diagnostics"])
            if info["pages"] <= master.baseline_pages and not info["overflow"]:
                break
            if not additions:
                raise CompileError("Baseline has overflow. Correct the master before automatic preparation.")
            omitted.insert(0, additions.pop())
        validate_pdf_content(info["text"], baseline_text, master.source, changes)
        for addition in additions:
            if not contains(info["text"], addition["name"]):
                raise CompileError(f"Cannot verify skill in PDF: {addition['name']}")
        (root / "candidate.pdf").replace(root / "resume.pdf")
        (root / "resume.tex").write_bytes(source.encode("utf-8"))
        item.source, item.changes, item.status = source, changes, "ready"
        item.diagnostics = "Validated source and PDF. " + ("Omitted for fit: " + ", ".join(s["name"] for s in omitted) if omitted else "All confirmed additions fit.")
        for decision in request.confirmed_skills:
            skill = db.query(ConfirmedSkill).filter_by(user_id=owner.id, canonical=decision.canonical).first()
            if skill:
                skill.category = decision.category
            else:
                db.add(ConfirmedSkill(user_id=owner.id, canonical=decision.canonical, name=candidates[decision.canonical]["name"], category=decision.category))
    except (CompileError, ValueError) as exc:
        item.status, item.diagnostics = "failed", str(exc)
        db.commit()
        raise HTTPException(422 if isinstance(exc, ValueError) else 503, str(exc)) from exc
    db.commit()
    return run_json(item)


@router.get("/runs")
def runs(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    return [run_json(r) for r in db.query(LatexTailoringRun).filter_by(user_id=owner.id).order_by(LatexTailoringRun.created_at.desc())]


@router.get("/runs/{identifier}/{kind}")
def run_file(identifier: str, kind: str, download: bool = False, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    item = owned(db, LatexTailoringRun, identifier, owner)
    if item.status != "ready":
        raise HTTPException(409, "Artifact has not passed validation.")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", item.label).strip("-")[:80] or "resume"
    if kind == "source":
        return Response(item.source, media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{slug}.tex"'})
    if kind == "project": return project_download(owned(db, LatexMaster, item.master_id, owner), item.source)
    if kind != "pdf":
        raise HTTPException(404)
    path = directory("runs", item.id) / "resume.pdf"
    if not path.exists():
        raise HTTPException(404, "Artifact file is missing.")
    return FileResponse(path, media_type="application/pdf", filename=f"{slug}.pdf",
                        content_disposition_type="attachment" if download else "inline")


@router.get("/versions")
def legacy_versions():
    return []


@router.post("/apply")
def retired_apply():
    raise HTTPException(410, "Whole-resume tailoring is retired. Use /tailor/runs/{id}/prepare.")
