import re
from agents.llm_client import LLMClient

# ── Vague Ownership (Enhancv-style) ──
VAGUE_OWNERSHIP = [
    r"\bassisted with\b", r"\bassisted in\b", r"\bhelped to\b",
    r"\bhelped in\b", r"\bparticipated in\b", r"\bwas part of\b",
    r"\bcontributed to\b", r"\bsupported\b", r"\baided\b",
    r"\bwas involved in\b", r"\bplayed a role in\b",
    r"\bwas a member of\b", r"\bhad exposure to\b",
]

# ── Passive/Duty-Focused ──
PASSIVE_DUTY = [
    r"\bresponsible for\b", r"\btasked with\b", r"\bhandled\b",
    r"\bworked on\b", r"\binvolved in\b", r"\bdutied to\b",
    r"\bmanaged to\b", r"\bcharged with\b", r"\boversaw the\b",
    r"\bdealt with\b", r"\btook care of\b", r"\bwas assigned to\b",
]

# ── Filler/Vague Quantifiers ──
VAGUE_QUANTIFIERS = [
    r"\bvarious\b", r"\bnumerous\b", r"\bmultiple\b",
    r"\bseveral\b", r"\ba number of\b", r"\bsome\b",
    r"\bmany\b", r"\ba lot of\b", r"\bdiverse\b",
]

# ── Cliché Soft Skills (show-don't-tell) ──
CLICHE_SOFT_SKILLS = [
    r"\bteam player\b", r"\bhard worker\b", r"\bself-starter\b",
    r"\bdetail-oriented\b", r"\bgo-getter\b", r"\bpeople person\b",
    r"\bfast learner\b", r"\bquick learner\b", r"\bthink outside the box\b",
    r"\bwear many hats\b", r"\bpassionate about\b", r"\benthusiastic about\b",
    r"\bdedicated to\b", r"\bstrong communicator\b",
]

# Combined for backwards compatibility
WEAK_PHRASES = VAGUE_OWNERSHIP + PASSIVE_DUTY + VAGUE_QUANTIFIERS + CLICHE_SOFT_SKILLS

def _should_improve_readability(bullet: str) -> bool:
    if not bullet or not bullet.strip():
        return False
    # 1. Too long — lowered threshold to 18 words to catch dense 20-22 word bullets
    if len(bullet.split()) > 18:
        return True
    # 2. Contains personal pronouns
    if re.search(r"\b(I|me|my|we|us|our)\b", bullet, re.IGNORECASE):
        return True
    # 3. Contains weak phrases
    for phrase in WEAK_PHRASES:
        if re.search(phrase, bullet, re.IGNORECASE):
            return True
    # 4. Does not start with a verb (common passive starters)
    first_word = bullet.strip().split()[0].lower().strip(".,;:()") if bullet.strip() else ""
    if first_word in ["was", "were", "been", "being", "had", "have", "has", "did", "does", "do"]:
        return True
    # 5. Comma-chain density — 3+ commas = overly complex and hard to parse
    if bullet.count(",") >= 3:
        return True
    return False

def _get_bullets(item: dict, section: str) -> list:
    if section == "experience":
        return item.get("bullet_points") or item.get("bullets") or []
    return item.get("bullets") or item.get("bullet_points") or []

def _bullet_field(item: dict, section: str) -> str:
    if section == "experience":
        return "bullet_points" if "bullet_points" in item else "bullets"
    return "bullets" if "bullets" in item else "bullet_points"

def fix(resume_json: dict) -> list:
    """
    Overhauls weak and long bullet points into strong, concise X-Y-Z statements starting with action verbs.
    Targets bullets > 18 words, containing weak phrases, pronouns, or excessive comma-chains.
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
                if _should_improve_readability(bullet):
                    system_prompt = (
                        "You are an expert resume writer and ATS optimization specialist. "
                        "Your task is to rewrite the original bullet point to make it highly professional, punchy, and readable.\n"
                        "Follow these rules strictly:\n"
                        "1. Start with a strong, high-impact past-tense Action Verb (e.g., Spearheaded, Engineered, Optimized, Designed, Deployed).\n"
                        "2. NEVER use personal pronouns (I, me, my, we, us, our).\n"
                        "3. Do not invent any new facts, metrics, or achievements. Keep all numbers/percentages EXACTLY as they were.\n"
                        "4. HARD LIMIT: Maximum 18 words total. Cut every filler word ruthlessly.\n"
                        "5. One idea per bullet only. If the original has multiple ideas, keep only the strongest one.\n"
                        "6. Avoid chaining clauses with commas - write direct, scannable statements.\n"
                        "7. Prioritize impact: lead with the verb, follow with the result, end with the metric."
                    )

                    user_prompt = (
                        f"Original sentence:\n{bullet}\n\n"
                        "Return ONLY the rewritten sentence (max 18 words). No markdown, no explanations."
                    )

                    try:
                        proposed = client.generate(
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
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
                                "reason": "Improved readability: shortened to under 18 words with a direct action-verb-first structure.",
                                "type": "rewrite"
                            })
                    except Exception:
                        pass
    return changes
