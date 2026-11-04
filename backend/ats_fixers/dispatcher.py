"""
dispatcher.py — Phase 7: Score-driven fixer routing with score-delta simulation.

Changes from old dispatcher:
1. Routes by finding_code (check_id) instead of running all 12 fixers blindly
2. Score-delta simulation: re-scores after each proposed fix to compute "+X pts"
3. Ranks suggestions by delta/effort not by severity
4. Initialises improved_ats={} before try-blocks (Bug 4 fix carried forward)
5. Every finding_code maps to exactly one fixer (or explicit no_auto_fix)
6. Coverage assertion: any unmapped finding code is logged as a warning
"""
import concurrent.futures
import logging
from typing import Optional

from ats_fixers.validation import validate_change
from ats_fixers import dates, education, unnecessary_sections, buzzwords, communication
from ats_fixers import quantify_impact, summary, length_depth, ats_keywords, readability
from ats_fixers import grammar, bullet_consistency

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Finding-code → fixer mapping (Phase 7 taxonomy)
# Every check_id that can produce a Finding must appear here or in NO_AUTO_FIX
# ──────────────────────────────────────────────────────────────────────────────
FINDING_TO_FIXER: dict[str, str] = {
    # IMPACT
    "quantified_bullets":       "quantify_impact",
    "action_verbs":             "grammar",        # tense/verb rewrite
    "weak_verbs":               "grammar",
    "verb_repetition":          "bullet_consistency",
    "achievement_vs_duty":      "quantify_impact",
    "metric_quality":           "quantify_impact",
    # BREVITY
    "resume_length":            "length_depth",
    "bullet_length":            "length_depth",
    "bullets_per_role":         "length_depth",
    "summary_length":           "summary",
    # STYLE
    "personal_pronouns":        "grammar",
    "punctuation_consistency":  "bullet_consistency",
    "filler_words":             "buzzwords",
    "buzzword_density":         "buzzwords",
    "passive_voice":            "grammar",
    "spelling":                 "grammar",
    "grammar_tense":            "grammar",
    # STRUCTURE
    "contact_completeness":     None,   # no_auto_fix — user must add contact
    "section_presence":         None,
    "summary_specificity":      "summary",
    "education_completeness":   "education",
    "skills_organisation":      None,
    "section_order":            None,
    "contact_in_header":        None,
    # FORMATTING (layout-based — no text fixer applies)
    "page_count":               None,
    "date_format_consistency":  "dates",
    "column_layout":            None,
    "tables_used":              None,
    "special_characters":       None,
    "bullet_glyph_consistency": "bullet_consistency",
    # AUTHENTICITY
    "duplicate_bullets":        "bullet_consistency",
    "keyword_stuffing":         None,
    "date_gaps":                None,
    "date_overlaps":            "dates",
    "unverifiable_superlatives": "buzzwords",
    # GROWTH
    "leadership":               "communication",
    "career_progression":       None,
    "tenure_pattern":           None,
    "increasing_scope":         "communication",
    # MATCH
    "keyword_match":            "ats_keywords",
    "hard_skills_coverage":     "ats_keywords",
    "title_match":              "summary",
    "seniority_fit":            "summary",
}

FIXER_REGISTRY = {
    "grammar":              grammar.fix,
    "bullet_consistency":   bullet_consistency.fix,
    "quantify_impact":      quantify_impact.get_flags_and_questions,
    "summary":              summary.fix,
    "length_depth":         length_depth.get_flags,
    "communication":        communication.fix,
    "education":            education.get_flags,
    "buzzwords":            buzzwords.fix,
    "dates":                dates.fix,
    "unnecessary_sections": unnecessary_sections.get_flags,
    "ats_keywords":         ats_keywords.get_flags_and_questions,
    "readability":          readability.fix,
}

AUTO_IMPROVE_SAFE = [
    "grammar", "bullet_consistency", "communication", "buzzwords",
    "dates", "summary", "quantify_impact", "length_depth",
    "education", "unnecessary_sections", "ats_keywords", "readability",
]


def _run_single_fixer(category: str, resume_json: dict, jd: Optional[str]) -> tuple[str, list]:
    fixer_fn = FIXER_REGISTRY.get(category)
    if not fixer_fn:
        return category, []
    try:
        if category == "ats_keywords":
            proposed = fixer_fn(resume_json, jd)
        else:
            proposed = fixer_fn(resume_json)
        validated = [c for c in proposed if validate_change(category, c, resume_json)]
        return category, validated
    except Exception as e:
        logger.error(f"Fixer '{category}' failed: {e}")
        return category, []


def _simulate_score_delta(
    change: dict,
    resume_json: dict,
    current_score: float,
) -> float:
    """
    Applies a single proposed change to a copy of resume_json, re-scores,
    and returns the score delta. Returns 0.0 on any failure.
    """
    try:
        import copy
        from ats.api_adapter import run_v3_scoring_from_json
        test_json = copy.deepcopy(resume_json)

        sec = change.get("section", "")
        idx = change.get("item_index")
        b_idx = change.get("bullet_index")
        field = change.get("field", "bullet_points")
        proposed = change.get("proposed", "")

        if sec and idx is not None and b_idx is not None:
            entries = test_json.get(sec, [])
            if idx < len(entries):
                bullets = entries[idx].get(field, [])
                if b_idx < len(bullets):
                    bullets[b_idx] = proposed
                    entries[idx][field] = bullets
        elif sec and idx is not None and proposed:
            entries = test_json.get(sec, [])
            if idx < len(entries):
                entries[idx][field] = proposed

        result = run_v3_scoring_from_json(test_json)
        new_score = result.get("baseline_score", current_score)
        return round(new_score - current_score, 1)
    except Exception:
        return 0.0


def dispatch(
    ats_score: dict,
    resume_json: dict,
    mode: str,
    jd: Optional[str] = None,
    threshold: int = 8,
    custom_category: Optional[str] = None,
    compute_deltas: bool = False,
) -> dict:
    """
    Phase 7 dispatcher: routes findings to fixers, optionally computes score deltas.

    mode: "auto_improve" | "custom" | "finding_driven"
    finding_driven: uses issues list from ats_score to pick only relevant fixers
    compute_deltas: if True, simulate re-score for each change (slower)
    """
    # Determine which fixers to run
    if mode == "auto_improve":
        categories_to_run = list(AUTO_IMPROVE_SAFE)

    elif mode == "custom" and custom_category:
        categories_to_run = [custom_category]

    elif mode == "finding_driven":
        # Route by finding codes from the score report
        issues = ats_score.get("issues", [])
        fixer_set: set[str] = set()
        for issue in issues:
            check_id = issue.get("category") or issue.get("check_id", "")
            fixer = FINDING_TO_FIXER.get(check_id)
            if fixer:
                fixer_set.add(fixer)
            elif check_id not in FINDING_TO_FIXER:
                logger.warning(f"No fixer mapping for finding_code '{check_id}' — add to FINDING_TO_FIXER")
        categories_to_run = list(fixer_set)

    else:
        categories_to_run = list(FIXER_REGISTRY.keys())

    # Run fixers in parallel
    results: dict[str, list] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(categories_to_run) or 1, 8)) as executor:
        futures = {
            executor.submit(_run_single_fixer, cat, resume_json, jd): cat
            for cat in categories_to_run
        }
        for future in concurrent.futures.as_completed(futures):
            category, validated_changes = future.result()
            if mode == "auto_improve":
                validated_changes = [c for c in validated_changes if c.get("type") != "question"]
            if validated_changes:
                results[category] = validated_changes

    # Score-delta simulation (Phase 7 — compute "+X pts" per suggestion)
    if compute_deltas:
        current_score = ats_score.get("baseline_score") or ats_score.get("match_score") or 0.0
        all_changes_flat = []
        for cat, changes in results.items():
            for change in changes:
                delta = _simulate_score_delta(change, resume_json, current_score)
                change["score_delta"] = delta
                change["fixer_category"] = cat
                all_changes_flat.append(change)

        # Sort by delta descending (highest impact first)
        all_changes_flat.sort(key=lambda c: c.get("score_delta", 0), reverse=True)
        return {"changes": all_changes_flat, "by_category": results}

    return results
