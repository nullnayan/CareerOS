"""
Repetition checker.

Two patterns worth catching separately:
1. Verbatim / near-identical bullets reused across roles or projects
   (common when people copy-paste and forget to tailor).
2. A single opening word/phrase dominating most bullets
   ("Responsible for..." repeated everywhere).

Uses simple difflib string similarity so no extra dependency is
required (swap in rapidfuzz.fuzz.ratio for speed on large documents
if you already have it installed).
"""

from collections import Counter
from difflib import SequenceMatcher
from typing import Dict, List


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def check_duplicate_bullets(bullets: List[str], similarity_threshold: float = 0.85) -> Dict:
    duplicates = []
    for i in range(len(bullets)):
        for j in range(i + 1, len(bullets)):
            sim = _similarity(bullets[i], bullets[j])
            if sim >= similarity_threshold:
                duplicates.append({
                    "bullet_a": bullets[i],
                    "bullet_b": bullets[j],
                    "similarity": round(sim, 3),
                })

    penalty = min(len(duplicates) * 0.08, 0.3)
    return {"duplicate_pairs": duplicates, "penalty": round(penalty, 3)}


def check_repeated_openers(bullets: List[str], dominance_threshold: float = 0.4) -> Dict:
    """
    Flags if a single opening word (or two-word phrase) accounts for
    more than dominance_threshold of all bullets — e.g. "Responsible
    for" opening 40%+ of bullets.
    """
    openers = []
    for b in bullets:
        words = b.strip().split()
        if not words:
            continue
        opener = " ".join(words[:2]).lower().rstrip(",.:;")
        openers.append(opener)

    if not openers:
        return {"dominant_opener": None, "penalty": 0.0}

    counts = Counter(openers)
    most_common_opener, count = counts.most_common(1)[0]
    share = count / len(openers)

    penalty = 0.15 if share >= dominance_threshold else 0.0

    return {
        "opener_counts": dict(counts),
        "dominant_opener": most_common_opener,
        "dominant_share": round(share, 3),
        "penalty": penalty,
    }


def combined_repetition_score(bullets: List[str]) -> Dict:
    dup_result = check_duplicate_bullets(bullets)
    opener_result = check_repeated_openers(bullets)

    total_penalty = min(dup_result["penalty"] + opener_result["penalty"], 0.4)
    score = round(1.0 - total_penalty, 3)

    return {
        "score": score,  # feed into content_quality bucket
        "duplicate_check": dup_result,
        "opener_check": opener_result,
    }
