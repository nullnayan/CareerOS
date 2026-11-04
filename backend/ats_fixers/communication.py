import re
from agents.llm_client import LLMClient

# Basic list of irregular past participles
IRREGULAR_PP = ["done", "seen", "gone", "built", "made", "taken", "written", "given", "found", "led"]
FILLER_WORDS = ["very", "really", "just", "basically", "literally", "actually", "simply", "quite", "rather", "somewhat"]


def _detect_communication_issues(text: str):
    """Detects passive voice, pronouns, and filler words in a text."""
    issues = []

    # 1. Passive Voice Detection
    irregs = "|".join(IRREGULAR_PP)
    passive_pattern = re.compile(rf'\b(was|were|been|being)\s+(\w+ed\b|\b({irregs})\b)', re.IGNORECASE)
    if passive_pattern.search(text):
        issues.append("Passive voice")

    # 2. Personal Pronouns
    pronoun_pattern = re.compile(r'\b(I|me|my|mine|we|us|our)\b', re.IGNORECASE)
    if pronoun_pattern.search(text):
        issues.append("Personal pronouns")

    # 3. Filler Words
    fillers = "|".join(FILLER_WORDS)
    filler_pattern = re.compile(rf'\b({fillers})\b', re.IGNORECASE)
    if filler_pattern.search(text):
        issues.append("Filler words")

    return issues


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
    Detects communication issues and uses narrow AI to fix just the flagged sentence.
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
                issues = _detect_communication_issues(bullet)
                if issues:
                    issue_str = ", ".join(issues)

                    system_prompt = (
                        f"You are a strict text editor. Rewrite ONLY this sentence to fix: {issue_str}. "
                        "Do not change any fact, number, or claim in the sentence. Keep the same meaning, but make it as concise, active, and readable as possible."
                    )

                    user_prompt = (
                        f"Original sentence:\n{bullet}\n\n"
                        "Return ONLY the rewritten sentence. No markdown, no explanations."
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
                                "reason": f"Fixed communication issues: {issue_str}",
                                "type": "rewrite"
                            })
                    except Exception:
                        pass

    return changes
