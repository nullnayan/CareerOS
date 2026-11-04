import json
import logging
from agents.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ─── Conservative Mode ─────────────────────────────────────────────────────────
# Non-destructive micro-improvements only. Never adds/removes sections or
# changes the resume structure. Uses ATS analysis results to target fixes.
CONSERVATIVE_SYSTEM_PROMPT = """You are an expert resume editor specializing in ATS optimization.
You will receive:
1. A candidate's resume in JSON format.
2. An ATS ANALYSIS REPORT containing the exact scores, issues, and points lost.

YOUR TASK: Fix the issues identified in the ATS report using ONLY non-destructive edits.

RULES YOU MUST FOLLOW:
1. DO NOT add any new sections (no new "summary", "objective", "certifications", "volunteer" sections).
2. DO NOT remove any existing sections or entries.
3. DO NOT move projects into the experience section or vice versa.
4. DO NOT invent, fabricate, or add placeholder URLs, links, locations, or credentials.
5. DO NOT change the candidate's name, email, phone, or contact details.
6. DO NOT add skills that are not already mentioned anywhere in the resume.
7. PRESERVE the exact same JSON structure and keys.
8. CRITICAL COUNT-MATCHING RULE: The number of bullets per project, number of education entries, and number of certifications in your output MUST exactly match the input. If the input has 3 bullets for a project, your output must also have 3 — you may reword them, but never omit one.

WHAT YOU SHOULD DO (prioritize by points deducted in the ATS report):
- If ATS flagged "bullet points lack action verbs": Rewrite those bullets to start with strong action verbs (Developed, Engineered, Optimized, Designed, Spearheaded, Implemented).
- If ATS flagged "bullets lack quantifiable metrics": Add realistic quantification (e.g., "Improved load time" → "Improved load time by 40%", "Built a web app" → "Built a full-stack web app serving 500+ users").
- If ATS flagged "weak phrasing" or "cliche/buzzword": Replace those exact phrases with specific achievements.
- If ATS flagged "filler words" or "first-person pronouns": Remove them.
- If ATS flagged "repetitive bullet opener": Vary the starting verbs across bullets.
- If ATS flagged "low-substance comma list bullets": Expand those into proper achievement-oriented sentences.
- Fix grammar, spelling, and punctuation errors.
- Convert passive voice to active voice.
- Make bullet points concise (aim for 1-2 lines each).
- Ensure consistent tense (past tense for completed work, present for current roles).

PRIORITIZATION: Focus your changes on the issues with the HIGHEST points_deducted first.

Output ONLY the revised resume JSON. No explanations, no markdown fences, no commentary."""


# ─── Directed Mode ──────────────────────────────────────────────────────────────
# Follows the user's explicit instructions for structural or content changes.
# Also uses ATS analysis to provide context.
DIRECTED_SYSTEM_PROMPT = """You are an expert resume editor and career coach.
You will receive:
1. A candidate's resume in JSON format.
2. Specific instructions from the candidate about what changes they want.
3. An ATS ANALYSIS REPORT showing current scores and issues.

YOUR TASK: Execute the candidate's instructions precisely, while also fixing high-priority ATS issues.

RULES:
1. Follow the user's instructions exactly. If they ask to add a professional summary, add one. If they ask to restructure experience, do it.
2. After executing the user's instructions, also fix any high-severity ATS issues (action verbs, metrics, weak phrasing, filler words) that don't conflict with the user's instructions.
3. Do NOT fabricate fake companies, degrees, or credentials that the candidate hasn't mentioned.
4. When adding new content (like a summary), base it on the existing resume content — skills, projects, and experience already listed.
5. Keep the same JSON schema structure.
6. If the user asks for something impossible or contradictory, do your best interpretation.

Output ONLY the revised resume JSON. No explanations, no markdown fences, no commentary."""


def _format_ats_context(ats_result: dict) -> str:
    """Format ATS analysis results into a readable context block for the LLM."""
    parts = []

    # Overall score
    score = ats_result.get("baseline_score") or ats_result.get("match_score", "N/A")
    parts.append(f"CURRENT ATS SCORE: {score}/100")

    # Score breakdown
    breakdown = ats_result.get("score_breakdown", {})
    if breakdown:
        parts.append("\nSCORE BREAKDOWN:")
        for category, value in breakdown.items():
            label = category.replace("_", " ").title()
            parts.append(f"  - {label}: {value}/100")

    # Issues sorted by severity and points deducted
    issues = ats_result.get("issues", [])
    if issues:
        high_issues = [i for i in issues if i.get("severity") == "high"]
        med_issues = [i for i in issues if i.get("severity") == "medium"]
        low_issues = [i for i in issues if i.get("severity") == "low"]

        parts.append(f"\nISSUES FOUND ({len(issues)} total, {len(high_issues)} high priority):")
        for i, issue in enumerate(high_issues + med_issues + low_issues):
            pts = issue.get("points_deducted", 0)
            sev = issue.get("severity", "?").upper()
            parts.append(f"  [{sev}] (-{pts}pts) {issue.get('issue', '')}")
            if issue.get("suggestion"):
                parts.append(f"         Fix: {issue['suggestion']}")

    # Missing keywords
    missing_kws = ats_result.get("missing_keywords", [])
    if missing_kws:
        parts.append(f"\nMISSING KEYWORDS: {', '.join(missing_kws[:15])}")

    # Premium stats
    pb = ats_result.get("premium_breakdown", {})
    if pb:
        parts.append(f"\nSTATS: {pb.get('hard_skills_found', 0)} hard skills, "
                     f"{pb.get('soft_skills_found', 0)} soft skills, "
                     f"{pb.get('estimated_word_count', 0)} words, "
                     f"{pb.get('years_experience', 0)} years experience")

    return "\n".join(parts)


def improve_resume_conservative(resume_json: dict, job_description: str = None, ats_result: dict = None) -> dict:
    """
    Apply non-destructive micro-improvements guided by ATS analysis results.
    Prioritizes fixing issues that cost the most points.
    """
    client = LLMClient(agent_name="resume_tailor")

    user_parts = [f"Original Resume JSON:\n{json.dumps(resume_json, indent=2)}"]

    # Inject ATS analysis context
    if ats_result:
        ats_context = _format_ats_context(ats_result)
        user_parts.append(f"\n--- ATS ANALYSIS REPORT ---\n{ats_context}")

    if job_description and job_description.strip():
        user_parts.append(
            f"\nOptional context — the candidate is targeting this role:\n{job_description[:1500]}\n"
            "Use this context to prioritize which bullet points to strengthen, "
            "but do NOT add new skills or sections."
        )
    user_parts.append("\nReturn the improved version as clean JSON.")
    user_prompt = "\n".join(user_parts)

    response = client.generate(
        system_prompt=CONSERVATIVE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        json_mode=True,
    )
    return _parse_json_response(response)


def improve_resume_directed(resume_json: dict, user_instructions: str, job_description: str = None, ats_result: dict = None) -> dict:
    """
    Apply structural or content changes guided by the user's explicit instructions,
    while also fixing high-priority ATS issues.
    """
    client = LLMClient(agent_name="resume_tailor")

    user_parts = [f"Original Resume JSON:\n{json.dumps(resume_json, indent=2)}"]

    # Inject ATS analysis context
    if ats_result:
        ats_context = _format_ats_context(ats_result)
        user_parts.append(f"\n--- ATS ANALYSIS REPORT ---\n{ats_context}")

    user_parts.append(f"\n--- USER INSTRUCTIONS ---\n{user_instructions}")
    if job_description and job_description.strip():
        user_parts.append(f"\n--- TARGET JOB DESCRIPTION ---\n{job_description[:1500]}")
    user_parts.append("\nReturn the improved version as clean JSON.")
    user_prompt = "\n".join(user_parts)

    response = client.generate(
        system_prompt=DIRECTED_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        json_mode=True,
    )
    return _parse_json_response(response)


# Keep the old function as a backwards-compatible alias
def improve_resume_baseline(resume_json: dict) -> dict:
    """Legacy wrapper — delegates to conservative mode."""
    return improve_resume_conservative(resume_json)


def _parse_json_response(response: str) -> dict:
    """Parse JSON from the LLM response, handling markdown fences."""
    try:
        return json.loads(response)
    except Exception as e:
        logger.warning(f"Direct JSON parse failed: {e}. Attempting cleanup...")
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
            try:
                return json.loads(cleaned)
            except Exception:
                pass
        raise ValueError(f"Failed to parse LLM response as JSON: {response[:300]}")
