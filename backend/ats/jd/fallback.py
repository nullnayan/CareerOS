"""
fallback.py — Rule-based JD extractor (non-tech / LLM-fallback path).

Per the calibration plan (§0.4 Bug 2 + Phase 1.3):
- Never return None. If fewer than 5 skills are found, return a JobTarget
  with extraction_confidence='low' rather than silently downgrading to baseline mode.
- The caller must check extraction_confidence and surface it to the user.
"""
import hashlib
from ..models import JobTarget, JDKeyword
from ..ontology.loader import SkillOntology

_LOW_CONFIDENCE_THRESHOLD = 5


def extract_fallback(jd_text: str, title: str, seniority: str, source_hash: str) -> JobTarget:
    """
    Rule-based extractor. Works for non-tech roles by scanning the ontology.
    Always returns a JobTarget; sets extraction_confidence based on keyword count.
    """
    onto = SkillOntology()
    jd_lower = jd_text.lower()
    keywords = []

    for skill_id, skill_data in onto._id_map.items():
        aliases = [skill_data["canonical"].lower()] + [a.lower() for a in skill_data.get("aliases", [])]

        for alias in aliases:
            # word-boundary-aware check: avoid "Go" matching inside "Django"
            import re
            if re.search(r"\b" + re.escape(alias) + r"\b", jd_lower):
                keywords.append(JDKeyword(
                    term=skill_data["canonical"],
                    skill_id=skill_id,
                    kind=skill_data["kind"],
                    jd_frequency=len(re.findall(r"\b" + re.escape(alias) + r"\b", jd_lower)),
                    required=False,
                ))
                break

    if len(keywords) == 0:
        confidence = "failed"
    elif len(keywords) < _LOW_CONFIDENCE_THRESHOLD:
        confidence = "low_confidence"
    else:
        confidence = "ok"

    # Normalise the extracted title (strip seniority prefixes)
    title_normalized = title.lower().strip()
    for prefix in ("senior ", "junior ", "lead ", "sr. ", "jr. ", "staff ", "principal "):
        if title_normalized.startswith(prefix):
            title_normalized = title_normalized[len(prefix):]
            break
    title_normalized = title_normalized.replace(" ", "_")

    return JobTarget(
        title=title,
        title_normalized=title_normalized,
        seniority=seniority,
        keywords=tuple(keywords),
        min_years=None,
        required_degree=None,
        source_hash=source_hash,
        extraction_confidence=confidence,
    )
