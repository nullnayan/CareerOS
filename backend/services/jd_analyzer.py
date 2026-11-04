"""
Single source of truth for JD analysis.
All modules that need JD keywords should call this instead of
extracting keywords independently.
"""
from agents.llm_client import LLMClient
from services.analysis_cache import analysis_cache
import json, logging

logger = logging.getLogger(__name__)

def analyze_jd(jd_text: str, resume_json: dict = None) -> dict:
    """
    Canonical JD analysis. Returns:
    {
        "required_hard_skills": [...],
        "required_soft_skills": [...],
        "jd_keywords": [...],
        "responsibilities": [...],
        "seniority_level": str,
        "raw_jd_text": jd_text,
    }
    """
    if not jd_text or not jd_text.strip():
        return {
            "required_hard_skills": [],
            "required_soft_skills": [],
            "jd_keywords": [],
            "responsibilities": [],
            "seniority_level": "mid",
            "raw_jd_text": "",
        }

    resume_text = json.dumps(resume_json)[:2000] if resume_json else ""
    
    cached = analysis_cache.get(resume_text, jd_text)
    if cached:
        return cached
    
    client = LLMClient("resume_tailor")
    system_prompt = (
        "You are an expert ATS analyst. Extract structured data from this job description.\n"
        "Return a JSON object with these exact keys:\n"
        "- required_hard_skills: list of technical skills/tools mentioned\n"
        "- required_soft_skills: list of soft skills mentioned\n"
        "- jd_keywords: list of important domain keywords\n"
        "- responsibilities: list of key job responsibilities\n"
        "- seniority_level: 'entry'|'mid'|'senior'|'lead'|'executive'\n"
    )
    
    try:
        response = client.generate(system_prompt, jd_text, json_mode=True)
        result = json.loads(response)
        result["raw_jd_text"] = jd_text
        analysis_cache.set(resume_text, jd_text, result)
        return result
    except Exception as e:
        logger.error(f"JD analysis failed: {e}")
        # Rule-based fallback if LLM fails
        from services.ats_wordlists import HARD_SKILLS, SOFT_SKILLS
        jd_lower = jd_text.lower()
        found_hard = [hs for hs in HARD_SKILLS if hs.lower() in jd_lower]
        found_soft = [ss for ss in SOFT_SKILLS if ss in jd_lower]
        fallback = {
            "required_hard_skills": found_hard,
            "required_soft_skills": found_soft,
            "jd_keywords": found_hard + found_soft,
            "responsibilities": [],
            "seniority_level": "mid",
            "raw_jd_text": jd_text,
        }
        return fallback
