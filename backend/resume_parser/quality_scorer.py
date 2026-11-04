"""
Phase 5 — Resume Quality Scorer
=================================
Computes objective, rule-based quality and completeness metrics.

Rules:
- All scoring is DETERMINISTIC (same input → same output, no randomness)
- Scores are based on presence/absence/richness of data
- NO AI/LLM involved
- NO fabrication or suggestions — only measurement

Output shape:
{
  "completeness": {
    "overall":  0.82,    ← 0.0 to 1.0
    "contact":  1.0,
    "experience": 0.75,
    "education":  1.0,
    "skills":     0.9,
    "summary":    1.0,
    "certifications": 0.5,
    "languages":  0.0
  },
  "quality": {
    "overall":         0.74,
    "bulletStrength":  0.8,   ← bullets have action verbs + metrics
    "experienceDepth": 0.7,   ← avg bullets per role
    "skillDiversity":  0.65,  ← spread across categories
    "consistentDates": True,
    "hasQuantifiedImpact": True,
    "totalYearsExperience": 6.5
  },
  "flags": [
    {"type": "warning", "field": "experience", "message": "..."},
    ...
  ]
}
"""

import re
from typing import Optional

# ─── Action verb library (for bullet strength scoring) ────────────────────────
_ACTION_VERBS = {
    "led", "built", "developed", "designed", "implemented", "created", "launched",
    "managed", "delivered", "optimized", "reduced", "increased", "improved",
    "architected", "spearheaded", "drove", "established", "deployed", "migrated",
    "automated", "streamlined", "collaborated", "mentored", "researched", "analyzed",
    "engineered", "scaled", "refactored", "debugged", "integrated", "authored",
    "coordinated", "executed", "facilitated", "generated", "grew", "identified",
    "initiated", "led", "maintained", "negotiated", "partnered", "proposed",
    "revamped", "secured", "trained", "transformed", "upgraded", "utilized",
    "validated", "won", "wrote", "shipped"
}

# Quantified impact: numbers, percentages, dollar amounts, time savings
_METRIC_PATTERN = re.compile(
    r"\b\d+\.?\d*\s*(?:%|percent|x|times|k|m|million|billion|users|requests|"
    r"seconds?|minutes?|hours?|days?|weeks?|months?|years?|engineers?|"
    r"customers?|clients?|projects?|features?|bugs?|tickets?|repos?)\b",
    re.IGNORECASE
)


# ─── Public entry point ────────────────────────────────────────────────────────

def score(parsed: dict) -> dict:
    """
    Compute completeness and quality scores for a parsed resume.
    Input: normalized output from pipeline.parse_resume()
    """
    completeness = _score_completeness(parsed)
    quality      = _score_quality(parsed)
    flags        = _generate_flags(parsed, completeness, quality)

    return {
        "completeness": completeness,
        "quality":      quality,
        "flags":        flags
    }


# ─── Completeness scoring ──────────────────────────────────────────────────────

def _score_completeness(p: dict) -> dict:
    contact_score   = _score_contact_completeness(p.get("contact") or {})
    exp_score       = _score_experience_completeness(p.get("experience") or {})
    edu_score       = _score_education_completeness(p.get("education") or [])
    skills_score    = _score_skills_completeness(p.get("skills") or {})
    summary_score   = 1.0 if p.get("summary") else 0.0
    certs_score     = 1.0 if p.get("certifications") else 0.0
    languages_score = 1.0 if p.get("languages") else 0.0

    # Weighted average (experience and contact are most important)
    weights = {
        "contact":        0.20,
        "experience":     0.35,
        "education":      0.15,
        "skills":         0.15,
        "summary":        0.10,
        "certifications": 0.03,
        "languages":      0.02,
    }
    scores = {
        "contact":        round(contact_score, 2),
        "experience":     round(exp_score, 2),
        "education":      round(edu_score, 2),
        "skills":         round(skills_score, 2),
        "summary":        round(summary_score, 2),
        "certifications": round(certs_score, 2),
        "languages":      round(languages_score, 2),
    }
    overall = sum(scores[k] * weights[k] for k in weights)
    scores["overall"] = round(overall, 2)

    return scores


def _score_contact_completeness(contact: dict) -> float:
    """Score based on how many contact fields are present."""
    fields = ["name", "email", "phone", "linkedin", "github"]
    filled = sum(1 for f in fields if contact.get(f))
    return filled / len(fields)


def _score_experience_completeness(experience: dict) -> float:
    entries = experience.get("entries", [])
    if not entries:
        return 0.0

    scores = []
    for e in entries:
        field_scores = [
            1.0 if e.get("company") else 0.0,
            1.0 if e.get("title") else 0.0,
            1.0 if e.get("startDate") else 0.0,
            0.5 if e.get("endDate") or e.get("isCurrent") else 0.0,
            min(1.0, len(e.get("bullets") or []) / 3),  # up to 3 bullets = full score
        ]
        scores.append(sum(field_scores) / len(field_scores))

    return sum(scores) / len(scores)


def _score_education_completeness(education: list) -> float:
    if not education:
        return 0.0
    scores = []
    for e in education:
        field_scores = [
            1.0 if e.get("degree") else 0.0,
            1.0 if e.get("institution") else 0.0,
            0.5 if e.get("endYear") else 0.0,
            0.5 if e.get("field") else 0.0,
        ]
        scores.append(sum(field_scores) / len(field_scores))
    return sum(scores) / len(scores)


def _score_skills_completeness(skills: dict) -> float:
    count = len(skills.get("all") or [])
    if count == 0:
        return 0.0
    # Full score at 15+ skills, partial below
    return min(1.0, count / 15)


# ─── Quality scoring ───────────────────────────────────────────────────────────

def _score_quality(p: dict) -> dict:
    bullet_strength, has_quantified = _score_bullet_quality(p.get("experience") or {})
    exp_depth        = _score_experience_depth(p.get("experience") or {})
    skill_diversity  = _score_skill_diversity(p.get("skills") or {})
    consistent_dates = _check_date_consistency(p.get("experience") or {})
    total_years      = (p.get("experience") or {}).get("_derived", {}).get("totalYearsExperience")

    overall = _weighted_quality_score(
        bullet_strength, exp_depth, skill_diversity,
        1.0 if consistent_dates else 0.5
    )

    return {
        "overall":              round(overall, 2),
        "bulletStrength":       round(bullet_strength, 2),
        "experienceDepth":      round(exp_depth, 2),
        "skillDiversity":       round(skill_diversity, 2),
        "consistentDates":      consistent_dates,
        "hasQuantifiedImpact":  has_quantified,
        "totalYearsExperience": total_years,
    }


def _score_bullet_quality(experience: dict) -> tuple[float, bool]:
    """
    Score bullet quality based on:
    - Action verb usage (starts with strong verb)
    - Presence of quantified metrics
    Returns (score 0-1, has_any_quantified_impact)
    """
    all_bullets = []
    for e in experience.get("entries", []):
        all_bullets.extend(e.get("bullets") or [])

    if not all_bullets:
        return 0.0, False

    action_verb_count = 0
    metric_count = 0

    for bullet in all_bullets:
        words = bullet.strip().split()
        if words and words[0].lower().rstrip(".,;") in _ACTION_VERBS:
            action_verb_count += 1
        if _METRIC_PATTERN.search(bullet):
            metric_count += 1

    action_verb_ratio = action_verb_count / len(all_bullets)
    metric_ratio = metric_count / len(all_bullets)
    has_quantified = metric_count > 0

    # Weighted: action verbs 60%, metrics 40%
    score = (action_verb_ratio * 0.6) + (metric_ratio * 0.4)
    return score, has_quantified


def _score_experience_depth(experience: dict) -> float:
    """Average bullets per experience entry (max score at 4+ bullets)."""
    entries = experience.get("entries", [])
    if not entries:
        return 0.0
    avg_bullets = sum(len(e.get("bullets") or []) for e in entries) / len(entries)
    return min(1.0, avg_bullets / 4)


def _score_skill_diversity(skills: dict) -> float:
    """Score diversity based on number of distinct categories."""
    categories = skills.get("byCategory", {})
    num_cats = len([c for c in categories if categories[c]])
    # Full score at 5+ categories
    return min(1.0, num_cats / 5)


def _check_date_consistency(experience: dict) -> bool:
    """
    Check that dates are consistent:
    - No future start dates (unless current)
    - End >= Start for each entry
    """
    from datetime import datetime
    now = datetime.now()
    entries = experience.get("entries", [])

    for e in entries:
        start = e.get("startDate")
        end   = e.get("endDate")
        is_current = e.get("isCurrent", False)

        if not start:
            continue

        try:
            sy, sm = map(int, start.split("-"))
            start_dt = datetime(sy, sm, 1)
            # Start date shouldn't be in the future
            if start_dt > now:
                return False
            if end and not is_current:
                ey, em = map(int, end.split("-"))
                end_dt = datetime(ey, em, 1)
                if end_dt < start_dt:
                    return False
        except Exception:
            continue

    return True


def _weighted_quality_score(*scores) -> float:
    """Simple average of quality sub-scores."""
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


# ─── Flag generation ───────────────────────────────────────────────────────────

def _generate_flags(parsed: dict, completeness: dict, quality: dict) -> list:
    """
    Generate human-readable flags for missing/weak sections.
    Flags are informational — never prescriptive about what to write.
    """
    flags = []

    # ── Contact flags ──────────────────────────────────────────────────────────
    contact = parsed.get("contact") or {}
    if not contact.get("email"):
        flags.append({"type": "error", "field": "contact.email",
                      "message": "No email address found."})
    if not contact.get("phone"):
        flags.append({"type": "warning", "field": "contact.phone",
                      "message": "No phone number found."})
    if not contact.get("linkedin"):
        flags.append({"type": "info", "field": "contact.linkedin",
                      "message": "No LinkedIn URL found."})
    if not contact.get("name"):
        flags.append({"type": "warning", "field": "contact.name",
                      "message": "Candidate name could not be extracted."})

    # ── Experience flags ───────────────────────────────────────────────────────
    experience = parsed.get("experience") or {}
    entries = experience.get("entries", [])
    if not entries:
        flags.append({"type": "error", "field": "experience",
                      "message": "No work experience entries found."})
    else:
        for i, e in enumerate(entries):
            if not e.get("bullets"):
                flags.append({"type": "warning", "field": f"experience[{i}].bullets",
                               "message": f"Role '{e.get('title', 'Unknown')}' at '{e.get('company', 'Unknown')}' has no bullet points."})
            if not e.get("startDate"):
                flags.append({"type": "warning", "field": f"experience[{i}].dates",
                               "message": f"Role '{e.get('title', 'Unknown')}' has no start date."})

    # ── Bullet quality flags ────────────────────────────────────────────────────
    if quality.get("bulletStrength", 1.0) < 0.4:
        flags.append({"type": "warning", "field": "experience.bullets",
                      "message": "Most bullets lack action verbs or quantified results."})
    if not quality.get("hasQuantifiedImpact"):
        flags.append({"type": "info", "field": "experience.bullets",
                      "message": "No quantified impact found in experience bullets (no numbers/percentages)."})

    # ── Education flags ─────────────────────────────────────────────────────────
    education = parsed.get("education") or []
    if not education:
        flags.append({"type": "warning", "field": "education",
                      "message": "No education entries found."})

    # ── Skills flags ────────────────────────────────────────────────────────────
    skills = parsed.get("skills") or {}
    skill_count = len(skills.get("all") or [])
    if skill_count == 0:
        flags.append({"type": "error", "field": "skills",
                      "message": "No skills found."})
    elif skill_count < 5:
        flags.append({"type": "warning", "field": "skills",
                      "message": f"Only {skill_count} skills detected. Consider adding more."})

    # ── Summary flag ────────────────────────────────────────────────────────────
    if not parsed.get("summary"):
        flags.append({"type": "info", "field": "summary",
                      "message": "No professional summary section found."})

    # ── Date consistency ────────────────────────────────────────────────────────
    if not quality.get("consistentDates", True):
        flags.append({"type": "error", "field": "experience.dates",
                      "message": "Date inconsistency detected (end date before start date, or future dates)."})

    # ── Employment gaps ────────────────────────────────────────────────────────
    gaps = (experience.get("_derived") or {}).get("employmentGaps", [])
    for gap in gaps:
        if gap.get("months", 0) >= 6:
            flags.append({"type": "info", "field": "experience.gaps",
                           "message": f"Employment gap of {gap['months']} months detected between {gap['from']} and {gap['to']}."})

    return flags
