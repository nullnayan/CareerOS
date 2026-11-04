from dataclasses import dataclass
from typing import Mapping
from ..models import Seniority, Dimension

@dataclass(frozen=True)
class Rubric:
    band: Seniority
    # thresholds
    metric_bullet_target: float
    action_verb_target: float
    max_pages: int
    min_words: int
    max_words: int
    max_bullets_per_role: int
    leadership_expectation: float
    # expectations
    expects_summary: bool
    expects_formal_experience: bool
    expects_gpa: bool
    counts_projects_as_experience: bool
    # weights
    dimension_weights: Mapping[Dimension, float]
    disabled_checks: frozenset[str]

# Baseline weights when NO JD is provided
BASELINE_WEIGHTS: Mapping[Dimension, float] = {
    "IMPACT":       0.26,
    "BREVITY":      0.14,
    "STYLE":        0.10,
    "STRUCTURE":    0.14,
    "FORMATTING":   0.16,
    "AUTHENTICITY": 0.10,
    "GROWTH":       0.10,
}

# Match weights when JD is provided (applied to MATCH score only)
MATCH_WEIGHTS = {
    "hard_skills":   0.50,
    "job_title":     0.15,
    "domain_terms":  0.12,
    "seniority_fit": 0.10,
    "soft_skills":   0.07,
    "education":     0.04,
    "certifications":0.02,
}

# Dimension weights by band (each sums to 1.0)
BAND_DIMENSION_WEIGHTS = {
    "student": {
        "IMPACT": 0.18, "BREVITY": 0.12, "STYLE": 0.10, "STRUCTURE": 0.22, 
        "FORMATTING": 0.18, "AUTHENTICITY": 0.10, "GROWTH": 0.10
    },
    "entry": {
        "IMPACT": 0.24, "BREVITY": 0.13, "STYLE": 0.10, "STRUCTURE": 0.18, 
        "FORMATTING": 0.17, "AUTHENTICITY": 0.10, "GROWTH": 0.08
    },
    "mid": {
        "IMPACT": 0.28, "BREVITY": 0.14, "STYLE": 0.10, "STRUCTURE": 0.14, 
        "FORMATTING": 0.16, "AUTHENTICITY": 0.10, "GROWTH": 0.08
    },
    "senior": {
        "IMPACT": 0.30, "BREVITY": 0.15, "STYLE": 0.09, "STRUCTURE": 0.12, 
        "FORMATTING": 0.15, "AUTHENTICITY": 0.09, "GROWTH": 0.10
    },
    "exec": {
        "IMPACT": 0.30, "BREVITY": 0.15, "STYLE": 0.08, "STRUCTURE": 0.11, 
        "FORMATTING": 0.14, "AUTHENTICITY": 0.08, "GROWTH": 0.14
    }
}

DISABLED_CHECKS_BY_BAND = {
  "student": frozenset({"structure.formal_experience_section", "impact.scope_signals",
              "growth.people_management", "structure.career_progression",
              "authenticity.employment_gaps", "brevity.summary_required"}),
  "entry":   frozenset({"growth.people_management", "structure.career_progression"}),
  "mid":     frozenset(),
  "senior":  frozenset({"structure.gpa_present"}),
  "exec":    frozenset({"structure.gpa_present", "impact.individual_contributor_depth"}),
}

def get_rubric(band: Seniority) -> Rubric:
    # Build a complete matrix of thresholds from the spec
    thresholds = {
        "student": (0.20, 0.75, 1, 250, 600, 5, 0.15, False, False, True, True),
        "entry":   (0.35, 0.85, 1, 300, 700, 6, 0.30, False, True, False, False), # partial for projects not fully handled here
        "mid":     (0.45, 0.90, 1, 400, 850, 6, 0.45, True, True, False, False),
        "senior":  (0.55, 0.90, 2, 500, 1100, 7, 0.65, True, True, False, False),
        "exec":    (0.60, 0.90, 2, 550, 1200, 8, 0.80, True, True, False, False),
    }
    
    t = thresholds[band]
    return Rubric(
        band=band,
        metric_bullet_target=t[0],
        action_verb_target=t[1],
        max_pages=t[2],
        min_words=t[3],
        max_words=t[4],
        max_bullets_per_role=t[5],
        leadership_expectation=t[6],
        expects_summary=t[7],
        expects_formal_experience=t[8],
        expects_gpa=t[9],
        counts_projects_as_experience=t[10],
        dimension_weights=BAND_DIMENSION_WEIGHTS[band],
        disabled_checks=DISABLED_CHECKS_BY_BAND[band]
    )
