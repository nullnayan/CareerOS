"""
Premium scoring engine — combines your original checks with the new
authenticity/stuffing, growth-signal, style, and red-flag checks.
"""

import re
from typing import Dict, List

# New weight scheme — adds "authenticity" (anti-stuffing) and
# "growth_signals" as first-class categories instead of burying them
# inside content_quality, since stuffing/fabrication is a distinct
# failure mode from "weak writing"
# Calibrated to mirror professional grading standards (e.g. Resume Worded)
WEIGHTS = {
    "quantified_impact": 0.30,       # Impact & Achievements
    "content_quality": 0.15,         # Writing Quality
    "formatting_parsability": 0.15,  # ATS Compatibility
    "experience_quality": 0.10,      # Experience depth/gaps
    "keyword_match": 0.10,           # Skills matching
    "section_completeness": 0.08,    # Resume Sections
    "growth_signals": 0.05,          # Leadership & Growth
    "education_completeness": 0.03,  # Education
    "contact_completeness": 0.02,    # Contact Information
    "style": 0.02,                   # Formatting Consistency
}

# Baseline mode: Uses hard_skill_density instead of keyword_match
BASELINE_WEIGHTS = {
    "quantified_impact": 0.30,
    "content_quality": 0.15,
    "formatting_parsability": 0.15,
    "experience_quality": 0.10,
    "hard_skill_density": 0.10,
    "section_completeness": 0.08,
    "growth_signals": 0.05,
    "education_completeness": 0.03,
    "contact_completeness": 0.02,
    "style": 0.02,
}

# Red flags apply as a hard cap, not a weighted component
REDFLAG_SCORE_CAP = 60  # if any red flag fires, overall score cannot exceed this


def calculate_ats_score(checks: Dict, redflags: Dict = None, debug: bool = False, weights_override: Dict = None) -> Dict:
    active_weights = weights_override if weights_override else WEIGHTS
    
    # In baseline mode BASELINE_WEIGHTS includes "hard_skill_density" replacing "keyword_match".
    # We must only validate keys that exist in the weight set.
    required_keys = set(k for k, w in active_weights.items() if w > 0)
    missing = [k for k in required_keys if k not in checks]
    if missing:
        raise ValueError(f"Missing required check scores: {missing}. ")

    contributions = {k: round(checks.get(k, 0.0) * active_weights.get(k, 0.0), 4) for k in active_weights}
    overall_0_1 = sum(contributions.values())
    overall_100 = round(overall_0_1 * 100, 1)

    capped = False
    if redflags and any(v.get("penalty", 0) > 0 for v in redflags.values() if isinstance(v, dict)):
        if overall_100 > REDFLAG_SCORE_CAP:
            overall_100 = REDFLAG_SCORE_CAP
            capped = True

    result = {
        "overall_score": overall_100,
        "redflag_capped": capped,
    }

    if debug:
        result["breakdown"] = {
            "raw_check_scores": checks,
            "weights": active_weights,
            "weighted_contributions": contributions,
            "sum_of_contributions_0_1": round(overall_0_1, 4),
            "redflags": redflags or {},
        }

    return result


# NOTE: build_overall_score_report() was removed — it referenced keys that don't
# exist in the actual checks dict and was never called. Use calculate_ats_score() instead.


SKILL_CATEGORIES = {
    "programming_languages": ["python", "java", "javascript", "typescript", "c++", "go", "rust"],
    "frameworks": ["react", "django", "fastapi", "spring", "next.js", "flask", "express"],
    "databases": ["postgresql", "mysql", "mongodb", "redis", "qdrant", "sqlite"],
    "cloud_platforms": ["aws", "azure", "gcp", "vercel", "heroku"],
    "devops_tools": ["docker", "kubernetes", "jenkins", "github actions", "terraform"],
    "ai_ml": ["tensorflow", "pytorch", "scikit-learn", "langchain", "huggingface"],
}


def categorize_skills(resume_skills, jd_required_skills, jd_preferred_skills=None):
    jd_preferred_skills = jd_preferred_skills or []
    resume_set = {s.lower() for s in resume_skills}
    required_set = {s.lower() for s in jd_required_skills}
    preferred_set = {s.lower() for s in jd_preferred_skills}

    result = {
        "required_skills_present": sorted(resume_set & required_set),
        "required_skills_missing": sorted(required_set - resume_set),
        "preferred_skills_present": sorted(resume_set & preferred_set),
        "preferred_skills_missing": sorted(preferred_set - resume_set),
        "by_category": {},
    }
    for category, known_skills in SKILL_CATEGORIES.items():
        known_set = {s.lower() for s in known_skills}
        result["by_category"][category] = sorted(resume_set & known_set)
    return result


WEAK_OPENERS = {"assisted", "helped", "worked on", "responsible for", "involved in"}
STRONG_ACTION_VERB_PATTERN = re.compile(r"^[A-Z][a-z]+(ed|d)\b")


def analyze_bullet(bullet):
    words = bullet.strip().split()
    first_word = words[0].lower() if words else ""
    starts_with_weak = any(bullet.lower().startswith(w) for w in WEAK_OPENERS)
    starts_with_action_verb = bool(STRONG_ACTION_VERB_PATTERN.match(bullet.strip())) and not starts_with_weak
    has_number = bool(re.search(r"\d", bullet))
    word_count = len(words)

    flags = []
    if starts_with_weak:
        flags.append("weak_opener")
    if not has_number:
        flags.append("not_quantified")
    if word_count < 5:
        flags.append("too_short")
    if word_count > 30:
        flags.append("too_long")

    return {
        "bullet": bullet,
        "starts_with_action_verb": starts_with_action_verb,
        "is_quantified": has_number,
        "word_count": word_count,
        "flags": flags,
        "quality": "strong" if not flags else ("weak" if len(flags) >= 2 else "needs_improvement"),
    }


def analyze_all_bullets(bullets):
    results = [analyze_bullet(b) for b in bullets]
    return {
        "bullets": results,
        "strong_count": sum(1 for r in results if r["quality"] == "strong"),
        "weak_count": sum(1 for r in results if r["quality"] == "weak"),
    }


def build_jd_match_report(resume_data, jd_data):
    resume_skills = {s.lower() for s in resume_data.get("skills", [])}
    jd_skills = {s.lower() for s in jd_data.get("skills", [])}
    skill_overlap_pct = round(len(resume_skills & jd_skills) / max(len(jd_skills), 1) * 100, 1)

    title_match = resume_data.get("target_title", "").lower() == jd_data.get("title", "").lower()

    resume_years = resume_data.get("years_experience", 0)
    jd_min_years = jd_data.get("min_years_experience", 0)
    experience_match = resume_years >= jd_min_years

    resume_degree = resume_data.get("degree", "").lower()
    jd_required_degree = jd_data.get("required_degree", "").lower()
    education_match = jd_required_degree in resume_degree if jd_required_degree else True

    resume_certs = {c.lower() for c in resume_data.get("certifications", [])}
    jd_certs = {c.lower() for c in jd_data.get("required_certifications", [])}
    cert_match_pct = round(len(resume_certs & jd_certs) / max(len(jd_certs), 1) * 100, 1) if jd_certs else 100.0

    return {
        "job_title_match": title_match,
        "skill_overlap_pct": skill_overlap_pct,
        "experience_match": experience_match,
        "education_match": education_match,
        "certification_match_pct": cert_match_pct,
    }


def check_missing_info(resume_data):
    checks = {
        "phone": bool(resume_data.get("phone")),
        "email": bool(resume_data.get("email")),
        "linkedin": bool(resume_data.get("linkedin_url")),
        "github": bool(resume_data.get("github_url")),
        "portfolio": bool(resume_data.get("portfolio_url")),
        "summary": bool(resume_data.get("summary")),
        "skills": bool(resume_data.get("skills")),
        "dates": bool(resume_data.get("has_dates")),
    }
    missing = [k for k, present in checks.items() if not present]
    return {"present": checks, "missing": missing}


def build_best_practices_checklist(structure_result, consistency_result, file_format, uses_graphics):
    return {
        "standard_section_headings": not structure_result.get("nonstandard_headings"),
        "reverse_chronological_order": structure_result.get("is_reverse_chronological", True),
        "consistent_date_format": consistency_result["date_format_check"]["penalty"] == 0 if consistency_result else True,
        "consistent_bullet_style": consistency_result["bullet_check"]["penalty"] == 0 if consistency_result else True,
        "standard_file_type": file_format.lower() in ("pdf", "docx"),
        "no_excessive_graphics": not uses_graphics,
    }


def check_parsing_confidence(extracted_fields):
    expected = ["name", "email", "phone", "skills", "education", "experience", "dates", "job_titles"]
    found = {f: bool(extracted_fields.get(f)) for f in expected}
    confidence = round(sum(found.values()) / len(expected), 3)
    return {"fields_found": found, "parsing_confidence": confidence}
