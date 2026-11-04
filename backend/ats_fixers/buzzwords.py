import re
from agents.llm_client import LLMClient

BUZZWORDS = [
    "hardworking", "team player", "results-driven", "go-getter",
    "detail-oriented", "self-starter", "thought leader", "synergy",
    "dynamic", "highly motivated", "proactive", "visionary", "rockstar"
]


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
    Detects clichés via curated list. Uses narrow AI to rewrite only the cliché.
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
                for word in BUZZWORDS:
                    pattern = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
                    if pattern.search(bullet):
                        system_prompt = (
                            "You are a strict text editor. Replace ONLY the specified buzzword "
                            "with more specific wording, using only facts already present in this sentence. "
                            "Do not add any new claims, numbers, or achievements. Keep the exact same meaning, but make it as concise, active, and readable as possible."
                        )

                        user_prompt = (
                            f"Buzzword to replace: '{word}'\n\n"
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
                                    "reason": f"Removed cliché buzzword: '{word}'",
                                    "type": "rewrite"
                                })
                        except Exception:
                            pass

                        # Only flag one buzzword per bullet to avoid multiple edits at once
                        break

    return changes
