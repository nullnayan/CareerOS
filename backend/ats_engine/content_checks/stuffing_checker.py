import re
from collections import Counter
from typing import Dict, List

# crude but effective: a bullet with a real verb-object structure has
# at least one verb-like word followed by more prose, not just a comma list
WEAK_STRUCTURE_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9+./#\- ]+,\s*){4,}[A-Za-z0-9+./#\- ]+\.?\s*$"
)


def check_bullet_stuffing(bullets: List[str]) -> Dict:
    """
    Flags bullets that are just comma-separated token dumps with no
    sentence structure — the pattern real parsers down-weight.
    """
    flagged = []
    for b in bullets:
        token_count = len([t for t in re.split(r"[,\s]+", b) if t])
        has_verb_structure = not WEAK_STRUCTURE_PATTERN.match(b.strip())
        if token_count > 7 and not has_verb_structure:
            flagged.append(b)

    penalty = min(len(flagged) * 0.08, 0.4)  # cap penalty at 40% of this check's weight
    return {
        "flagged_bullets": flagged,
        "flagged_count": len(flagged),
        "stuffing_penalty": round(penalty, 3),
    }


def check_keyword_density(resume_text: str, jd_keywords: List[str], max_natural_repeats: int = 4) -> Dict:
    """
    Flags any single keyword repeated far more than natural writing
    would produce. Real guidance: 2-3 natural repeats across summary/
    skills/experience is normal; beyond ~4-5 is stuffing.
    """
    text_lower = resume_text.lower()
    counts = Counter()
    for kw in jd_keywords:
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue
        counts[kw] = len(re.findall(r"\b" + re.escape(kw_lower) + r"\b", text_lower))

    stuffed = {kw: c for kw, c in counts.items() if c > max_natural_repeats}
    penalty = min(len(stuffed) * 0.1, 0.4)

    return {
        "keyword_counts": dict(counts),
        "stuffed_keywords": stuffed,
        "density_penalty": round(penalty, 3),
    }


def combined_stuffing_score(bullets: List[str], resume_text: str, jd_keywords: List[str]) -> Dict:
    """
    Returns a single 0-1 score (1 = clean, 0 = heavily stuffed) plus
    the raw detail, so you can feed `score` straight into your
    weighted scorer's `content_quality` or a new `authenticity` bucket.
    """
    bullet_result = check_bullet_stuffing(bullets)
    density_result = check_keyword_density(resume_text, jd_keywords)

    total_penalty = min(bullet_result["stuffing_penalty"] + density_result["density_penalty"], 0.8)
    score = round(1.0 - total_penalty, 3)

    return {
        "score": score,  # plug into scorer weights
        "bullet_check": bullet_result,
        "density_check": density_result,
    }
