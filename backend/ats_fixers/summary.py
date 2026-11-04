from agents.llm_client import LLMClient


def _extract_facts(resume_json: dict) -> str:
    """Extract all skills and project/experience highlights into a flat list of facts."""
    facts = []

    # Skills (supports both list-of-strings and list-of-category-dicts)
    skills = resume_json.get("skills") or []
    if skills:
        if isinstance(skills[0], dict):
            for skill_cat in skills:
                cat = skill_cat.get("category", "")
                items = ", ".join(skill_cat.get("items", []))
                if items:
                    facts.append(f"Skills ({cat}): {items}")
        else:
            facts.append(f"Skills: {', '.join(str(s) for s in skills)}")

    # Experience titles
    for exp in resume_json.get("experience") or []:
        title = exp.get("title", "")
        company = exp.get("company", "")
        if title:
            facts.append(f"Role: {title}" + (f" at {company}" if company else ""))

    # Project technologies
    for proj in resume_json.get("projects") or []:
        name = proj.get("name", "")
        tech = proj.get("technologies") or []
        if tech:
            facts.append(f"Project '{name}' used: {', '.join(tech)}")

    # Education
    for edu in resume_json.get("education") or []:
        degree = edu.get("degree", "")
        field = edu.get("field", "")
        institution = edu.get("institution", "")
        if degree:
            facts.append(f"Education: {degree}" + (f" in {field}" if field else "") + (f" from {institution}" if institution else ""))

    return "\n".join(facts)


def fix(resume_json: dict) -> list:
    """
    If summary is missing or empty, generate one constrained strictly to existing facts.
    If summary is too long (> 50 words), condense it to under 40 words.
    Returns a change item with section='summary' and field='summary' (top-level string).
    """
    changes = []
    summary_text = (resume_json.get("summary") or "").strip()
    words = summary_text.split()

    if not summary_text:
        # ── Generate missing summary ──
        client = LLMClient("bullet_rewriter")
        facts = _extract_facts(resume_json)

        if not facts:
            return changes  # Nothing to base a summary on

        system_prompt = (
            "You are a strict text editor. Write a professional resume summary using ONLY the following facts. "
            "Every claim must be traceable to the provided facts list. "
            "Do not add any skill, achievement, or experience not in this list. "
            "Write a professional summary paragraph. Ensure it is at least 35 words long (occupying at least 2 to 3 lines in a standard document). "
            "If there is rich experience/skills to highlight, write a detailed summary (up to 4-5 lines, roughly 60-85 words). "
            "If there is very little content, write a concise summary (around 2 lines, ~30-40 words). "
            "Target around 3 lines of text. No fluff, no buzzwords."
        )

        user_prompt = (
            f"ALLOWED FACTS:\n{facts}\n\n"
            "Return ONLY the summary paragraph. No markdown, no explanations."
        )

        try:
            proposed = client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_mode=False
            ).strip().strip('"\'')

            if proposed:
                changes.append({
                    "section": "summary",
                    "item_index": -1,
                    "bullet_index": None,
                    "field": "summary",
                    "original": "",
                    "proposed": proposed,
                    "reason": "Added a professional summary based on your existing skills and experience.",
                    "type": "rewrite"
                })
        except Exception:
            pass

    elif len(words) > 90:
        # ── Condense overly long summary ──
        client = LLMClient("bullet_rewriter")
        system_prompt = (
            "You are a strict resume editor. Rewrite and condense the following summary to be professional and concise "
            "(aim for 3-4 lines, roughly 50-70 words). Do not condense it so much that it is less than 3 lines. "
            "Do not add any new facts. Preserve the core professional identity."
        )
        user_prompt = (
            f"Original Summary ({len(words)} words):\n{summary_text}\n\n"
            "Return ONLY the condensed summary. No explanations."
        )
        try:
            proposed = client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_mode=False
            ).strip().strip('"\'')
            if proposed and len(proposed.split()) < len(words):
                changes.append({
                    "section": "summary",
                    "item_index": -1,
                    "bullet_index": None,
                    "field": "summary",
                    "original": summary_text,
                    "proposed": proposed,
                    "reason": f"Condensed verbose summary from {len(words)} to {len(proposed.split())} words for optimal ATS readability.",
                    "type": "rewrite"
                })
        except Exception:
            pass

    return changes
