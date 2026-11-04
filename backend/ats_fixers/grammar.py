import re
from agents.llm_client import LLMClient

# Common grammar mistakes that AI can safely fix
GRAMMAR_PATTERNS = [
    # Tense mixing - past/present in the same bullet
    (r"\b(ensure|develop|manage|lead|create|build|design|implement|maintain)\b", "present-tense verb in likely past-role bullet"),
    # Missing articles / agreement issues caught by pattern
    (r"\bsetup\b", "setup used as verb (should be 'set up')"),
    (r"\bspell-check\b|\bspellcheck\b", "spelling inconsistency"),
]

PRESENT_VERBS = {
    "build", "develop", "design", "create", "manage", "lead", "ensure", "maintain",
    "work", "implement", "write", "run", "deploy", "test", "review", "handle",
    "support", "improve", "monitor", "analyze", "collaborate", "integrate"
}

PAST_TENSE_MAP = {
    "build": "built",
    "develop": "developed",
    "design": "designed",
    "create": "created",
    "manage": "managed",
    "lead": "led",
    "ensure": "ensured",
    "maintain": "maintained",
    "work": "worked",
    "implement": "implemented",
    "write": "wrote",
    "run": "ran",
    "deploy": "deployed",
    "test": "tested",
    "review": "reviewed",
    "handle": "handled",
    "support": "supported",
    "improve": "improved",
    "monitor": "monitored",
    "analyze": "analyzed",
    "collaborate": "collaborated",
    "integrate": "integrated",
    "contribute": "contributed",
    "setup": "set up",
    "Setup": "Set up",
}


def _is_current_role(item: dict) -> bool:
    """Returns True if this is a current/ongoing role."""
    end = (
        item.get("end_date") or item.get("endDate") or ""
    ).strip().lower()
    return end in ["present", "current", "now", ""]


def _get_first_verb(bullet: str) -> str:
    """Returns the first word of the bullet in lowercase."""
    words = bullet.strip().split()
    return words[0].lower().strip(".,;:()") if words else ""


def _starts_with_present_verb(bullet: str) -> bool:
    """Returns True if bullet starts with a present-tense verb (should be past)."""
    first = _get_first_verb(bullet)
    return first in PRESENT_VERBS


def _get_bullets(item: dict, section: str) -> list:
    if section == "experience":
        return item.get("bullet_points") or item.get("bullets") or []
    return item.get("bullets") or item.get("bullet_points") or []


def _bullet_field(item: dict, section: str) -> str:
    if section == "experience":
        return "bullet_points" if "bullet_points" in item else "bullets"
    return "bullets" if "bullets" in item else "bullet_points"


def _quick_tense_fix(bullet: str) -> str:
    """
    Fast rule-based tense fix for bullets starting with a known present-tense verb.
    Returns fixed bullet or original if no simple map exists.
    """
    words = bullet.strip().split()
    if not words:
        return bullet
    first = words[0].strip(".,;:()")
    fixed = PAST_TENSE_MAP.get(first) or PAST_TENSE_MAP.get(first.lower())
    if not fixed:
        return bullet
    # Preserve original capitalisation style
    if first[0].isupper():
        fixed = fixed[0].upper() + fixed[1:]
    return fixed + bullet[len(first):]


def fix(resume_json: dict) -> list:
    """
    Grammar & tense consistency fixer.
    1. Fixes present-tense bullets in past/finished roles.
    2. Uses AI to fix grammar issues that rule-based patterns catch but can't trivially rewrite.
    3. Projects section always uses past tense (all projects are completed).
    """
    changes = []
    client = LLMClient("bullet_rewriter")

    # ── Experience: fix tense for past roles ──────────────────────────────────
    for i, item in enumerate(resume_json.get("experience", []) or []):
        is_current = _is_current_role(item)
        bullets = _get_bullets(item, "experience")
        field = _bullet_field(item, "experience")

        for j, bullet in enumerate(bullets):
            if not bullet or not bullet.strip():
                continue

            first_verb = _get_first_verb(bullet)

            if not is_current and first_verb in PRESENT_VERBS:
                # Try fast rule-based fix first
                quick_fix = _quick_tense_fix(bullet)
                if quick_fix != bullet:
                    changes.append({
                        "section": "experience",
                        "item_index": i,
                        "bullet_index": j,
                        "field": field,
                        "original": bullet,
                        "proposed": quick_fix,
                        "reason": f"Fixed tense: past roles must use past tense ('{first_verb}' → '{PAST_TENSE_MAP.get(first_verb, '?')}').",
                        "type": "rewrite"
                    })
                else:
                    # Fall back to LLM for irregular verbs
                    try:
                        proposed = client.generate(
                            system_prompt=(
                                "You are a strict resume editor. Convert this bullet to past tense. "
                                "Only change verb tenses. Do NOT change any facts, numbers, or other words."
                            ),
                            user_prompt=f"Original:\n{bullet}\n\nReturn ONLY the past-tense rewritten sentence.",
                            json_mode=False
                        ).strip().strip('"\'')
                        if proposed and proposed != bullet:
                            changes.append({
                                "section": "experience",
                                "item_index": i,
                                "bullet_index": j,
                                "field": field,
                                "original": bullet,
                                "proposed": proposed,
                                "reason": "Fixed tense: past roles must use past tense.",
                                "type": "rewrite"
                            })
                    except Exception:
                        pass

    # ── Projects: always use past tense ──────────────────────────────────────
    for i, item in enumerate(resume_json.get("projects", []) or []):
        bullets = _get_bullets(item, "projects")
        field = _bullet_field(item, "projects")

        for j, bullet in enumerate(bullets):
            if not bullet or not bullet.strip():
                continue

            first_verb = _get_first_verb(bullet)
            if first_verb in PRESENT_VERBS:
                quick_fix = _quick_tense_fix(bullet)
                if quick_fix != bullet:
                    changes.append({
                        "section": "projects",
                        "item_index": i,
                        "bullet_index": j,
                        "field": field,
                        "original": bullet,
                        "proposed": quick_fix,
                        "reason": f"Fixed tense: project bullets must use past tense ('{first_verb}' → completed work).",
                        "type": "rewrite"
                    })

    return changes
