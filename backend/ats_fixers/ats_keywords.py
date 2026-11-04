"""
ats_keywords.py
Improved keyword alignment fixer.
Baseline mode: ensures standard tech skills present in the resume appear in Skills section correctly.
Job-specific mode: extracts required skills/tools from the JD, checks coverage in Skills + bullets,
and proposes adding missing ones to Skills (not hallucinating experience).
"""
import re
from agents.llm_client import LLMClient

# Common tech skills that should be in Skills section if mentioned anywhere in resume
COMMON_TECH_SKILLS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "kotlin", "swift",
    "react", "nextjs", "next.js", "nodejs", "node.js", "express", "vue", "angular",
    "html", "css", "tailwind", "bootstrap",
    "sql", "mysql", "postgresql", "mongodb", "redis", "sqlite",
    "aws", "gcp", "azure", "firebase", "docker", "kubernetes", "k8s",
    "git", "github", "gitlab", "ci/cd", "jenkins",
    "rest", "graphql", "api", "microservices",
    "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy", "opencv",
    "linux", "bash", "shell",
    "flask", "django", "fastapi", "spring",
}


def _extract_jd_keywords(jd: str) -> list[str]:
    """
    Extract tech skills and tools from a job description using centralized JDAnalyzer.
    Returns a list of lowercase skill keywords.
    """
    if not jd or not jd.strip():
        return []

    try:
        from services.jd_analyzer import analyze_jd
        analysis = analyze_jd(jd)
        kws = (analysis.get("required_hard_skills", []) +
               analysis.get("required_soft_skills", []) +
               analysis.get("jd_keywords", []))
        return list({k.strip().lower() for k in kws if k and isinstance(k, str)})[:20]
    except Exception:
        # Fallback: regex-based extraction
        words = re.findall(r'\b[A-Za-z][A-Za-z0-9#+\-.]{1,20}\b', jd)
        return list({w.lower() for w in words if w.lower() in COMMON_TECH_SKILLS})[:10]


def _get_resume_text(resume_json: dict) -> str:
    """Flatten all resume content into one searchable string."""
    return str(resume_json).lower()


def _skills_list(resume_json: dict) -> list[str]:
    """Get existing skills as a flat lowercase list."""
    skills = resume_json.get("skills", {})
    if isinstance(skills, list):
        return [str(s).lower() for s in skills]
    if isinstance(skills, dict):
        all_skills = []
        for v in skills.values():
            if isinstance(v, list):
                all_skills.extend([str(s).lower() for s in v])
            elif isinstance(v, str):
                all_skills.append(v.lower())
        return all_skills
    return []


def get_flags_and_questions(resume_json: dict, jd: str = None) -> list:
    """
    Baseline mode (no JD): checks that tech skills mentioned in bullets also appear in Skills section.
    Job-specific mode (JD given): checks coverage of JD keywords across Skills + bullets.
    Only returns 'question' type changes — no silent rewrites to skills.
    """
    changes = []
    resume_text = _get_resume_text(resume_json)
    skills_list = _skills_list(resume_json)

    if jd:
        # Job-specific: check JD keyword coverage
        jd_keywords = _extract_jd_keywords(jd)
        missing_from_skills = []
        missing_entirely = []

        for kw in jd_keywords:
            in_skills = any(kw in s for s in skills_list)
            in_resume = kw in resume_text
            if not in_skills and in_resume:
                # Skill is in resume text (bullets/projects) but not in Skills section
                missing_from_skills.append(kw)
            elif not in_resume:
                # Skill is entirely missing from resume
                missing_entirely.append(kw)

        # Propose adding skills from resume content to Skills section (safe — no new claims)
        for kw in missing_from_skills[:3]:
            changes.append({
                "section": "skills",
                "item_index": 0,
                "field": "add_keyword",
                "original": "",
                "proposed": kw,
                "reason": f"'{kw}' appears in your bullets but is not listed in your Skills section. Adding it improves ATS keyword coverage.",
                "type": "add_skill"
            })

        # Ask about entirely missing JD keywords
        for kw in missing_entirely[:2]:
            changes.append({
                "section": "skills",
                "item_index": 0,
                "field": "missing_keyword",
                "original": "",
                "proposed": f"The job description requires '{kw}'. Do you have any experience with this? If yes, describe how you used it and we will add it to a relevant bullet.",
                "reason": f"Missing ATS keyword from JD: '{kw}'",
                "type": "question"
            })
    else:
        # Baseline: check that tech skills mentioned in bullets are in Skills section
        bullet_text = ""
        for section in ["experience", "projects"]:
            for item in (resume_json.get(section) or []):
                for b in (item.get("bullet_points") or item.get("bullets") or []):
                    bullet_text += " " + b.lower()

        for skill in COMMON_TECH_SKILLS:
            if skill in bullet_text and not any(skill in s for s in skills_list):
                changes.append({
                    "section": "skills",
                    "item_index": 0,
                    "field": "add_keyword",
                    "original": "",
                    "proposed": skill,
                    "reason": f"'{skill}' appears in your project/experience bullets but is missing from your Skills section.",
                    "type": "add_skill"
                })

    return changes


def apply_fix_with_answer(resume_json: dict, user_answer: str, keyword: str) -> dict:
    """
    Called after user confirms they know the keyword and provides a sentence.
    Finds the most relevant bullet and rewrites it to include the keyword.
    """
    client = LLMClient("bullet_rewriter")
    # Find the most relevant bullet to insert keyword into
    best_bullet = None
    best_section = None
    best_item_idx = None
    best_bullet_idx = None
    best_field = None

    for section in ["experience", "projects"]:
        for i, item in enumerate(resume_json.get(section) or []):
            bullets = item.get("bullet_points") or item.get("bullets") or []
            field = "bullet_points" if "bullet_points" in item else "bullets"
            for j, b in enumerate(bullets):
                if not best_bullet:
                    best_bullet = b
                    best_section = section
                    best_item_idx = i
                    best_bullet_idx = j
                    best_field = field

    if not best_bullet:
        return {}

    try:
        proposed = client.generate(
            system_prompt=(
                f"You are a strict resume editor. Naturally incorporate the skill '{keyword}' "
                f"into this bullet based on the user's description: '{user_answer}'. "
                "Do not add any other new facts. Keep bullet under 20 words."
            ),
            user_prompt=f"Original bullet:\n{best_bullet}\n\nReturn ONLY the rewritten bullet.",
            json_mode=False
        ).strip().strip('"\'')
        return {
            "section": best_section,
            "item_index": best_item_idx,
            "bullet_index": best_bullet_idx,
            "field": best_field,
            "original": best_bullet,
            "proposed": proposed,
            "reason": f"Incorporated '{keyword}' based on your experience.",
            "type": "rewrite"
        }
    except Exception:
        return {}
