"""
services/template_fit.py
========================
Dynamic layout configuration for resume rendering.

Handles auto-ordering of sections based on career stage, and provides
density offsets (font size/line height adjustments) based on word count.
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# Keys that are NOT renderable resume sections
_NON_SECTION_KEYS = frozenset({
    "contact", "name", "email", "phone", "location",
    "metadata", "formatting_metadata", "formatting_issues", "formatting_checks",
    "original_section_headings", "jd_skills", "skills_modified",
    "_raw_text", "_parser_version", "_raw",
    "summary", "education", "experience", "projects",
    "skills", "certifications",
    "ats_score", "score_breakdown", "match_report", "match_score",
    "suggestions", "total_potential_score", "total_potential",
    "content_flags", "recruiter_tips", "hard_skills_matched",
    "hard_skills_missing", "soft_skills_matched", "soft_skills_missing",
    "keyword_frequency", "section_checks", "job_title", "job_description",
    "id", "user_id", "created_at", "updated_at", "version", "is_tailored",
    "target_job", "score", "feedback",
})

def auto_order_sections(resume_json: dict, template_id: str = None) -> List[str]:
    """
    Returns an ordered list of section keys based on content and template.

    Strategy:
      1. Use the template's default section_order as the starting point.
      2. If no experience entries, promote Education above Experience (fresher case).
      3. Filter out empty/missing sections.
      4. Append any unknown/custom sections detected in resume_json (Research, Achievements, etc.)
         so content is never silently dropped.
    """
    from services.resume_templates import get_template, get_default_section_order

    # Get template's preferred order (or fall back to sane defaults)
    if template_id:
        base_order = get_default_section_order(template_id)
    else:
        base_order = ["summary", "experience", "projects", "skills", "education", "certifications"]

    experience = resume_json.get("experience") or []

    # For freshers: if template puts experience before education but candidate has none,
    # promote education above experience.
    if len(experience) == 0:
        if "experience" in base_order and "education" in base_order:
            exp_idx = base_order.index("experience")
            edu_idx = base_order.index("education")
            if exp_idx < edu_idx:
                # Swap: put education where experience was
                base_order[exp_idx] = "education"
                base_order[edu_idx] = "experience"

    # Filter out empty sections
    final_order = []
    for sec in base_order:
        if sec == "summary":
            val = resume_json.get("summary")
            if val and isinstance(val, str) and val.strip():
                final_order.append(sec)
        elif sec == "skills":
            val = resume_json.get("skills")
            if val:
                final_order.append(sec)
        else:
            val = resume_json.get(sec)
            if val and isinstance(val, list) and len(val) > 0:
                final_order.append(sec)

    # Detect and append unknown sections from resume_json
    for key in resume_json.keys():
        if key in _NON_SECTION_KEYS or key.startswith("_"):
            continue
        if key in final_order:
            continue
        val = resume_json.get(key)
        if val and (isinstance(val, (list, str)) or isinstance(val, dict)):
            final_order.append(key)

    return final_order

def get_visible_word_count(resume_json: dict) -> Dict[str, int]:
    """
    Computes exact visible text word count from resume sections (excluding JSON key names).
    """
    text_parts = []
    
    # Summary
    summary = resume_json.get("summary")
    if summary and isinstance(summary, str):
        text_parts.append(summary)

    # Skills
    skills = resume_json.get("skills", {})
    if isinstance(skills, dict):
        for cat, val in skills.items():
            text_parts.append(str(cat))
            if isinstance(val, list):
                text_parts.extend([str(v) for v in val if v])
            elif isinstance(val, str):
                text_parts.append(val)
    elif isinstance(skills, list):
        text_parts.extend([str(s) for s in skills if s])

    # Projects & Experience
    for sec in ["experience", "projects"]:
        for item in (resume_json.get(sec) or []):
            if isinstance(item, dict):
                text_parts.append(str(item.get("company") or item.get("name") or ""))
                text_parts.append(str(item.get("title") or ""))
                bullets = item.get("bullet_points") or item.get("bullets") or []
                text_parts.extend([str(b) for b in bullets if b])

    # Education
    for edu in (resume_json.get("education") or []):
        if isinstance(edu, dict):
            text_parts.append(f"{edu.get('degree', '')} {edu.get('field', '')} {edu.get('institution', '')}")

    full_text = " ".join(filter(None, text_parts))
    words = full_text.split()
    return {
        "word_count": len(words),
        "full_text_len": len(full_text)
    }

def select_density_config(resume_json: dict) -> Dict[str, float]:
    """
    Analyzes visible resume volume and returns font/line height offsets
    to be layered ON TOP of the chosen template's base sizes.
    """
    metrics = get_visible_word_count(resume_json)
    word_count = metrics["word_count"]

    if word_count < 200:
        # Light content -> scale up slightly
        offsets = {"font_size_offset": 0.5, "line_height_offset": 0.05}
        logger.info(f"[TemplateFit] Light content ({word_count} words). Scaling up.")
    elif word_count >= 500:
        # Dense content -> scale down slightly
        offsets = {"font_size_offset": -0.5, "line_height_offset": -0.05}
        logger.info(f"[TemplateFit] Dense content ({word_count} words). Scaling down.")
    else:
        # Normal content -> no scaling
        offsets = {"font_size_offset": 0.0, "line_height_offset": 0.0}
        logger.info(f"[TemplateFit] Normal content ({word_count} words). No offset.")

    return offsets
