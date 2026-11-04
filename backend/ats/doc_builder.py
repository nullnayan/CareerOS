"""
doc_builder.py — Canonical resume builder.

Production key spellings (from resume_parser and frontend):
  experience[*].bullet_points  (list of str)
  experience[*].start_date
  experience[*].end_date

Corpus / legacy spellings (may still appear in older data):
  bullets / startDate / endDate

Both are accepted; legacy keys emit a warning so drift is visible.
A contract assertion fires if a resume has experience entries but
zero bullets — that is always a parse failure, not a zero score.
"""
import logging
import warnings
from typing import Mapping
from .models import (
    ResumeDoc, Contact, Experience, Education, Project, Skill, Certification,
    TextViews, Bullet, CandidateProfile, LayoutFacts
)
from .profile import compute_years_experience, get_effective_band

logger = logging.getLogger(__name__)


def _get_exp_bullets(exp_dict: dict) -> list[str]:
    """
    Return bullet list from an experience entry, accepting both
    production spelling ('bullet_points') and legacy spelling ('bullets').
    """
    if "bullet_points" in exp_dict:
        return list(exp_dict["bullet_points"] or [])
    if "bullets" in exp_dict:
        logger.warning(
            "doc_builder: found legacy 'bullets' key in experience entry — "
            "expected 'bullet_points'. Migrate corpus or parser output."
        )
        return list(exp_dict["bullets"] or [])
    return []


def _get_exp_dates(exp_dict: dict) -> tuple[str, str]:
    """
    Return (start_date, end_date) accepting both spellings.
    """
    if "start_date" in exp_dict or "end_date" in exp_dict:
        return exp_dict.get("start_date", ""), exp_dict.get("end_date", "")
    if "startDate" in exp_dict or "endDate" in exp_dict:
        logger.warning(
            "doc_builder: found legacy 'startDate'/'endDate' keys — "
            "expected 'start_date'/'end_date'. Migrate corpus or parser output."
        )
        return exp_dict.get("startDate", ""), exp_dict.get("endDate", "")
    return "", ""


def _parse_skills(raw_skills) -> list[dict]:
    """
    Normalise skills: accepts list-of-str, list-of-dicts, or dict-of-category->list.
    """
    if isinstance(raw_skills, dict):
        # e.g. {"technical": ["Python", "SQL"], "tools": ["Docker"]}
        result = []
        for category, items in raw_skills.items():
            if isinstance(items, list):
                for item in items:
                    result.append({"name": str(item), "category": category})
        return result
    if isinstance(raw_skills, list):
        normalised = []
        for item in raw_skills:
            if isinstance(item, str):
                normalised.append({"name": item, "category": ""})
            elif isinstance(item, dict):
                normalised.append(item)
        return normalised
    return []


def build_resume_doc(
    parsed_json: dict,
    layout_facts,
    declared_band: str | None,
    domain: str | None = None,
) -> ResumeDoc:
    """
    Constructs the frozen, canonical ResumeDoc from parsed JSON and layout facts.
    This is the single source of truth for the ATS scoring engine.

    Contract assertions:
    - If experience entries exist but all have zero bullets, a warning is logged
      with SCHEMA_MISMATCH so callers can detect the parse failure.
    """
    if isinstance(layout_facts, dict):
        layout = LayoutFacts(**layout_facts)
    else:
        layout = layout_facts

    # --- Contact ---
    contact_dict = parsed_json.get("contact", {}) or {}
    contact = Contact(
        name=contact_dict.get("name"),
        email=contact_dict.get("email"),
        phone=contact_dict.get("phone"),
        location=contact_dict.get("location"),
        links=tuple(contact_dict.get("links", []) or []),
    )

    summary = parsed_json.get("summary", "") or ""

    experiences = []
    projects = []
    educations = []
    certifications = []

    bullets: list[Bullet] = []
    by_section: dict[str, str] = {}

    # --- 1. Experience ---
    exp_text_parts: list[str] = []
    raw_experiences = parsed_json.get("experience", []) or []
    exp_has_entries = len(raw_experiences) > 0
    exp_total_bullets = 0

    for entry_idx, exp_dict in enumerate(raw_experiences):
        company = exp_dict.get("company", "") or ""
        title = exp_dict.get("title", "") or ""
        start_date, end_date = _get_exp_dates(exp_dict)
        is_current = "present" in (end_date or "").lower() or not end_date
        desc = exp_dict.get("description", "") or ""

        entry_bullet_strs = _get_exp_bullets(exp_dict)
        exp_total_bullets += len(entry_bullet_strs)

        experiences.append(Experience(
            company=company,
            title=title,
            start_date=start_date,
            end_date=end_date,
            is_current=is_current,
            bullets=tuple(entry_bullet_strs),
            description=desc,
        ))

        exp_text_parts.append(f"{company} {title}".strip())
        for b_idx, b_text in enumerate(entry_bullet_strs):
            bullets.append(Bullet(
                text=b_text,
                section="experience",
                entry_index=entry_idx,
                bullet_index=b_idx,
                entry_is_current=is_current,
            ))
            exp_text_parts.append(b_text)

    # Contract assertion: experience entries but no bullets = schema mismatch
    if exp_has_entries and exp_total_bullets == 0:
        logger.warning(
            "SCHEMA_MISMATCH: resume has %d experience entries but 0 bullets. "
            "Check key spellings (expected 'bullet_points'). Scoring may be unreliable.",
            len(raw_experiences),
        )

    by_section["experience"] = "\n".join(exp_text_parts)

    # --- 2. Projects ---
    proj_text_parts: list[str] = []
    for entry_idx, proj_dict in enumerate(parsed_json.get("projects", []) or []):
        name = proj_dict.get("name", "") or ""
        entry_bullet_strs = list(proj_dict.get("bullets", []) or [])
        desc = proj_dict.get("description", "") or ""
        techs = tuple(proj_dict.get("technologies", []) or [])

        projects.append(Project(
            name=name,
            bullets=tuple(entry_bullet_strs),
            description=desc,
            technologies=techs,
        ))

        proj_text_parts.append(name)
        # Include technology names in text so JD matching sees them
        proj_text_parts.extend(techs)
        for b_idx, b_text in enumerate(entry_bullet_strs):
            bullets.append(Bullet(
                text=b_text,
                section="projects",
                entry_index=entry_idx,
                bullet_index=b_idx,
                entry_is_current=False,
            ))
            proj_text_parts.append(b_text)

    by_section["projects"] = "\n".join(proj_text_parts)

    # --- 3. Education ---
    edu_text_parts: list[str] = []
    for edu_dict in parsed_json.get("education", []) or []:
        inst = edu_dict.get("institution", "") or ""
        deg = edu_dict.get("degree", "") or ""
        fld = edu_dict.get("field", "") or ""
        # Accept both 'endYear' and 'end_year'
        end_year = edu_dict.get("end_year") or edu_dict.get("endYear", "") or ""

        gpa_obj = edu_dict.get("gpa", {})
        gpa_val = (gpa_obj.get("raw", "") if isinstance(gpa_obj, dict) else str(gpa_obj or ""))

        educations.append(Education(
            institution=inst,
            degree=deg,
            field=fld,
            end_year=str(end_year),
            gpa=gpa_val,
        ))
        edu_text_parts.extend(filter(None, [inst, deg, fld]))

    by_section["education"] = "\n".join(edu_text_parts)

    # --- 4. Skills (handles list-of-str, list-of-dicts, dict-of-category->list) ---
    skill_text_parts: list[str] = []
    skills: list[Skill] = []
    normalised_skills = _parse_skills(parsed_json.get("skills", []))
    for skill_entry in normalised_skills:
        name = skill_entry.get("name", "") or ""
        cat = skill_entry.get("category", "") or ""
        skills.append(Skill(name=name, category=cat))
        if name:
            skill_text_parts.append(name)

    by_section["skills"] = "\n".join(skill_text_parts)

    # --- 5. Certifications ---
    cert_text_parts: list[str] = []
    for cert_dict in parsed_json.get("certifications", []) or []:
        name = cert_dict.get("name", "") if isinstance(cert_dict, dict) else str(cert_dict)
        certifications.append(Certification(name=name))
        if name:
            cert_text_parts.append(name)

    by_section["certifications"] = "\n".join(cert_text_parts)
    by_section["summary"] = summary

    # --- Full text: include all rich fields so JD matching works ---
    full_parts = []
    if contact.name:
        full_parts.append(contact.name)
    if contact.email:
        full_parts.append(contact.email)
    if contact.phone:
        full_parts.append(contact.phone)
    if contact.location:
        full_parts.append(contact.location)
    if summary:
        full_parts.append(summary)
    for section in ("experience", "projects", "skills", "education", "certifications"):
        sec_text = by_section.get(section, "")
        if sec_text:
            full_parts.append(sec_text)

    full_text = "\n\n".join(full_parts)

    text_views = TextViews(
        bullets=tuple(bullets),
        by_section=by_section,
        full=full_text,
        layout_raw="",  # Populated from PDF in formatting checks
    )

    # --- Profile ---
    temp_doc = ResumeDoc(
        contact=contact,
        summary=summary,
        experience=tuple(experiences),
        education=tuple(educations),
        projects=tuple(projects),
        skills=tuple(skills),
        certifications=tuple(certifications),
        text=text_views,
        layout=layout,
        profile=CandidateProfile(
            seniority="student", years_experience=0.0, domain="", has_formal_experience=False
        ),
    )

    years = compute_years_experience(temp_doc)
    effective_band = get_effective_band(declared_band, years)
    has_formal_experience = len(experiences) > 0

    # Infer domain from skills/title if not provided
    if domain is None:
        domain = _infer_domain(skills, experiences)

    profile = CandidateProfile(
        seniority=effective_band,
        years_experience=years,
        domain=domain,
        has_formal_experience=has_formal_experience,
    )

    return ResumeDoc(
        contact=contact,
        summary=summary,
        experience=tuple(experiences),
        education=tuple(educations),
        projects=tuple(projects),
        skills=tuple(skills),
        certifications=tuple(certifications),
        text=text_views,
        layout=layout,
        profile=profile,
    )


_TECH_INDICATORS = {
    "python", "java", "javascript", "typescript", "react", "node", "sql", "aws",
    "docker", "kubernetes", "git", "linux", "c++", "go", "rust", "machine learning",
    "deep learning", "data", "engineer", "developer", "software",
}
_DATA_INDICATORS = {"sql", "excel", "tableau", "power bi", "analytics", "data analyst"}
_HEALTHCARE_INDICATORS = {"nursing", "rn", "patient", "clinical", "bls", "cpr", "medical"}


def _infer_domain(skills: list[Skill], experiences: list[Experience]) -> str:
    """Basic domain inference from skills and job titles."""
    all_text = " ".join(
        [s.name.lower() for s in skills]
        + [e.title.lower() for e in experiences]
    )
    if any(w in all_text for w in _HEALTHCARE_INDICATORS):
        return "healthcare"
    if any(w in all_text for w in _DATA_INDICATORS):
        return "data"
    if any(w in all_text for w in _TECH_INDICATORS):
        return "software"
    return "professional"
