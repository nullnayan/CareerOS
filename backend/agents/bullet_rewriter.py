import json
import logging
from agents.llm_client import LLMClient

logger = logging.getLogger(__name__)

def rewrite_bullet(bullet_text: str, jd_text: str = None) -> dict:
    """
    Rewrites a weak bullet point into a strong, metric-driven action bullet.
    Returns a dict with {"suggested": "The rewritten bullet", "reasoning": "Why this is better"}
    """
    client = LLMClient("bullet_rewriter")
    
    system_prompt = (
        "You are an expert technical resume writer. Your job is to rewrite a single "
        "weak bullet point into a strong, impactful, ATS-friendly bullet point.\n\n"
        "Guidelines:\n"
        "1. Start with a strong action verb (e.g. Engineered, Spearheaded, Optimized).\n"
        "2. Include metrics or numbers if possible, or leave placeholders like [X]% if context suggests it.\n"
        "3. Focus on the impact and result, not just the task.\n"
        "4. Do NOT use first-person pronouns (I, me, my).\n"
    )
    if jd_text:
        system_prompt += "5. Align the language with the provided Job Description where relevant.\n"
        
    system_prompt += (
        "\nRespond with a JSON object containing exactly two keys:\n"
        "- 'suggested': The rewritten bullet point string.\n"
        "- 'reasoning': A brief explanation of why this rewrite is better.\n"
    )
    
    user_prompt = f"--- ORIGINAL BULLET ---\n{bullet_text}\n"
    if jd_text:
        user_prompt += f"\n--- JOB DESCRIPTION CONTEXT ---\n{jd_text}\n"
        
    try:
        response_text = client.generate(system_prompt, user_prompt, json_mode=True)
        data = json.loads(response_text)
        return {
            "suggested": data.get("suggested", bullet_text),
            "reasoning": data.get("reasoning", "Rewritten for better impact.")
        }
    except Exception as e:
        logger.error(f"Bullet rewriter failed: {e}")
        return {
            "suggested": bullet_text,
            "reasoning": "Failed to rewrite bullet."
        }
