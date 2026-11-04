from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Cookie, Query
from fastapi.responses import FileResponse
from fastapi.background import BackgroundTasks
from sqlalchemy.orm import Session
from db.session import get_db
from db.models import ResumeVersion
from services.text_extraction import extract_text
from services.vector_store_service import embed_and_upsert_resume
from core.workspace import get_workspace_owner as get_current_user
from resume_parser.pipeline import parse_resume as parse_resume_pipeline
from typing import Optional
from datetime import datetime
import logging

router = APIRouter(prefix="/resumes", tags=["Resumes"])
logger = logging.getLogger(__name__)

def _reconstruct_raw_text(parsed_json: dict) -> str:
    parts = []
    contact = parsed_json.get("contact", {})
    if contact:
        parts.append(f"Name: {contact.get('name') or ''}")
        parts.append(f"Email: {contact.get('email') or ''}")
        parts.append(f"Phone: {contact.get('phone') or ''}")
        parts.append(f"Location: {contact.get('location') or ''}")
        if contact.get('links'):
            parts.append(f"Links: {', '.join(contact.get('links') or [])}")
    
    summary = parsed_json.get("summary")
    if summary:
        parts.append(f"Summary:\n{summary}")
        
    skills = parsed_json.get("skills")
    if skills:
        parts.append(f"Skills: {', '.join(skills)}")
        
    experience = parsed_json.get("experience", [])
    if experience:
        parts.append("Work Experience:")
        for exp in experience:
            parts.append(f"- {exp.get('title') or ''} at {exp.get('company') or ''} ({exp.get('start_date') or ''} - {exp.get('end_date') or ''})")
            for bp in exp.get('bullet_points') or []:
                parts.append(f"  * {bp}")
                
    projects = parsed_json.get("projects", [])
    if projects:
        parts.append("Projects:")
        for proj in projects:
            parts.append(f"- {proj.get('name') or ''} (Technologies: {', '.join(proj.get('technologies') or [])})")
            for b in proj.get('bullets') or []:
                parts.append(f"  * {b}")
                
    certs = parsed_json.get("certifications", [])
    if certs:
        parts.append(f"Certifications: {', '.join(certs)}")
        
    return "\n".join(parts)


def parse_resume_hybrid(file_bytes: bytes, filename: str) -> dict:
    """
    Hybrid Resume Parser:
    1. First checks if the file is a direct image (PNG/JPG) or a scanned PDF.
       If so, skips text parsing and triggers the Groq Vision LLM parser.
    2. Otherwise, tries to parse the resume using the custom modular pipeline software.
    3. Runs quality audits to check if key sections (experience, projects, phone, email) were extracted successfully.
    4. If any section is incomplete but exists in the raw text, it triggers the AI Agent Parser as a fallback/healing mechanism.
    5. If the modular software is 100% complete, it maps the modular schema to the clean flat schema.
    """
    from resume_parser.pipeline import parse_resume as parse_resume_pipeline
    from services.text_extraction import extract_text, is_image_file, render_pdf_to_images, check_pdf_layout
    from agents.resume_parser import parse_resume as parse_resume_agent, parse_resume_vision
    import logging
    import mimetypes
    
    local_logger = logging.getLogger("parse_resume_hybrid")

    # Step 0.1: Check direct image
    if is_image_file(filename):
        local_logger.info(f"Direct image uploaded: {filename}. Triggering Vision Parser.")
        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "image/png"
        ai_result = parse_resume_vision(file_bytes, mime_type)
        ai_result["_raw"] = _reconstruct_raw_text(ai_result)
        ai_result["formatting_metadata"] = {
            "has_columns": False,
            "has_tables": False,
            "is_scanned_pdf": True
        }
        return ai_result

    # Step 0.2: Check scanned PDF
    layout_info = check_pdf_layout(file_bytes)
    if layout_info.get("is_scanned_pdf"):
        local_logger.info(f"Scanned PDF uploaded: {filename}. Rendering to image and triggering Vision Parser.")
        images = render_pdf_to_images(file_bytes)
        if images:
            ai_result = parse_resume_vision(images[0], "image/png")
            ai_result["_raw"] = _reconstruct_raw_text(ai_result)
            ai_result["formatting_metadata"] = {
                "has_columns": False,
                "has_tables": False,
                "is_scanned_pdf": True
            }
            return ai_result

    # Step 1: Run our software pipeline first
    try:
        software_result = parse_resume_pipeline(file_bytes, filename, include_raw=True)
    except Exception as e:
        local_logger.warning(f"Software modular pipeline parser failed: {e}. Falling back to AI parser.")
        software_result = None

    # Step 2: Heuristic audit for 100% completeness
    is_complete = True
    if not software_result:
        is_complete = False
    else:
        raw_text = software_result.get("_raw", "").lower()
        
        # Check experience completeness
        has_experience_section = "experience" in software_result.get("original_section_headings", {})
        parsed_experience = software_result.get("experience", {})
        experience_entries = parsed_experience.get("entries", []) if isinstance(parsed_experience, dict) else parsed_experience
        if has_experience_section and not experience_entries:
            is_complete = False
            local_logger.info("Software parser missed work experience entries. Falling back to AI.")
            
        # Check projects completeness
        has_projects_section = "projects" in software_result.get("original_section_headings", {})
        parsed_projects = software_result.get("projects")
        if has_projects_section:
            if isinstance(parsed_projects, str) and parsed_projects.strip():
                import re
                proj_list = []
                current_p = None
                for line in [l.strip() for l in parsed_projects.split('\n') if l.strip()]:
                    is_b = bool(re.match(r'^[•\-\*\u2022\u2023\u25e6\u2043\u2219]', line))
                    if not is_b:
                        parts = line.split('|')
                        name = parts[0].strip()
                        techs = [t.strip() for t in parts[1].split(',')] if len(parts) > 1 else []
                        current_p = {'name': name, 'bullets': [], 'technologies': techs}
                        proj_list.append(current_p)
                    elif current_p:
                        b_text = re.sub(r'^[•\-\*\u2022\u2023\u25e6\u2043\u2219\s]+', '', line).strip()
                        if b_text:
                            current_p['bullets'].append(b_text)
                software_result["projects"] = proj_list
            elif not parsed_projects:
                is_complete = False
                local_logger.info("Software parser missed projects section. Falling back to AI.")

        # Check certifications completeness
        if "certification" in raw_text or "course" in raw_text:
            parsed_certs = software_result.get("certifications", [])
            if not parsed_certs:
                is_complete = False
                local_logger.info("Software parser missed certifications. Falling back to AI.")

        # Contact details: if missing, trigger AI fallback to ensure we get phone/email.
        contact = software_result.get("contact", {})
        if not contact.get("phone") or not contact.get("email"):
            is_complete = False
            local_logger.warning("Software parser missed phone/email. Falling back to AI.")

    # Step 3: If not 100% complete, fall back to the AI Agent Parser (blazing fast Llama 4 Scout on Groq)
    if not is_complete:
        local_logger.info("Software parser is incomplete. Triggering AI healing/fallback parser.")
        if software_result and software_result.get("_raw"):
            raw_text = software_result["_raw"]
        else:
            raw_text = extract_text(file_bytes, filename)
            
        ai_result = parse_resume_agent(raw_text)
        ai_result["_raw"] = raw_text
        ai_result["formatting_metadata"] = {
            "has_columns": False,
            "has_tables": False,
            "is_scanned_pdf": False
        }
        if software_result and software_result.get("metadata"):
            ai_result["metadata"] = software_result.get("metadata")
                
        from services.skill_manager import group_skills_into_categories
        raw_skills = ai_result.get("skills", [])
        if isinstance(raw_skills, list):
            ai_result["skills"] = {
                "all": raw_skills,
                "byCategory": group_skills_into_categories(raw_skills)
            }
        return ai_result

    # Step 4: Software parser succeeded 100%. Convert modular schema -> flat schema so the ATS scorer works perfectly!
    local_logger.info("Software parser completed successfully! Mapping schema.")
    flat_result = {
        "contact": {
            "name": software_result.get("contact", {}).get("name"),
            "email": software_result.get("contact", {}).get("email"),
            "phone": software_result.get("contact", {}).get("phone"),
            "location": software_result.get("contact", {}).get("location", {}).get("raw") if isinstance(software_result.get("contact", {}).get("location"), dict) else software_result.get("contact", {}).get("location"),
            "links": list(dict.fromkeys(
                [val for val in [
                    software_result.get("contact", {}).get("linkedin"),
                    software_result.get("contact", {}).get("github"),
                    software_result.get("contact", {}).get("portfolio")
                ] if val] +
                list(software_result.get("contact", {}).get("links") or [])
            ))
        },
        "skills": software_result.get("skills", {}),
        "experience": [
            {
                "company": entry.get("company"),
                "title": entry.get("title"),
                "start_date": entry.get("startDate"),
                "end_date": entry.get("endDate"),
                "bullet_points": entry.get("bullets", [])
            }
            for entry in (software_result.get("experience", {}).get("entries", []) if isinstance(software_result.get("experience"), dict) else software_result.get("experience", []))
        ],
        "education": [
            {
                "institution": edu.get("institution"),
                "degree": edu.get("degree"),
                "field": edu.get("field"),
                "graduation_date": edu.get("graduationDate"),
                "cgpa_or_percentage": edu.get("gpa")
            }
            for edu in software_result.get("education", [])
        ],
        "projects": [
            {
                "name": proj.get("name"),
                "bullets": proj.get("bullets", []),
                "technologies": proj.get("technologies", [])
            }
            for proj in (software_result.get("projects", []) if isinstance(software_result.get("projects"), list) else [])
        ],
        "certifications": software_result.get("certifications", []),
        "summary": software_result.get("summary"),
        "formatting_metadata": {
            "has_columns": software_result.get("metadata", {}).get("hasColumns", False),
            "has_tables": software_result.get("metadata", {}).get("hasTables", False),
            "is_scanned_pdf": software_result.get("metadata", {}).get("isScannedPdf", False)
        },
        "metadata": software_result.get("metadata", {}),
        "original_section_headings": software_result.get("original_section_headings", {}),
        "_raw": software_result.get("_raw")
    }
    return flat_result


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    source: str = Query("uploaded"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    try:
        user_id = current_user.id
        import os
        
        # 1. Read the file bytes
        file_bytes = await file.read()
        
        # 2. Parse using the hybrid pipeline
        parsed_json = parse_resume_hybrid(file_bytes, file.filename)
        raw_text = parsed_json.get("_raw", "")
        raw_text_clean = raw_text.strip().lower()
        
        # 3. Check for existing ResumeVersion records for this user and source
        existing_resumes = db.query(ResumeVersion).filter(
            ResumeVersion.user_id == user_id,
            ResumeVersion.source == source
        ).all()
        
        existing_record = None
        for r in existing_resumes:
            r_text = (r.raw_text or "").strip().lower()
            # Match 1: Exact raw text content match
            if r_text and r_text == raw_text_clean:
                existing_record = r
                break
            # Match 2: Same filename AND very similar text length
            if r.original_filename == file.filename and abs(len(r_text) - len(raw_text_clean)) < 50:
                existing_record = r
                break

        if existing_record:
            # Update existing entry in-place (no duplicate row, count stays same!)
            existing_record.original_filename = file.filename
            existing_record.raw_text = raw_text
            existing_record.structured_json = parsed_json
            existing_record.created_at = datetime.utcnow()
            db.commit()
            db.refresh(existing_record)
            resume_version = existing_record
            logger.info(f"Updated existing resume version '{resume_version.id}' for deduplication")
        else:
            # Check if same filename exists with DIFFERENT content -> auto-rename filename to preserve distinct resumes
            filename_matches = [r for r in existing_resumes if r.original_filename == file.filename]
            save_filename = file.filename
            if filename_matches:
                name_part, ext_part = os.path.splitext(file.filename)
                save_filename = f"{name_part} ({len(filename_matches)}){ext_part}"

            resume_version = ResumeVersion(
                user_id=user_id,
                source=source,
                original_filename=save_filename,
                raw_text=raw_text,
                structured_json=parsed_json
            )
            db.add(resume_version)
            db.commit()
            db.refresh(resume_version)

        # 3.5 Save the original uploaded file bytes to backend disk
        os.makedirs("uploads", exist_ok=True)
        ext = os.path.splitext(file.filename)[1].lower()
        with open(f"uploads/{resume_version.id}{ext}", "wb") as out_f:
            out_f.write(file_bytes)

        # 4. Chunk + embed the resume text into Qdrant for RAG search
        chunks_stored = 0
        try:
            chunks_stored = embed_and_upsert_resume(
                user_id=str(user_id),
                resume_version_id=str(resume_version.id),
                raw_text=raw_text,
                source_filename=file.filename,
            )
        except Exception as embed_err:
            logger.warning(f"Vector embedding failed (non-fatal): {embed_err}")
        
        return {
            "status": "success", 
            "resume_id": resume_version.id, 
            "parsed_data": parsed_json,
            "chunks_embedded": chunks_stored
        }
        
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/parse")
async def parse_resume_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Accepts resume file upload, runs the extraction + agent parser,
    and saves the result to the user profile if authenticated.
    Allows anonymous parsing.
    """
    try:
        # 1. Read the file bytes
        file_bytes = await file.read()
        
        # 2. Parse using the hybrid pipeline
        parsed_json = parse_resume_hybrid(file_bytes, file.filename)
        raw_text = parsed_json.get("_raw", "")
        
        # Personal workspace owner is resolved consistently for every upload.
        resume_version_id = None
        chunks_stored = 0
        if current_user:
            # Save to ResumeVersions table
            resume_version = ResumeVersion(
                user_id=current_user.id,
                source="uploaded",
                original_filename=file.filename,
                raw_text=raw_text,
                structured_json=parsed_json
            )
            db.add(resume_version)
            db.commit()
            db.refresh(resume_version)
            resume_version_id = resume_version.id

            # Save the original uploaded file bytes to backend disk
            import os
            os.makedirs("uploads", exist_ok=True)
            ext = os.path.splitext(file.filename)[1].lower()
            with open(f"uploads/{resume_version.id}{ext}", "wb") as out_f:
                out_f.write(file_bytes)
            
            # Embed into vector store
            try:
                chunks_stored = embed_and_upsert_resume(
                    user_id=str(current_user.id),
                    resume_version_id=str(resume_version.id),
                    raw_text=raw_text,
                    source_filename=file.filename,
                )
            except Exception as embed_err:
                logger.warning(f"Vector embedding failed (non-fatal): {embed_err}")
        
        return {
            "status": "success",
            "resume_id": resume_version_id,
            "parsed_data": parsed_json,
            "chunks_embedded": chunks_stored
        }
    except Exception as e:
        logger.error(f"Parse endpoint failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/extract-text")
async def extract_resume_text(file: UploadFile = File(...)):
    """Fast, direct text extraction from PDF/DOCX without saving or AI parsing."""
    try:
        file_bytes = await file.read()
        raw_text = extract_text(file_bytes, file.filename)
        return {
            "status": "success",
            "filename": file.filename,
            "text": raw_text
        }
    except Exception as e:
        logger.error(f"Text extraction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/templates')
def list_all_templates():
    from services.resume_templates import list_templates
    return list_templates()

@router.get('/fonts')
def list_all_fonts():
    """Return the list of available font options for the resume font picker."""
    from services.font_registry import list_fonts
    return list_fonts()

@router.get('/')
def get_resumes(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    try:
        user_id = current_user.id
        resumes = db.query(ResumeVersion).filter(
            ResumeVersion.user_id == user_id,
            ResumeVersion.source.in_(["uploaded", "builder"])
        ).order_by(ResumeVersion.created_at.desc()).all()
        return resumes
    except Exception as e:
        logger.error(f"Failed to fetch resumes: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch resumes")


@router.delete("/all")
def delete_all_resumes(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Delete all uploaded and builder resumes for the current user."""
    try:
        import os
        from db.models import Skill
        user_id = current_user.id
        resumes = db.query(ResumeVersion).filter(
            ResumeVersion.user_id == user_id,
            ResumeVersion.source.in_(["uploaded", "builder"])
        ).all()
        
        if resumes:
            resume_ids = [r.id for r in resumes]
            # Unlink any skills referencing these resumes
            db.query(Skill).filter(Skill.source_resume_id.in_(resume_ids)).update({"source_resume_id": None}, synchronize_session=False)
            
            for r in resumes:
                db.delete(r)
                for ext in [".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"]:
                    file_path = f"uploads/{r.id}{ext}"
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except Exception:
                        pass
                        
            db.commit()
        return {"status": "success", "message": "All resumes deleted successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"Delete all resumes failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/{resume_id}")
def get_resume_by_id(resume_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Fetch a single resume version by its ID."""
    resume = db.query(ResumeVersion).filter(ResumeVersion.id == resume_id, ResumeVersion.user_id == current_user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return {
        "id": resume.id,
        "source": resume.source,
        "original_filename": resume.original_filename,
        "structured_json": resume.structured_json,
        "created_at": str(resume.created_at),
    }


@router.delete("/{resume_id}")
def delete_resume(resume_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Delete a resume version by its ID, along with any duplicates (same filename)."""
    import os
    from db.models import Skill
    resume = db.query(ResumeVersion).filter(ResumeVersion.id == resume_id, ResumeVersion.user_id == current_user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    filename = resume.original_filename
    if filename:
        duplicates = db.query(ResumeVersion).filter(
            ResumeVersion.user_id == current_user.id,
            ResumeVersion.original_filename == filename
        ).all()
        dup_ids = [dup.id for dup in duplicates]
        db.query(Skill).filter(Skill.source_resume_id.in_(dup_ids)).update({"source_resume_id": None}, synchronize_session=False)
        for dup in duplicates:
            db.delete(dup)
            # Try to clean up physical file from uploads/
            for ext in [".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"]:
                file_path = f"uploads/{dup.id}{ext}"
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    pass
    else:
        db.query(Skill).filter(Skill.source_resume_id == resume.id).update({"source_resume_id": None}, synchronize_session=False)
        db.delete(resume)
        for ext in [".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"]:
            file_path = f"uploads/{resume.id}{ext}"
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
                
    db.commit()
    return {"status": "success", "message": "Resume deleted successfully"}


# ─── Rename resume ────────────────────────────────────────────────────

from pydantic import BaseModel as _PydanticBase

class RenameRequest(_PydanticBase):
    name: str

@router.patch("/{resume_id}/rename")
def rename_resume(
    resume_id: str,
    body: RenameRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Rename a resume (update original_filename)."""
    resume = db.query(ResumeVersion).filter(
        ResumeVersion.id == resume_id,
        ResumeVersion.user_id == current_user.id,
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    resume.original_filename = body.name.strip() or "Untitled Resume"
    db.commit()
    return {"status": "success", "name": resume.original_filename}


# ─── Duplicate resume ───────────────────────────────────────────────────

import copy as _copy

@router.post("/{resume_id}/duplicate")
def duplicate_resume(
    resume_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a deep copy of a resume under the same user."""
    original = db.query(ResumeVersion).filter(
        ResumeVersion.id == resume_id,
        ResumeVersion.user_id == current_user.id,
    ).first()
    if not original:
        raise HTTPException(status_code=404, detail="Resume not found")
    new_name = f"{original.original_filename or 'Resume'} (Copy)"
    dup = ResumeVersion(
        user_id=current_user.id,
        source=original.source,
        raw_text=original.raw_text,
        structured_json=_copy.deepcopy(original.structured_json),
        original_filename=new_name,
        design_json=_copy.deepcopy(original.design_json) if original.design_json else None,
        builder_template_id=original.builder_template_id,
    )
    db.add(dup)
    db.commit()
    db.refresh(dup)
    return {"status": "success", "resume_id": dup.id, "name": dup.original_filename}


def build_pdf_from_json(data: dict, template_id: Optional[str] = None, section_order: Optional[list] = None, font_id: Optional[str] = None, design: Optional[dict] = None) -> str:
    """Generate a clean, ATS-optimized PDF for the given resume JSON using the one-page fitting engine."""
    from services.pdf_fitter import build_fitted_pdf
    return build_fitted_pdf(data, template_id=template_id, section_order_override=section_order, font_id=font_id, design=design)


@router.get("/{resume_id}/pdf")
def get_resume_pdf(
    resume_id: str,
    background_tasks: BackgroundTasks,
    template_id: Optional[str] = None,
    font_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate a clean, ATS-optimized PDF for the given resume ID using PyMuPDF Stories."""
    import os
    from fastapi.responses import FileResponse

    resume = db.query(ResumeVersion).filter(
        ResumeVersion.id == resume_id,
        ResumeVersion.user_id == current_user.id,
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    data = resume.structured_json or {}
    design = resume.design_json or {}
    try:
        temp_path = build_pdf_from_json(data, template_id=template_id, font_id=font_id, design=design)
        background_tasks.add_task(os.unlink, temp_path)
        return FileResponse(
            temp_path,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline"}
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")


@router.get("/{resume_id}/docx")
def get_resume_docx(
    resume_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate a clean DOCX document for the given resume ID."""
    import os
    import tempfile
    from services.docx_exporter import generate_docx
    from fastapi.responses import FileResponse

    resume = db.query(ResumeVersion).filter(
        ResumeVersion.id == resume_id,
        ResumeVersion.user_id == current_user.id,
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    data = resume.structured_json or {}
    try:
        doc = generate_docx(data)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
        temp_path = temp_file.name
        temp_file.close()
        doc.save(temp_path)
        filename = f"resume_{resume_id[:8]}.docx"
        background_tasks.add_task(os.unlink, temp_path)
        return FileResponse(
            temp_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.error(f"DOCX generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate DOCX: {str(e)}")


@router.get("/{resume_id}/original")
def get_original_resume_file(
    resume_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Serve the exact raw file uploaded by the user, with a fallback to dynamic PDF rendering if the raw file is missing."""
    import os
    resume = db.query(ResumeVersion).filter(
        ResumeVersion.id == resume_id,
        ResumeVersion.user_id == current_user.id,
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    # Search for stored original file in uploads/
    for ext in [".pdf", ".docx", ".txt"]:
        file_path = f"uploads/{resume_id}{ext}"
        if os.path.exists(file_path):
            media_types = {
                ".pdf": "application/pdf",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".txt": "text/plain"
            }
            # PDFs open inline in the browser; DOCX/TXT must download (browsers can't render them)
            disposition = "inline" if ext == ".pdf" else f"attachment; filename=\"{resume.original_filename or f'resume{ext}'}\""
            return FileResponse(
                file_path,
                media_type=media_types.get(ext, "application/octet-stream"),
                headers={"Content-Disposition": disposition},
            )

    # Dynamic Fallback: if raw file is not found (parsed before update), render from JSON
    try:
        temp_path = build_pdf_from_json(resume.structured_json or {})
        return FileResponse(
            temp_path,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline"},
        )
    except Exception as render_err:
        logger.error(f"Fallback rendering failed: {render_err}")
        raise HTTPException(status_code=404, detail="Original document file not found")


# Legacy whole-resume tailoring has been retired.
from pydantic import BaseModel

@router.post('/tailor', status_code=410)
@router.post('/tailor/phase8/pdf', status_code=410)
@router.post('/tailor/phase8/docx', status_code=410)
def retired_tailoring():
    raise HTTPException(410, 'Use the LaTeX skills-only tailor at /tailor.')


class AnnotateRequest(BaseModel):
    job_description: Optional[str] = None

@router.post("/{resume_id}/annotate")
def annotate_resume(
    resume_id: str,
    request: Optional[AnnotateRequest] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Provides line-by-line bullet annotations with strength & quality signals."""
    from services.bullet_annotator import annotate_all_bullets
    from services.ats_scorer import _extract_jd_keywords

    resume_ver = db.query(ResumeVersion).filter(
        ResumeVersion.id == resume_id,
        ResumeVersion.user_id == current_user.id,
    ).first()
    if not resume_ver or not resume_ver.structured_json:
        raise HTTPException(status_code=404, detail="Resume not found")
        
    jd_keywords = []
    if request and request.job_description:
        jd_keywords = _extract_jd_keywords(request.job_description)
        
    annotations = annotate_all_bullets(resume_ver.structured_json, jd_keywords)
    return annotations


# ─── Resume Builder: Live HTML Preview ────────────────────────────────────────

class PreviewHtmlRequest(BaseModel):
    structured_json: dict
    template_id: Optional[str] = "classic"
    font_id: Optional[str] = None
    section_order: Optional[list] = None
    design: Optional[dict] = None

@router.post("/preview-html")
async def get_preview_html(
    req: PreviewHtmlRequest,
    current_user=Depends(get_current_user),
):
    """Return rendered HTML for live preview in the Resume Builder."""
    try:
        from services.pdf_fitter import build_preview_html
        html = build_preview_html(
            data=req.structured_json,
            template_id=req.template_id,
            section_order=req.section_order,
            font_id=req.font_id,
            design=req.design,
        )
        return {"html": html}
    except Exception as e:
        logger.error(f"preview-html error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Resume Builder: Live-payload PDF download ────────────────────────────────

class BuilderDownloadRequest(BaseModel):
    structured_json: dict
    template_id: Optional[str] = "classic"
    section_order: Optional[list] = None
    design: Optional[dict] = None
    filename: Optional[str] = "resume"

@router.post("/builder-download-pdf")
async def builder_download_pdf(
    req: BuilderDownloadRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    """
    Render and stream a PDF from a live builder payload without requiring
    the resume to be saved first. Useful for one-click export.
    """
    import tempfile, os
    try:
        from services.html_templates import build_html
        from services.resume_migrations import upgrade_to_v1

        data = upgrade_to_v1(req.structured_json)
        data["section_order"] = req.section_order or data.get("section_order") or []
        html = build_html(
            data=data,
            template_id=req.template_id or "classic",
            section_order=req.section_order or [],
            design=req.design or {},
        )

        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            await page.pdf(
                path=tmp.name,
                format="A4" if (req.design or {}).get("page_format") == "A4" else "Letter",
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
            await browser.close()

        safe_name = "".join(c for c in (req.filename or "resume") if c.isalnum() or c in " _-").strip() or "resume"
        background_tasks.add_task(os.unlink, tmp.name)
        return FileResponse(
            tmp.name,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
        )
    except Exception as e:
        logger.error(f"builder-download-pdf error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Resume Builder: Save ─────────────────────────────────────────────────────

class BuilderSaveRequest(BaseModel):
    resume_id: Optional[str] = None
    structured_json: dict
    design_json: Optional[dict] = None
    template_id: Optional[str] = "classic"
    font_id: Optional[str] = None
    section_order: Optional[list] = None
    original_filename: Optional[str] = "My Resume"

@router.post("/builder-save")
def builder_save(
    req: BuilderSaveRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Auto-save or manually save a resume created in the Resume Builder."""
    try:
        if req.resume_id:
            # Update existing resume — use partial-update semantics so missing fields don't wipe stored data
            resume = db.query(ResumeVersion).filter(
                ResumeVersion.id == req.resume_id,
                ResumeVersion.user_id == current_user.id,
            ).first()
            if not resume:
                raise HTTPException(status_code=404, detail="Resume not found")
            if req.structured_json is not None:
                resume.structured_json = req.structured_json
            if req.design_json is not None:
                resume.design_json = req.design_json
            if req.template_id is not None:
                resume.builder_template_id = req.template_id
            if req.original_filename:
                resume.original_filename = req.original_filename
            db.commit()
            return {"resume_id": resume.id, "message": "Updated"}
        else:
            # Create new resume
            resume = ResumeVersion(
                user_id=current_user.id,
                source="builder",
                structured_json=req.structured_json,
                design_json=req.design_json,
                builder_template_id=req.template_id,
                original_filename=req.original_filename or "My Resume",
            )
            db.add(resume)
            db.commit()
            db.refresh(resume)
            return {"resume_id": resume.id, "message": "Created"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"builder-save error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ─── Resume Builder: Upload Avatar ────────────────────────────────────────────

@router.post("/upload-avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    """Upload a profile photo for use in the Resume Builder."""
    import base64
    try:
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Only image files are allowed")
        contents = await file.read()
        if len(contents) > 3 * 1024 * 1024:  # 3MB limit
            raise HTTPException(status_code=400, detail="Image too large. Max 3MB.")
        # Store as base64 data URI so it embeds directly in HTML preview and PDF
        b64 = base64.b64encode(contents).decode("utf-8")
        data_uri = f"data:{file.content_type};base64,{b64}"
        return {"url": data_uri, "filename": file.filename}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"upload-avatar error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
