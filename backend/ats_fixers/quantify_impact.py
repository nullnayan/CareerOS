import re
from agents.llm_client import LLMClient


def _has_metric(text: str) -> bool:
    """Check if text contains a number, percentage, or common scale word."""
    if re.search(r'\d+', text):
        return True
    scale_words = ["hundreds", "thousands", "millions", "dozens"]
    for w in scale_words:
        if w in text.lower():
            return True
    return False


def _get_bullets(item: dict, section: str) -> list:
    """Return bullets using the correct field name for this section."""
    if section == "experience":
        return item.get("bullet_points") or item.get("bullets") or []
    return item.get("bullets") or item.get("bullet_points") or []


def _bullet_field(item: dict, section: str) -> str:
    """Return the actual field name used for bullets in this item."""
    if section == "experience":
        return "bullet_points" if "bullet_points" in item else "bullets"
    return "bullets" if "bullets" in item else "bullet_points"


def _is_quantifiable(text: str) -> bool:
    """
    Return True only if this bullet describes an action or achievement
    where a number could genuinely be added. Skip pure tech-list bullets.
    """
    lower = text.lower()
    # Too short to be a meaningful achievement bullet
    if len(text.split()) < 5:
        return False
    # Bullets that are just comma-separated tech stacks / skill lists
    # Heuristic: if >40% of words are tech keywords and there's no verb, skip it
    tech_words = {
        "react", "node", "nodejs", "express", "python", "java", "javascript",
        "typescript", "html", "css", "sql", "mongodb", "postgresql", "firebase",
        "aws", "gcp", "azure", "docker", "kubernetes", "git", "github", "flask",
        "django", "nextjs", "tailwind", "jwt", "rest", "api", "opencv", "tensorflow",
        "pytorch", "scikit", "pandas", "numpy", "c++", "c#", "kotlin", "swift",
        "android", "ios", "flutter", "dart", "graphql", "redis", "nginx", "linux"
    }
    action_verbs = {
        "built", "developed", "created", "designed", "implemented", "improved",
        "optimized", "reduced", "increased", "achieved", "deployed", "integrated",
        "automated", "led", "managed", "delivered", "launched", "migrated",
        "engineered", "architected", "analyzed", "trained", "generated", "processed"
    }
    words = [w.strip(".,;:()") for w in text.split()]
    tech_count = sum(1 for w in words if w.lower() in tech_words)
    has_action = any(w.lower() in action_verbs for w in words)
    # If mostly tech words and no action verb → not quantifiable
    if tech_count / max(len(words), 1) > 0.4 and not has_action:
        return False
    return True


def get_flags_and_questions(resume_json: dict, jd: str = None) -> list:
    """
    Flags bullets lacking metrics and generates clarifying questions.
    Only flags bullets where a number would genuinely make sense.
    """
    changes = []
    sections = ["experience", "projects"]

    for section in sections:
        items = resume_json.get(section) or []
        for i, item in enumerate(items):
            bullets = _get_bullets(item, section)
            field = _bullet_field(item, section)
            for j, bullet in enumerate(bullets):
                if not _has_metric(bullet) and _is_quantifiable(bullet):
                    changes.append({
                        "section": section,
                        "item_index": i,
                        "bullet_index": j,
                        "field": field,
                        "original": bullet,
                        "proposed": "Can you provide a specific number or percentage for this achievement? (e.g. how many users, how much improvement, how many hours saved)",
                        "reason": "Bullet lacks quantifiable impact metrics.",
                        "type": "question"
                    })
    return changes


def apply_fix_with_answer(original_bullet: str, user_answer: str) -> str:
    """
    Called in a separate step after the user provides a number.
    Rewrites the bullet inserting ONLY the confirmed number.
    """
    client = LLMClient("bullet_rewriter")

    system_prompt = (
        f"You are a strict text editor. Insert ONLY the following user-confirmed number into this bullet, "
        f"do not add any other number or claim: '{user_answer}'. Do not change any other part of the bullet's meaning. "
        f"Keep the same sentence structure as much as possible."
    )

    user_prompt = (
        f"Original sentence:\n{original_bullet}\n\n"
        "Return ONLY the rewritten sentence. No markdown, no explanations."
    )

    try:
        proposed = client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=False
        ).strip().strip('"\'')
        return proposed
    except Exception:
        return original_bullet
