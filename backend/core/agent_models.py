"""Current Groq model routing. Credentials are assigned separately by task group."""

FAST_MODEL = "openai/gpt-oss-20b"
TEXT_MODEL = FAST_MODEL
VISION_MODEL = "qwen/qwen3.8-27b"
REPAIR_MODEL = "qwen/qwen3.8-27b"

AGENT_MODELS = {
    "resume_parser": ("groq", TEXT_MODEL),
    "resume_vision_parser": ("groq", VISION_MODEL),
    "image_analysis": ("groq", VISION_MODEL),
    "chat_rag": ("groq", TEXT_MODEL),
    "resume_builder": ("groq", TEXT_MODEL),
    "jd_skill_extractor": ("groq", TEXT_MODEL),
    "latex_repair": ("groq", REPAIR_MODEL),
    "jd_extractor": ("groq", TEXT_MODEL),
    "summary_generator": ("groq", TEXT_MODEL),
    "ats_analyzer": ("groq", TEXT_MODEL),
    "resume_tailor": ("groq", TEXT_MODEL),  # Standalone ATS improver, not LaTeX mutation.
    "bullet_rewriter": ("groq", TEXT_MODEL),
    "chat_rerank": ("groq", FAST_MODEL),
    "intent_classifier": ("groq", FAST_MODEL),
    "push_intent": ("groq", FAST_MODEL),
    "sanity_checker": ("groq", FAST_MODEL),
    "job_match_reason": ("groq", FAST_MODEL),
    "readiness_judge": ("groq", FAST_MODEL),
    "trajectory_judge": ("groq", FAST_MODEL),
    "coverage_diff": ("groq", TEXT_MODEL),
    "coverage_diff_fallback": ("groq", TEXT_MODEL),
    "skill_classifier": ("groq", FAST_MODEL),
}

# Output caps include reasoning tokens. Large structured resumes and complete
# LaTeX repairs retain room for full documents; routine answers stay concise.
AGENT_MAX_TOKENS = {
    "resume_parser": 8192,
    "resume_vision_parser": 8192,
    "image_analysis": 8192,
    "chat_rag": 1024,
    "resume_builder": 8192,
    "jd_skill_extractor": 2048,
    "latex_repair": 8192,
    "jd_extractor": 4096,
    "summary_generator": 1024,
    "ats_analyzer": 4096,
    "resume_tailor": 4096,
    "bullet_rewriter": 1024,
    "chat_rerank": 512,
    "intent_classifier": 256,
    "push_intent": 256,
    "sanity_checker": 512,
    "job_match_reason": 512,
    "readiness_judge": 512,
    "trajectory_judge": 512,
    "coverage_diff": 2048,
    "coverage_diff_fallback": 2048,
    "skill_classifier": 512,
}
