"""
api_adapter.py — Translates ATS v3 ScoreReport to the legacy API JSON shape.

Fixes per PROMPT_dual_mode_ats.md:
- Bug 1: match_fallback surfaced in response
- Bug 2: THREE distinct score fields: baseline_score, match_score, overall_score
         (no more aliasing headline to both)
- Bug 3: infer_jd_title_from_dict() works on structured dict, not ORM object;
         called from BOTH entry points so pasted-text path gets a real title
- Bug 4: extraction_confidence uses "ok"|"low_confidence"|"failed";
         "failed" = zero keywords; top-level jd_extraction_status key,
         absent entirely in baseline mode
- Bug 5: removed premium_breakdown/resume_vs_jd_match_pct/jd_matching from
         response (they were always empty); deleted the dead-field emitters
"""
import logging
import re
from typing import Any, Mapping, Optional
from .models import ResumeDoc, JobTarget
from .scoring.scorer import score_resume, ScoreReport
from .doc_builder import build_resume_doc
from .layout_probe import probe_layout
from .jd.extract import extract_job_target
from .profile import get_band_drift
from db.models import ResumeVersion

logger = logging.getLogger(__name__)


def infer_jd_title_from_dict(structured_json: dict) -> str:
    """
    Bug 3 fix: infer the best JD title from a structured resume dict
    (works without an ORM object, so the paste-text path can use it too).
    Precedence: contact.target_role → first experience title → "".
    """
    try:
        target_role = structured_json.get("target_role") or structured_json.get("targetRole")
        if target_role:
            return str(target_role).strip()
    except Exception:
        pass
    try:
        experiences = structured_json.get("experience", []) or []
        if experiences:
            return (experiences[0].get("title") or "").strip()
    except Exception:
        pass
    return ""


def convert_to_api_response(
    doc: ResumeDoc,
    report: ScoreReport,
    is_targeted: bool,
    jd: Optional[JobTarget] = None,
) -> Mapping[str, Any]:
    """
    Converts a ScoreReport into the JSON shape the frontend consumes.

    Three distinct score fields (Bug 2):
      baseline_score  — report.strength; JD-independent; present in BOTH modes
      match_score     — report.match; present only in targeted mode;
                        None when JD unreadable (Bug 1/Bug 4)
      overall_score   — report.headline; the blended number; present in BOTH modes
    """
    # ── Issue list ────────────────────────────────────────────────────────────
    formatted_issues = []
    for finding in report.findings:
        formatted_issues.append({
            "category": finding.check_id.split(".")[0] if "." in finding.check_id else finding.check_id,
            "issue": finding.title,
            "suggestion": finding.detail,
            "points_deducted": finding.points,
            "severity": finding.severity,
            "section": finding.anchor.section if finding.anchor else "general",
        })
    for finding in report.ledger_applied:
        formatted_issues.append({
            "category": "ledger",
            "issue": finding.title,
            "suggestion": finding.detail,
            "points_deducted": finding.points,
            "severity": finding.severity,
            "section": "general",
        })

    # ── Keyword lists ─────────────────────────────────────────────────────────
    matched_keywords: list[str] = []
    missing_keywords: list[str] = []
    if jd and jd.keywords:
        text_lower = doc.text.full.lower()
        for kw in jd.keywords:
            pattern = r"\b" + re.escape(kw.term.lower()) + r"\b"
            if re.search(pattern, text_lower):
                matched_keywords.append(kw.term)
            else:
                missing_keywords.append(kw.term)

    # ── Bullet-level analysis ─────────────────────────────────────────────────
    bullet_point_analysis = [
        {
            "section": f.anchor.section,
            "entry_index": f.anchor.entry_index,
            "bullet_index": f.anchor.bullet_index,
            "issue": f.title,
            "suggestion": f.detail,
            "severity": f.severity,
        }
        for f in report.findings
        if f.anchor is not None
    ]

    # ── score_breakdown: only numeric values, no null/None entries ────────────
    score_breakdown: dict[str, Any] = {
        "strength": report.strength,
        "parseability": report.parseability,
    }
    # Only add match in targeted mode AND only when it is not None (Bug 2)
    if is_targeted and report.match is not None:
        score_breakdown["match"] = report.match
    if report.role_fit is not None:
        score_breakdown["role_fit"] = report.role_fit

    # ── Meta (no jd_extraction_status in baseline — Bug 4) ───────────────────
    meta: dict[str, Any] = {
        "version": report.version,
        "bullets_evaluated": len(doc.text.bullets),
        "years_experience": doc.profile.years_experience,
        "band": doc.profile.seniority,
        "domain": doc.profile.domain,
        "layout_evaluated": doc.layout.page_count > 0,
        "band_drift": get_band_drift(
            getattr(doc.profile, "_declared_band", None),
            doc.profile.years_experience,
        ),
    }

    # Bug 4: extraction_confidence tri-state; absent in baseline mode
    if is_targeted:
        if jd is None:
            jd_status = "failed"
        elif report.match_fallback:
            # JD had zero usable keywords — failed extraction
            jd_status = "failed" if (not jd.keywords) else "low_confidence"
            if len(jd.keywords) == 0:
                jd_status = "failed"
            else:
                # remap legacy "low" → "low_confidence"
                jd_status = "low_confidence" if jd.extraction_confidence in ("low", "low_confidence") else "ok"
        else:
            raw_conf = jd.extraction_confidence if jd else "failed"
            if raw_conf == "ok":
                jd_status = "ok"
            elif len(jd.keywords) == 0:
                jd_status = "failed"
            else:
                jd_status = "low_confidence"
        meta["jd_extraction_status"] = jd_status

    # ── Response assembly ─────────────────────────────────────────────────────
    response: dict[str, Any] = {
        "score_breakdown": score_breakdown,
        "meta": meta,
        "issues": formatted_issues,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "bullet_point_analysis": bullet_point_analysis,
        "summary": _build_summary(report, meta),
    }

    # Bug 2: three distinct, honestly-named score fields
    # baseline_score = strength (JD-independent, always present)
    response["baseline_score"] = report.strength
    # overall_score = headline blend (always present)
    response["overall_score"] = report.headline

    if is_targeted:
        # match_score = None when JD unreadable (never collapse to headline)
        response["match_score"] = report.match  # may be None
        # Surface jd_extraction_status at top level too (Bug 4 — frontend reads top level)
        response["jd_extraction_status"] = meta.get("jd_extraction_status", "failed")
        # Explain fallback when it occurred
        if report.match_fallback:
            response["match_fallback_reason"] = (
                "Job description could not be read — no recognised skills found. "
                "Score shown is resume strength only."
            )

    return response


def _build_summary(report: ScoreReport, meta: dict) -> str:
    """Human-readable one-line summary."""
    score = report.strength
    if score >= 85:
        label = "Excellent"
    elif score >= 72:
        label = "Good"
    elif score >= 58:
        label = "Needs work"
    else:
        label = "Significant gaps"
    return (
        f"{label} resume ({score:.0f}/100). "
        f"Band: {meta['band']} · {meta['bullets_evaluated']} bullets evaluated."
    )


def _infer_jd_title(resume: ResumeVersion) -> str:
    """
    Bug 3 fix: ORM-object variant — delegates to the dict-based function.
    """
    try:
        if resume.user and getattr(resume.user, "target_role", None):
            return str(resume.user.target_role).strip()
    except Exception:
        pass
    return infer_jd_title_from_dict(resume.structured_json or {})


def run_v3_scoring(
    resume: ResumeVersion,
    job_description: Optional[str] = None,
) -> Mapping[str, Any]:
    """
    Entry point for saved-resume scoring (ResumeVersion DB object).
    """
    pdf_source = None
    file_type = "unknown"
    try:
        if hasattr(resume, "file_path") and resume.file_path:
            pdf_source = resume.file_path
            file_type = "pdf" if str(resume.file_path).lower().endswith(".pdf") else "unknown"
        elif hasattr(resume, "raw_bytes") and resume.raw_bytes:
            pdf_source = resume.raw_bytes
            file_type = "pdf"
    except Exception:
        pass

    layout = probe_layout(pdf_source, file_type=file_type)

    band = "entry"
    try:
        if resume.user and getattr(resume.user, "career_level", None):
            band = resume.user.career_level
    except Exception:
        pass

    structured_json = resume.structured_json or {}
    doc = build_resume_doc(structured_json, layout, declared_band=band)

    jd = None
    if job_description and job_description.strip():
        # Bug 3 fix: infer real title from resume, not hardcoded "Unknown Title"
        title = _infer_jd_title(resume)
        jd = extract_job_target(job_description, title or "Unknown Title", band)

    report = score_resume(doc, jd)
    return convert_to_api_response(doc, report, is_targeted=bool(jd), jd=jd)


def run_v3_scoring_from_json(
    structured_json: dict,
    job_description: Optional[str] = None,
    band: str = "entry",
    jd_title: str = "",
) -> Mapping[str, Any]:
    """
    Entry point for paste-text path (no ResumeVersion yet).
    Bug 3 fix: infers title from structured_json when jd_title not supplied.
    """
    layout = probe_layout(None)
    doc = build_resume_doc(structured_json, layout, declared_band=band)

    jd = None
    if job_description and job_description.strip():
        # Bug 3 fix: infer from dict when caller didn't supply a title
        title = jd_title or infer_jd_title_from_dict(structured_json) or "Unknown Title"
        jd = extract_job_target(job_description, title, band)

    report = score_resume(doc, jd)
    return convert_to_api_response(doc, report, is_targeted=bool(jd), jd=jd)
