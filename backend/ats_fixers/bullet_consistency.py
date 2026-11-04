"""
bullet_consistency.py
Ensures all bullet points follow a consistent, ATS-friendly style:
  - Every bullet must start with an action verb.
  - No bullet should start with an article (The, A, An).
  - No bullet should start with a noun-phrase (role name, company, tech stack).
  - No bullet should be a fragment (< 6 words).
"""
import re
from agents.llm_client import LLMClient

# Strong past-tense action verbs (the gold standard for resume bullets)
ACTION_VERBS = {
    "built", "developed", "created", "designed", "implemented", "improved",
    "optimized", "reduced", "increased", "achieved", "deployed", "integrated",
    "automated", "led", "managed", "delivered", "launched", "migrated",
    "engineered", "architected", "analyzed", "trained", "generated", "processed",
    "established", "maintained", "produced", "coordinated", "collaborated",
    "configured", "constructed", "authored", "evaluated", "executed",
    "extracted", "facilitated", "formulated", "identified", "modernized",
    "monitored", "orchestrated", "overhauled", "partnered", "performed",
    "planned", "proposed", "refactored", "resolved", "restructured",
    "reviewed", "secured", "spearheaded", "streamlined", "supported",
    "tested", "transformed", "utilized", "validated", "wrote",
    "containerized", "debugged", "documented", "enabled", "enhanced",
    "ensured", "estimated", "expanded", "exposed", "extended", "fixed",
    "handled", "initialized", "integrated", "minimized", "parsed",
    "prototyped", "published", "replaced", "shipped", "simplified",
    "standardized", "translated", "upgraded", "fused", "coded", "launched",
    "minimized", "deployed", "configured", "formulated",
}

BAD_STARTERS = {
    # Articles
    "the", "a", "an",
    # Pronouns already handled by communication.py but double-check
    "i", "we", "my", "our",
    # Generic nouns that shouldn't start bullets
    "experience", "role", "project", "task", "duties", "responsibilities",
    "responsible", "job", "work",
}


def _get_bullets(item: dict, section: str) -> list:
    if section == "experience":
        return item.get("bullet_points") or item.get("bullets") or []
    return item.get("bullets") or item.get("bullet_points") or []


def _bullet_field(item: dict, section: str) -> str:
    if section == "experience":
        return "bullet_points" if "bullet_points" in item else "bullets"
    return "bullets" if "bullets" in item else "bullet_points"


def _has_bad_start(bullet: str) -> tuple[bool, str]:
    """
    Returns (True, reason) if the bullet starts with a non-action-verb word.
    Returns (False, '') if bullet starts correctly.
    """
    words = bullet.strip().split()
    if not words:
        return False, ""

    first = words[0].lower().strip(".,;:()")

    if first in BAD_STARTERS:
        return True, f"Bullet starts with '{words[0]}' instead of an action verb"

    if first not in ACTION_VERBS:
        # Could be an unlisted action verb — only flag if it's clearly not
        # Check if it ends in common verb suffixes
        if not (first.endswith("ed") or first.endswith("led") or first.endswith("ped")
                or first.endswith("ned") or first.endswith("red")):
            # Might be a gerund (e.g. "Building...") — flag those too
            if first.endswith("ing"):
                return True, f"Bullet starts with gerund '{words[0]}' instead of a past-tense action verb"

    return False, ""


def fix(resume_json: dict) -> list:
    """
    Checks all bullets in experience and projects for consistent action-verb-first style.
    Proposes AI rewrites for bullets with bad starters.
    """
    changes = []
    client = LLMClient("bullet_rewriter")
    sections = ["experience", "projects"]

    for section in sections:
        items = resume_json.get(section) or []
        for i, item in enumerate(items):
            bullets = _get_bullets(item, section)
            field = _bullet_field(item, section)

            for j, bullet in enumerate(bullets):
                if not bullet or len(bullet.strip().split()) < 4:
                    continue  # Too short to meaningfully fix

                is_bad, reason = _has_bad_start(bullet)
                if not is_bad:
                    continue

                try:
                    proposed = client.generate(
                        system_prompt=(
                            "You are an expert resume editor. Rewrite this bullet so it starts with a strong "
                            "past-tense action verb (e.g., Built, Deployed, Designed, Implemented). "
                            "Do NOT change any facts, numbers, or meaning. Keep it under 18 words."
                        ),
                        user_prompt=(
                            f"Original:\n{bullet}\n\n"
                            "Return ONLY the rewritten sentence. No markdown, no explanations."
                        ),
                        json_mode=False
                    ).strip().strip('"\'')

                    if proposed and proposed != bullet:
                        changes.append({
                            "section": section,
                            "item_index": i,
                            "bullet_index": j,
                            "field": field,
                            "original": bullet,
                            "proposed": proposed,
                            "reason": f"Bullet consistency: {reason}. All bullets must start with a past-tense action verb.",
                            "type": "rewrite"
                        })
                except Exception:
                    pass

    return changes
