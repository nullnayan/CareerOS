"""
ATS Analyzer agent.

Job: compare a parsed resume against a job description, and produce:
- a match score
- specific missing keywords
- concrete bullet-point rewrite suggestions

Like the Resume Parser, this file does ONE job and nothing else — it
doesn't touch the database or create Suggestion rows. That happens in
api/ats.py, which calls this agent and then decides what to do with
the result.
"""

import json
from agents.llm_client import LLMClient

SYSTEM_PROMPT = """You are an ATS (Applicant Tracking System) analysis assistant. You will be given a candidate's resume data (as JSON) and a job description (as plain text).

Compare them and return ONLY valid JSON in this EXACT shape, nothing else — no markdown fences, no explanation text:

{
  "match_score": 0-100 integer,
  "missing_keywords": ["list of important terms from the job description NOT found in the resume"],
  "matched_keywords": ["list of important terms found in BOTH"],
  "bullet_rewrites": [
    {
      "original": "the exact original bullet point from the resume's experience section",
      "suggested": "an improved version that better matches the job description's language",
      "reason": "one short sentence explaining why this rewrite helps"
    }
  ]
}

Rules:
- match_score should reflect genuine overlap between the resume's actual content and the job description's key requirements, not just enthusiasm.
- Only suggest bullet rewrites for bullets that genuinely exist in the resume's experience section — never invent achievements the person didn't list.
- Limit bullet_rewrites to the 3-5 most impactful suggestions, not every bullet."""


def analyze_ats(resume_structured_json: dict, job_description: str) -> dict:
    """
    resume_structured_json: the dict already saved in resume_versions.structured_json
    job_description: plain text the user pasted in
    Returns: a dict matching the schema above.
    """
    client = LLMClient(agent_name="ats_analyzer")

    user_prompt = (
        f"RESUME DATA:\n{json.dumps(resume_structured_json, indent=2)}\n\n"
        f"JOB DESCRIPTION:\n{job_description}"
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
            f"ATS Analyzer didn't return valid JSON. "
            f"Raw response was: {response_text[:500]}"
        ) from e
