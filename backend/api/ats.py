"""
ATS analysis endpoint.

Supports TWO modes:
1. Baseline (no job description): evaluates general ATS friendliness
2. Targeted (with job description): compares resume vs. specific job posting

Both modes save findings as Suggestion rows — per our rule that AI never
directly modifies user data, only proposes changes for the user to
accept/reject/edit later.
"""

from typing import Optional
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from db.session import get_db
from db.models import ResumeVersion, Suggestion
from core.workspace import get_workspace_owner as get_current_user

from agents.resume_improver_agent import improve_resume_baseline

from ats.api_adapter import run_v3_scoring, run_v3_scoring_from_json

router = APIRouter()
logger = logging.getLogger(__name__)


class ATSAnalyzeRequest(BaseModel):
    resume_id: str
    job_description: Optional[str] = None


@router.post("/analyze")
def analyze(request: ATSAnalyzeRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    # Step 1: fetch the resume — fail clearly if it doesn't exist
    resume = db.get(ResumeVersion, request.resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail=f"No resume found with id '{request.resume_id}'.",
        )

    created_suggestions = []

    # Step 2: decide which analysis mode to run
    if request.job_description and request.job_description.strip():
        # TARGETED MODE: deterministic scoring against a specific job description
        result = run_v3_scoring(resume, request.job_description)

        # Turn each issue into a Suggestion row
        for issue in result.get("issues", []):
            suggestion = Suggestion(
                user_id=resume.user_id,
                type="ats_targeted_issue",
                reason=issue.get("issue", ""),
                confidence_score=None,
                expected_impact=issue.get("suggestion", ""),
                status="pending",
                target_entity_type="resume_version",
                target_entity_id=resume.id,
                payload={
                    "category": issue.get("category"),
                    "severity": issue.get("severity"),
                    "issue": issue.get("issue"),
                    "suggestion": issue.get("suggestion"),
                    "points_deducted": issue.get("points_deducted", 0),
                    "mode": "targeted",
                },
            )
            db.add(suggestion)
            created_suggestions.append(suggestion)

        # Persist best-effort score to DB (prefer overall, fallback baseline)
        persist_score = result.get("overall_score") or result.get("baseline_score")
        if persist_score is not None:
            from sqlalchemy.orm.attributes import flag_modified
            if isinstance(resume.structured_json, dict):
                resume.structured_json["score"] = persist_score
                flag_modified(resume, "structured_json")
                db.add(resume)

        db.commit()
        for s in created_suggestions:
            db.refresh(s)

        resp = {
            "mode": "targeted",
            "resume_id": resume.id,
            "baseline_score": result.get("baseline_score"),
            "match_score": result.get("match_score"),   # may be None per Bug 1
            "overall_score": result.get("overall_score"),
            "jd_extraction_status": result.get("jd_extraction_status"),
            "score_breakdown": result.get("score_breakdown", {}),
            "missing_keywords": result.get("missing_keywords", []),
            "matched_keywords": result.get("matched_keywords", []),
            "bullet_point_analysis": result.get("bullet_point_analysis", []),
            "issues": result.get("issues", []),
            "summary": result.get("summary", ""),
            "suggestions_created": [
                {
                    "id": s.id,
                    "category": s.payload.get("category"),
                    "severity": s.payload.get("severity"),
                    "reason": s.reason,
                    "suggestion": s.payload.get("suggestion"),
                    "points_deducted": s.payload.get("points_deducted", 0),
                    "status": s.status,
                }
                for s in created_suggestions
            ],
        }
        if result.get("match_fallback_reason"):
            resp["match_fallback_reason"] = result["match_fallback_reason"]
        return resp

    else:
        # BASELINE MODE: deterministic scoring — no AI, pure Python rules
        result = run_v3_scoring(resume, None)

        # Step 3b: turn each issue into a Suggestion row.
        for issue in result.get("issues", []):
            suggestion = Suggestion(
                user_id=resume.user_id,
                type="ats_baseline_issue",
                reason=issue.get("issue", ""),
                confidence_score=None,
                expected_impact=issue.get("suggestion", ""),
                status="pending",
                target_entity_type="resume_version",
                target_entity_id=resume.id,
                payload={
                    "category": issue.get("category"),
                    "severity": issue.get("severity"),
                    "issue": issue.get("issue"),
                    "suggestion": issue.get("suggestion"),
                    "mode": "baseline",
                },
            )
            db.add(suggestion)
            created_suggestions.append(suggestion)

        persist_score = result.get("overall_score") or result.get("baseline_score")
        if persist_score is not None:
            from sqlalchemy.orm.attributes import flag_modified
            if isinstance(resume.structured_json, dict):
                resume.structured_json["score"] = persist_score
                flag_modified(resume, "structured_json")
                db.add(resume)

        db.commit()
        for s in created_suggestions:
            db.refresh(s)

        return {
            "mode": "baseline",
            "resume_id": resume.id,
            "baseline_score": result.get("baseline_score"),
            "overall_score": result.get("overall_score"),
            "score_breakdown": result.get("score_breakdown", {}),
            "summary": result.get("summary", ""),
            "bullet_point_analysis": result.get("bullet_point_analysis", []),
            "issues": result.get("issues", []),
            "suggestions_created": [
                {
                    "id": s.id,
                    "category": s.payload.get("category"),
                    "severity": s.payload.get("severity"),
                    "reason": s.reason,
                    "suggestion": s.payload.get("suggestion"),
                    "status": s.status,
                }
                for s in created_suggestions
            ],
        }


class ATSImproveProposeRequest(BaseModel):
    resume_id: str
    mode: str = "auto_improve" # or "custom"
    custom_category: Optional[str] = None
    job_description: Optional[str] = None

class ChangeItem(BaseModel):
    section: str
    item_index: int
    bullet_index: Optional[int] = None
    field: str
    original: str
    proposed: str
    reason: str
    type: str # "rewrite" or "question"
    user_answer: Optional[str] = None # Filled by frontend for questions
    category: Optional[str] = None # Which fixer generated this

class ATSImproveApplyRequest(BaseModel):
    resume_id: str
    accepted_changes: list[ChangeItem]


@router.post("/improve/propose")
def improve_propose(request: ATSImproveProposeRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    from ats_fixers.dispatcher import dispatch
    from ats.api_adapter import run_v3_scoring

    resume = db.get(ResumeVersion, request.resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resume not found")

    original_json = resume.structured_json

    try:
        ats_result = run_v3_scoring(resume, None)
    except Exception as e:
        logger.warning(f"ATS pre-scoring failed: {e}")
        ats_result = {}

    changes_dict = dispatch(
        ats_result,
        original_json,
        mode="finding_driven" if request.mode == "auto_improve" else request.mode,
        jd=request.job_description,
        custom_category=request.custom_category,
        compute_deltas=True,
    )
    
    # Apply the string rewrites and skill additions (skip questions that need user input)
    import copy
    simulated_json = copy.deepcopy(original_json)

    for cat, changes in changes_dict.items():
        for change in changes:
            t = change.get("type")
            if t in ("rewrite", "add_skill"):
                sec = change["section"]
                idx = change["item_index"]
                b_idx = change.get("bullet_index")
                fld = change["field"]
                val = change["proposed"]
                try:
                    if t == "add_skill" and sec == "skills":
                        skills = simulated_json.get("skills")
                        if skills is None:
                            simulated_json["skills"] = [val]
                        elif isinstance(skills, list):
                            if val.lower() not in [s.lower() for s in skills]:
                                skills.append(val)
                        elif isinstance(skills, dict):
                            added = False
                            for key in ["technical", "languages", "tools", "frameworks", "skills"]:
                                if key in skills and isinstance(skills[key], list):
                                    if val.lower() not in [s.lower() for s in skills[key]]:
                                        skills[key].append(val)
                                    added = True
                                    break
                            if not added:
                                for key, v in skills.items():
                                    if isinstance(v, list):
                                        if val.lower() not in [s.lower() for s in v]:
                                            v.append(val)
                                        added = True
                                        break
                            if not added:
                                skills["other"] = [val]
                    elif idx == -1 or sec in ("summary", "objective"):
                        simulated_json[sec] = val
                    elif b_idx is not None and fld in ("bullets", "bullet_points"):
                        actual_key = "bullet_points" if "bullet_points" in simulated_json[sec][idx] else "bullets"
                        simulated_json[sec][idx][actual_key][b_idx] = val
                    else:
                        simulated_json[sec][idx][fld] = val
                except Exception:
                    pass
                    
    from services.pdf_fitter import simulate_pruning
    pruned_changes = simulate_pruning(simulated_json)
    
    if pruned_changes:
        changes_dict["page_fitter"] = pruned_changes

    # Flatten dict into a list and inject the category name
    flat_changes = []
    for cat, changes in changes_dict.items():
        for c in changes:
            if "category" not in c:
                c["category"] = cat
            flat_changes.append(c)

    return {
        "status": "success",
        "proposed_changes": flat_changes,
        "old_score": ats_result.get("baseline_score", "?")
    }

import copy

@router.post("/improve/apply")
def improve_apply(request: ATSImproveApplyRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    from ats.api_adapter import run_v3_scoring
    from ats_fixers import quantify_impact, length_depth
    from ats_fixers.locked_registry import build_locked_registry, validate_rewrite

    resume = db.get(ResumeVersion, request.resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resume not found")

    new_json = copy.deepcopy(resume.structured_json)
    locked_registry = build_locked_registry(resume.structured_json)
    applied_diffs = []

    # Apply changes
    for change in request.accepted_changes:
        sec = change.section
        idx = change.item_index
        b_idx = change.bullet_index
        fld = change.field

        # Resolve question-type changes that need user input first
        final_text = change.proposed
        if change.type == "question" and change.user_answer:
            if change.category == "quantify_impact":
                final_text = quantify_impact.apply_fix_with_answer(change.original, change.user_answer)
            elif change.category == "length_depth":
                final_text = length_depth.apply_fix_with_answer(change.original, change.user_answer)
            else:
                final_text = change.user_answer

        # Protect locked fields on line-level rewrites
        if fld in ("bullets", "bullet_points") and b_idx is not None:
            if not validate_rewrite(change.original, final_text, locked_registry, change.user_answer):
                logger.warning(f"Validation failed. Rejecting edit: {change.original} -> {final_text}")
                continue  # Reject the rewrite to prevent hallucination/data corruption

        # Apply to JSON
        try:
            # ── Case 0: Skills section addition (add_skill type)
            if sec == "skills" and change.type == "add_skill":
                skills = new_json.get("skills")
                if skills is None:
                    new_json["skills"] = [final_text]
                elif isinstance(skills, list):
                    if final_text.lower() not in [s.lower() for s in skills]:
                        new_json["skills"].append(final_text)
                elif isinstance(skills, dict):
                    added = False
                    for key in ["technical", "languages", "tools", "frameworks", "skills"]:
                        if key in skills and isinstance(skills[key], list):
                            if final_text.lower() not in [s.lower() for s in skills[key]]:
                                skills[key].append(final_text)
                            added = True
                            break
                    if not added:
                        for key, val in skills.items():
                            if isinstance(val, list):
                                if final_text.lower() not in [s.lower() for s in val]:
                                    val.append(final_text)
                                added = True
                                break
                    if not added:
                        skills["other"] = [final_text]

            # ── Case 1: Top-level string field (summary, objective)
            elif idx == -1 or sec in ("summary", "objective"):
                new_json[sec] = final_text

            # ── Case 2: Bullet point edit inside a section array
            elif b_idx is not None and fld in ("bullets", "bullet_points"):
                item = new_json[sec][idx]
                actual_key = "bullet_points" if "bullet_points" in item else "bullets"
                new_json[sec][idx][actual_key][b_idx] = final_text

            # ── Case 3: Direct field on an array item (dates, title, company, etc.)
            else:
                new_json[sec][idx][fld] = final_text
                
            applied_diffs.append(change.dict())

        except (KeyError, IndexError, TypeError) as e:
            logger.warning(f"Could not apply change to {sec}[{idx}].{fld}[{b_idx}]: {e}")




    # Re-score the improved resume
    improved_ats = {}
    new_score = None
    try:
        from ats.api_adapter import run_v3_scoring_from_json
        rescore_result = run_v3_scoring_from_json(new_json)
        new_score = rescore_result.get("baseline_score")
        improved_ats = rescore_result
    except Exception as rescore_err:
        logger.warning(f"Re-score after improve_apply failed: {rescore_err}")

    if new_score is not None:
        new_json["score"] = new_score

    # Save
    version_num = (resume.version_number or 1) + 1
    improved_version = ResumeVersion(
        user_id=resume.user_id,
        source="builder",
        raw_text=None,
        structured_json=new_json,
        original_filename=resume.original_filename or "improved_resume.pdf",
        version_number=version_num,
        ats_score=new_score,
        issues_json=improved_ats.get("issues", []),
        diff_json=applied_diffs
    )
    db.add(improved_version)
    db.commit()
    db.refresh(improved_version)


    return {
        "status": "success",
        "improved_resume_id": improved_version.id,
        "new_score": new_score,
        "improved_json": new_json,
        "download_url": f"http://127.0.0.1:8000/resumes/{improved_version.id}/pdf"
    }


def _build_change_list(original: dict, improved: dict) -> list:
    """Build a list of human-readable changes between original and improved resume JSON."""
    changes = []

    # Compare bullet points in experience
    for section_key in ["experience", "projects"]:
        orig_items = original.get(section_key, []) or []
        new_items = improved.get(section_key, []) or []
        for i, (orig_item, new_item) in enumerate(zip(orig_items, new_items)):
            if not isinstance(orig_item, dict) or not isinstance(new_item, dict):
                continue
            label = orig_item.get("company") or orig_item.get("name") or f"{section_key} #{i+1}"
            orig_bullets = orig_item.get("bullet_points", []) or []
            new_bullets = new_item.get("bullet_points", []) or []
            # If description was a string, split it
            if not orig_bullets and orig_item.get("description"):
                orig_bullets = [orig_item["description"]]
            if not new_bullets and new_item.get("description"):
                new_bullets = [new_item["description"]]
            for j, (ob, nb) in enumerate(zip(orig_bullets, new_bullets)):
                if ob != nb:
                    changes.append({
                        "section": section_key,
                        "item": label,
                        "bullet_index": j,
                        "original": ob,
                        "improved": nb,
                    })

    # Compare summary
    orig_summary = original.get("summary", "") or ""
    new_summary = improved.get("summary", "") or ""
    if orig_summary != new_summary and new_summary:
        changes.append({
            "section": "summary",
            "item": "Professional Summary",
            "bullet_index": 0,
            "original": orig_summary,
            "improved": new_summary,
        })

    # Compare skills
    orig_skills = set(s if isinstance(s, str) else s.get("name", "") for s in (original.get("skills") or []))
    new_skills = set(s if isinstance(s, str) else s.get("name", "") for s in (improved.get("skills") or []))
    added = new_skills - orig_skills
    removed = orig_skills - new_skills
    if added:
        changes.append({
            "section": "skills",
            "item": "Skills Added",
            "bullet_index": 0,
            "original": "",
            "improved": ", ".join(sorted(added)),
        })
    if removed:
        changes.append({
            "section": "skills",
            "item": "Skills Removed",
            "bullet_index": 0,
            "original": ", ".join(sorted(removed)),
            "improved": "",
        })

    return changes


class ATSImproveBulletRequest(BaseModel):
    bullet_text: str
    job_description: Optional[str] = None


@router.post("/improve-bullet")
def improve_bullet(request: ATSImproveBulletRequest, current_user = Depends(get_current_user)):

    """
    On-demand bullet rewrite using mistral-medium-3.5-128b.
    Returns the suggested rewrite and reasoning.
    """
    from agents.bullet_rewriter import rewrite_bullet
    
    try:
        result = rewrite_bullet(request.bullet_text, request.job_description)
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to rewrite bullet: {str(e)}")


class ATSAnalyzeTextRequest(BaseModel):
    resume_text: str
    job_description: Optional[str] = None


@router.post("/analyze-text")
def analyze_text(request: ATSAnalyzeTextRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    from api.resumes import parse_resume_hybrid
    
    if not request.resume_text.strip():
        raise HTTPException(status_code=400, detail="Resume text cannot be empty.")
        
    try:
        # Convert string to bytes to use the hybrid pipeline
        file_bytes = request.resume_text.encode("utf-8")
        structured_json = parse_resume_hybrid(file_bytes, "pasted_resume.txt")
    except Exception as parse_err:
        raise HTTPException(status_code=502, detail=f"Failed to parse resume text: {str(parse_err)}")

    # Detect PDF layout issues on raw text (mock empty metadata since text is pasted/direct)
    structured_json["formatting_metadata"] = {
        "has_columns": False,
        "has_tables": False,
        "is_scanned_pdf": False
    }

    # Score it using the parsed JSON directly (no DB object yet)
    is_targeted = bool(request.job_description and request.job_description.strip())
    band = "entry"
    try:
        if current_user and getattr(current_user, "career_level", None):
            band = current_user.career_level
    except Exception:
        pass

    from ats.api_adapter import run_v3_scoring_from_json, infer_jd_title_from_dict

    # Bug 3 fix: infer title from parsed JSON before calling run_v3_scoring_from_json
    inferred_title = infer_jd_title_from_dict(structured_json)

    result = run_v3_scoring_from_json(
        structured_json,
        job_description=request.job_description if is_targeted else None,
        band=band,
        jd_title=inferred_title,
    )
    
    # Store score — prefer overall, fallback to baseline
    score_val = result.get("overall_score") or result.get("baseline_score")
    if score_val is not None:
        structured_json["score"] = score_val

    import uuid
    resume_id = str(uuid.uuid4())
    user_id = current_user.id

    def _save_resume_to_db():
        try:
            with next(get_db()) as bg_db:
                temp_resume = ResumeVersion(
                    id=resume_id,
                    user_id=user_id,
                    source="uploaded",
                    original_filename="pasted_resume.pdf",
                    raw_text=request.resume_text,
                    structured_json=structured_json
                )
                bg_db.add(temp_resume)
                bg_db.commit()
        except Exception as db_err:
            logger.warning(f"Background DB save failed (non-fatal): {db_err}")

    background_tasks.add_task(_save_resume_to_db)

    suggestions = []
    for i, issue in enumerate(result.get("issues", [])):
        suggestions.append({
            "id": f"temp_{i}",
            "category": issue.get("category"),
            "severity": issue.get("severity"),
            "reason": issue.get("issue"),
            "suggestion": issue.get("suggestion"),
            "points_deducted": issue.get("points_deducted", 0),
            "status": "pending",
        })

    # Bug 2+5: honest three-field response shape (same as /ats/analyze)
    response_data: dict = {
        "mode": "targeted" if is_targeted else "baseline",
        "resume_id": resume_id,
        "baseline_score": result.get("baseline_score"),
        "overall_score": result.get("overall_score"),
        "score_breakdown": result.get("score_breakdown", {}),
        "issues": result.get("issues", []),
        "suggestions_created": suggestions,
        "bullet_point_analysis": result.get("bullet_point_analysis", []),
        "summary": result.get("summary", ""),
    }

    if is_targeted:
        response_data["match_score"] = result.get("match_score")  # may be None
        response_data["jd_extraction_status"] = result.get("jd_extraction_status", "failed")
        response_data["missing_keywords"] = result.get("missing_keywords", [])
        response_data["matched_keywords"] = result.get("matched_keywords", [])
        if result.get("match_fallback_reason"):
            response_data["match_fallback_reason"] = result["match_fallback_reason"]

    return response_data
