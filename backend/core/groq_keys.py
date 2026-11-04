"""Task primaries and optional backups with independently assigned org quotas."""
import os
import hashlib
import json
from pathlib import Path

KEY_GROUPS = ("parsing", "chat", "tailoring", "ats", "classification")
ROUTING_POLICY_FILE = Path(__file__).resolve().parents[1] / "data" / "groq-routing.json"
TASK_GROUPS = {
    "resume_parser": "parsing", "resume_vision_parser": "parsing", "image_analysis": "parsing",
    "chat_rag": "chat", "chat_rerank": "chat", "resume_builder": "chat",
    "jd_skill_extractor": "tailoring", "summary_generator": "tailoring", "jd_extractor": "tailoring",
    "latex_repair": "tailoring",
    "resume_tailor": "ats", "ats_analyzer": "ats", "bullet_rewriter": "ats",
    "readiness_judge": "ats", "trajectory_judge": "ats",
    "coverage_diff": "classification", "coverage_diff_fallback": "classification",
    "skill_classifier": "classification", "sanity_checker": "classification",
    "intent_classifier": "classification", "push_intent": "classification", "job_match_reason": "classification",
}


def independent_organizations() -> bool:
    override = os.getenv("GROQ_KEYS_INDEPENDENT_ORGANIZATIONS")
    if override is not None: return override.lower() in {"1", "true", "yes"}
    try:
        policy = json.loads(ROUTING_POLICY_FILE.read_text(encoding="utf-8"))
        return isinstance(policy, dict) and policy.get("independent_organizations") is True
    except (OSError, ValueError):
        return False


def key_candidates_for_task(task: str) -> list[tuple[str, str, str]]:
    """Fallback is enabled only for explicitly confirmed independent org quotas."""
    if not independent_organizations():
        key, variable = key_for_task(task)
        return [(key, variable, "shared-organization")]
    group = TASK_GROUPS.get(task, "classification")
    index = KEY_GROUPS.index(group)
    groups = KEY_GROUPS[index:] + KEY_GROUPS[:index]
    result, seen = [], set()
    for assigned in groups:
        variable = "GROQ_API_KEY_" + assigned.upper()
        key = os.getenv(variable)
        if assigned == group and not key:
            key, variable = os.getenv("GROQ_API_KEY"), "GROQ_API_KEY"
        if not key: continue
        fingerprint = hashlib.sha256(key.encode()).hexdigest()
        if fingerprint in seen: continue
        seen.add(fingerprint)
        result.append((key, variable, fingerprint))
    if not result: key_for_task(task)  # Reuse the clear missing-credential error.
    return result


def key_for_task(task: str) -> tuple[str, str]:
    group = TASK_GROUPS.get(task, "classification")
    variable = "GROQ_API_KEY_" + group.upper()
    key = os.getenv(variable) or os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError(f"No Groq credential configured for {group}. Set {variable} on the backend.")
    return key, variable


def routing_status() -> list[dict]:
    backups = independent_organizations()
    def available_backups(group):
        index = KEY_GROUPS.index(group)
        order = KEY_GROUPS[index + 1:] + KEY_GROUPS[:index]
        seen = {os.getenv("GROQ_API_KEY_" + group.upper()) or os.getenv("GROQ_API_KEY")}
        result = []
        for other in order:
            variable = "GROQ_API_KEY_" + other.upper()
            key = os.getenv(variable)
            if key and key not in seen:
                result.append(variable); seen.add(key)
        return result
    return [{"group": group, "variable": "GROQ_API_KEY_" + group.upper(),
             "configured": bool(os.getenv("GROQ_API_KEY_" + group.upper()) or os.getenv("GROQ_API_KEY")),
             "independent_organization_backups": backups,
             "backup_variables": available_backups(group) if backups else [],
             "tasks": sorted(task for task, assigned in TASK_GROUPS.items() if assigned == group)}
            for group in KEY_GROUPS]
