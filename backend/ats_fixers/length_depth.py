from agents.llm_client import LLMClient


def _get_bullets(item: dict, section: str) -> list:
    if section == "experience":
        return item.get("bullet_points") or item.get("bullets") or []
    return item.get("bullets") or item.get("bullet_points") or []


def _bullet_field(item: dict, section: str) -> str:
    if section == "experience":
        return "bullet_points" if "bullet_points" in item else "bullets"
    return "bullets" if "bullets" in item else "bullet_points"


def get_flags(resume_json: dict) -> list:
    """
    Flag bullets that are too short and ask the user to expand them.
    """
    changes = []
    sections = ["experience", "projects"]

    for section in sections:
        items = resume_json.get(section) or []
        for i, item in enumerate(items):
            bullets = _get_bullets(item, section)
            field = _bullet_field(item, section)
            for j, bullet in enumerate(bullets):
                words = bullet.split()
                if len(words) < 8:
                    changes.append({
                        "section": section,
                        "item_index": i,
                        "bullet_index": j,
                        "field": field,
                        "original": bullet,
                        "proposed": "This bullet is very short. Can you provide more detail on what you did or the impact it had?",
                        "reason": "Bullet is too brief to provide meaningful detail to recruiters.",
                        "type": "question"
                    })
    return changes


def apply_fix_with_answer(original_bullet: str, user_answer: str) -> str:
    """
    Called after user provides more detail for a short bullet.
    """
    client = LLMClient("bullet_rewriter")

    system_prompt = (
        "You are a strict text editor. Rewrite the original bullet point to include the user's additional details. "
        "Do not invent any new facts, numbers, or skills. Combine the original sentence and the user's answer into one clear, professional bullet point."
    )

    user_prompt = (
        f"Original sentence: {original_bullet}\n"
        f"User's additional details: {user_answer}\n\n"
        "Return ONLY the rewritten sentence. No markdown, no explanations."
    )

    try:
        return client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=False
        ).strip().strip('"\'')
    except Exception:
        return original_bullet
