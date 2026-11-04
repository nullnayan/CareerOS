import re
from typing import Dict, List

LEADERSHIP_SIGNALS = [
    "led", "managed", "mentored", "coordinated", "organized", "directed",
    "supervised", "spearheaded", "founded", "initiated", "orchestrated",
]
TEAMWORK_SIGNALS = [
    "collaborated", "partnered", "coordinated with", "cross-functional",
    "team of", "worked closely with",
]
COMMUNICATION_SIGNALS = [
    "presented", "communicated", "documented", "authored", "published",
    "reported to", "trained",
]
ANALYTICAL_SIGNALS = [
    "analyzed", "evaluated", "optimized", "researched", "modeled",
    "diagnosed", "investigated",
]

FILLER_WORDS = [
    "very", "really", "basically", "actually", "just", "quite",
    "in order to", "a lot of", "things", "stuff", "kind of", "sort of",
]
PERSONAL_PRONOUNS = [r"\bi\b", r"\bme\b", r"\bmy\b", r"\bmyself\b"]


def _count_hits(text_lower: str, phrases: List[str]) -> int:
    return sum(1 for p in phrases if p in text_lower)


def check_leadership_signals(resume_text: str) -> Dict:
    text_lower = resume_text.lower()
    leadership = _count_hits(text_lower, LEADERSHIP_SIGNALS)
    teamwork = _count_hits(text_lower, TEAMWORK_SIGNALS)
    communication = _count_hits(text_lower, COMMUNICATION_SIGNALS)
    analytical = _count_hits(text_lower, ANALYTICAL_SIGNALS)

    # cap each category so one repeated word can't dominate the score
    raw_total = min(leadership, 3) + min(teamwork, 2) + min(communication, 2) + min(analytical, 2)
    max_possible = 3 + 2 + 2 + 2
    score = round(raw_total / max_possible, 3)

    return {
        "score": score,  # 0-1, feed into a "growth_signals" bucket
        "leadership_hits": leadership,
        "teamwork_hits": teamwork,
        "communication_hits": communication,
        "analytical_hits": analytical,
    }


def check_style(resume_text: str, bullets: List[str]) -> Dict:
    text_lower = resume_text.lower()

    filler_hits = sum(text_lower.count(f) for f in FILLER_WORDS)
    pronoun_hits = sum(len(re.findall(p, text_lower)) for p in PERSONAL_PRONOUNS)

    long_bullets = [b for b in bullets if len(b.split()) > 30]
    avg_bullet_len = (sum(len(b.split()) for b in bullets) / len(bullets)) if bullets else 0

    # penalties: filler and pronouns should be near-zero on a clean resume
    penalty = 0.0
    penalty += min(filler_hits * 0.03, 0.3)
    penalty += min(pronoun_hits * 0.05, 0.3)
    penalty += min(len(long_bullets) * 0.05, 0.2)

    score = round(max(1.0 - penalty, 0.0), 3)

    return {
        "score": score,  # 0-1, feed into scorer's content_quality bucket
        "filler_word_hits": filler_hits,
        "personal_pronoun_hits": pronoun_hits,
        "long_bullets_flagged": len(long_bullets),
        "avg_bullet_word_count": round(avg_bullet_len, 1),
    }
