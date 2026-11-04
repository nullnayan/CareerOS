import json
import logging
from agents.llm_client import LLMClient

logger = logging.getLogger(__name__)

def score_recruiter_readiness(resume_text: str) -> float:
    """
    Evaluates if the resume reads like a strong candidate.
    Returns a score between 0.0 and 1.0.
    """
    client = LLMClient("readiness_judge")
    
    system_prompt = (
        "You are an expert technical recruiter and hiring manager.\n"
        "Evaluate the following resume text for 'Recruiter Readiness'.\n"
        "Does this candidate sound impactful, clear, and professional? Are the descriptions "
        "substantive (metric-driven, action-oriented) rather than just a list of keywords?\n\n"
        "Respond with a JSON object containing exactly two keys:\n"
        "- 'reasoning': a brief 1-2 sentence explanation of your judgment.\n"
        "- 'score': a float between 0.0 (terrible, unprofessional) and 1.0 (outstanding, highly compelling).\n"
    )
    
    try:
        response_text = client.generate(system_prompt, resume_text, json_mode=True)
        data = json.loads(response_text)
        score = float(data.get("score", 0.5))
        return min(max(score, 0.0), 1.0)
    except Exception as e:
        logger.error(f"Readiness judge failed: {e}")
        return 0.5

def score_trajectory_alignment(resume_text: str, jd_text: str) -> float:
    """
    Evaluates if the candidate's career trajectory aligns with the target role.
    Returns a score between 0.0 and 1.0.
    """
    if not jd_text or not jd_text.strip():
        return 1.0
        
    client = LLMClient("trajectory_judge")
    
    system_prompt = (
        "You are an expert technical recruiter and hiring manager.\n"
        "Evaluate the alignment between the candidate's career trajectory (resume) "
        "and the target role (job description).\n"
        "Does their experience genuinely demonstrate they can do this job, beyond just "
        "matching buzzwords? (e.g. if the JD needs a Lead Engineer, have they shown leadership?)\n\n"
        "Respond with a JSON object containing exactly two keys:\n"
        "- 'reasoning': a brief 1-2 sentence explanation of your judgment.\n"
        "- 'score': a float between 0.0 (completely irrelevant) and 1.0 (perfectly aligned).\n"
    )
    
    user_prompt = f"--- JOB DESCRIPTION ---\n{jd_text}\n\n--- RESUME ---\n{resume_text}"
    
    try:
        response_text = client.generate(system_prompt, user_prompt, json_mode=True)
        data = json.loads(response_text)
        score = float(data.get("score", 0.5))
        return min(max(score, 0.0), 1.0)
    except Exception as e:
        logger.error(f"Trajectory judge failed: {e}")
        return 0.5
