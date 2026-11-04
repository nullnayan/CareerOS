"""
ATS Baseline Analyzer agent.

Job: evaluate a resume's general ATS friendliness WITHOUT a specific job description.
Checks for:
- Formatting issues (weird fonts, tables, graphics)
- Section completeness (contact info, summary, work experience, education, skills)
- Keyword density and variation
- Common ATS-killer patterns
- Overall readability

Returns a baseline score (0-100) + specific, actionable issues the user should fix.
Unlike the targeted analyzer, this doesn't compare against a job description.
"""

import json
from agents.llm_client import LLMClient

SYSTEM_PROMPT = """You are an ATS (Applicant Tracking System) baseline analyzer. You evaluate a candidate's resume for general ATS friendliness — NOT against a specific job description, but against best practices that most ATS systems follow.

Given a candidate's resume data (as JSON), identify and score:
1. Format & Structure: Does it use problematic elements (tables, graphics, unusual fonts)?
2. Section Completeness: Does it have all key sections? (contact, summary, experience, education, skills). Note: A summary section is optional, especially for entry-level or student resumes; do not heavily penalize its absence if other sections are solid.
3. Work Experience / Projects: For students or entry-level candidates, treat internships, academic projects, or freelance work as valid experience sections. Do not penalize them for lacking full-time corporate experience.
4. Keyword Density & Clarity: Are there enough concrete skills/technologies listed?
5. Common ATS Traps: Missing dates? Unclear formatting? Skills hidden in descriptions?

Return ONLY valid JSON in this EXACT shape, nothing else:

{
  "baseline_score": 0-100 integer,
  "score_breakdown": {
    "format_and_structure": 0-100,
    "section_completeness": 0-100,
    "keyword_clarity": 0-100,
    "ats_compatibility": 0-100
  },
  "issues": [
    {
      "category": "format" | "completeness" | "keywords" | "compatibility",
      "severity": "high" | "medium" | "low",
      "issue": "brief description of the problem",
      "suggestion": "actionable fix (not a rewrite, just guidance)"
    }
  ],
  "summary": "1-2 sentences summarizing the resume's ATS readiness"
}

Rules:
- baseline_score is the average of all subscores, representing overall ATS friendliness.
- Limit issues to 5-7 most impactful items. Prioritize HIGH severity.
- Suggestions should be specific but not rewrite entire sections — just point to the issue.
- Be realistic: don't fail someone for minor formatting; focus on what ATS systems actually struggle with.
- If the candidate is a student (indicated by education dates or lack of full-time jobs), evaluate their 'Projects' or 'Internships' as their experience section so their score reflects their readiness relative to entry-level roles."""


def analyze_ats_baseline(resume_structured_json: dict) -> dict:
    """
    resume_structured_json: the dict already saved in resume_versions.structured_json
    Returns: a dict matching the schema above.
    """
    client = LLMClient(agent_name="ats_analyzer")  # reuse ats_analyzer model config

    user_prompt = (
        f"RESUME DATA:\n{json.dumps(resume_structured_json, indent=2)}\n\n"
        f"Analyze this resume for general ATS compatibility (no specific job description)."
    )

    response_text = client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        json_mode=True,
    )

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"ATS Baseline Analyzer didn't return valid JSON. "
            f"Raw response was: {response_text[:500]}"
        ) from e
