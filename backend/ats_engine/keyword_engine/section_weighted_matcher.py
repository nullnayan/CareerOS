from typing import Dict, List, Callable

# Priority weights — mirrors how real ATS treat section importance
SECTION_WEIGHTS = {
    "skills": 1.0,
    "experience": 1.0,
    "projects": 0.85,       # your resumes lean heavily on projects — treat close to experience
    "summary": 0.7,
    "education": 0.4,
    "certifications": 0.6,
    "other": 0.2,
}


def section_weighted_score(
    sections: Dict[str, str],
    jd_keywords: List[str],
    match_fn: Callable[[str, List[str]], float],
) -> Dict:
    """
    sections: dict like {"skills": "...", "experience": "...", "education": "..."}
    jd_keywords: list of keywords/phrases pulled from the job description
    match_fn: a function(text, keywords) -> float in range 0-1
              (wire this to your existing exact/fuzzy/semantic combined matcher)

    Returns a dict with the weighted overall score plus a per-section
    breakdown so you can see exactly where points came from.
    """
    breakdown = {}
    weighted_sum = 0.0
    weight_total = 0.0

    for section_name, text in sections.items():
        weight = SECTION_WEIGHTS.get(section_name.lower(), SECTION_WEIGHTS["other"])
        raw_score = match_fn(text, jd_keywords) if text and text.strip() else 0.0
        breakdown[section_name] = {
            "raw_match": round(raw_score, 3),
            "weight": weight,
            "contribution": round(raw_score * weight, 3),
        }
        weighted_sum += raw_score * weight
        weight_total += weight

    overall = (weighted_sum / weight_total) if weight_total > 0 else 0.0

    return {
        "keyword_match_score": round(overall, 3),  # 0-1, feed into your scorer's weights dict
        "section_breakdown": breakdown,
    }
