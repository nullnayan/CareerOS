"""
services/readability_scorer.py
==============================
Computes objective readability metrics for a resume JSON:
- Flesch Reading Ease
- Flesch-Kincaid Grade Level
- Passive Voice Detection
- Cliché / Buzzword Detection
- Bullet Density Metrics
"""

import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# Common business buzzwords / clichés to flag
BUZZWORDS_LIST = {
    "synergy", "rockstar", "thought leader", "go-getter", "hardworking",
    "out of the box", "out-of-the-box", "ninja", "wizard", "self-starter",
    "results-driven", "detail-oriented", "team player", "guru", "dynamic",
    "passionate professional", "bottom line", "game changer", "cutting edge"
}

# Passive voice detection pattern
PASSIVE_VOICE_REGEX = re.compile(
    r'\b(am|is|are|was|were|be|been|being)\s+([a-z]+ed|built|made|done|written|led|run|sent|kept|found)\b',
    re.IGNORECASE
)


def score_readability(resume_json: dict) -> Dict:
    """
    Calculates readability, grade level, passive voice, and cliché count for a resume JSON.
    """
    try:
        import textstat
    except ImportError:
        textstat = None

    bullets = []
    text_chunks = []

    summary = resume_json.get("summary", "")
    if summary and isinstance(summary, str):
        text_chunks.append(summary)

    for section in ["experience", "projects"]:
        items = resume_json.get(section, []) or []
        for item in items:
            if isinstance(item, dict):
                b_list = item.get("bullet_points") or item.get("bullets") or []
                for b in b_list:
                    if isinstance(b, str) and b.strip():
                        bullets.append(b.strip())
                        text_chunks.append(b.strip())

    full_text = " ".join(text_chunks) if text_chunks else "Empty resume text."

    # Flesch Readability Metrics
    if textstat:
        try:
            flesch_reading_ease = round(textstat.flesch_reading_ease(full_text), 1)
            flesch_kincaid_grade = round(textstat.flesch_kincaid_grade(full_text), 1)
        except Exception:
            flesch_reading_ease = 65.0
            flesch_kincaid_grade = 9.0
    else:
        flesch_reading_ease = 65.0
        flesch_kincaid_grade = 9.0

    # Passive voice detection
    passive_matches = PASSIVE_VOICE_REGEX.findall(full_text)
    passive_count = len(passive_matches)
    passive_snippets = [f"{m[0]} {m[1]}" for m in passive_matches[:5]]

    # Buzzword / Cliché detection
    words_lower = set(re.findall(r'\b[a-z\-]+\b', full_text.lower()))
    found_buzzwords = list(BUZZWORDS_LIST.intersection(words_lower))

    # Bullet density metrics
    total_words = len(re.findall(r'\b\w+\b', full_text))
    total_bullets = len(bullets)
    avg_words_per_bullet = round(total_words / total_bullets, 1) if total_bullets > 0 else 0.0

    # Readability Score calculation (out of 100)
    grade_penalty = max(0, abs(flesch_kincaid_grade - 10.0) * 3)
    passive_penalty = min(20, passive_count * 4)
    buzzword_penalty = min(15, len(found_buzzwords) * 5)
    overall_readability_score = max(30, min(100, int(round(100 - grade_penalty - passive_penalty - buzzword_penalty))))

    return {
        "overall_readability_score": overall_readability_score,
        "flesch_reading_ease": flesch_reading_ease,
        "flesch_kincaid_grade": flesch_kincaid_grade,
        "passive_voice_count": passive_count,
        "passive_snippets": passive_snippets,
        "buzzword_flags": found_buzzwords,
        "total_bullets": total_bullets,
        "avg_words_per_bullet": avg_words_per_bullet,
        "total_words": total_words
    }
