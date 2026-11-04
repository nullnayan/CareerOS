from dataclasses import dataclass
from typing import Mapping, Any
from ..models import ResumeDoc, CheckResult, Finding
from ..checks.base import CHECK_REGISTRY, Check
from .rubric import get_rubric, Rubric, MATCH_WEIGHTS
from .ledger import PenaltyLedger
from .version import SCORING_VERSION
from .calibration import calibrate

@dataclass
class ScoreReport:
    version: str
    parseability: float
    strength: float
    match: float | None
    role_fit: float | None
    headline: float
    findings: tuple[Finding, ...]
    ledger_applied: tuple[Finding, ...]
    match_fallback: bool = False  # True when JD supplied but match could not be computed

def assign_points(dim: str, result: CheckResult, dim_weight: float, check_weight: float, score_basis: float) -> None:
    """
    Honest points algorithm: checks never assign points. The scorer derives them,
    and they sum exactly to the deduction.
    """
    if result.score is None:
        return
        
    lost = score_basis * dim_weight * check_weight * (1.0 - result.score)
    if not result.findings or lost <= 0:
        return
        
    sev_mass = {"critical": 5, "high": 3, "medium": 2, "low": 1, "info": 0}
    total = sum(sev_mass[f.severity] for f in result.findings) or 1
    
    for f in result.findings:
        f.points = round(lost * sev_mass[f.severity] / total, 1)

def _run_dimension_checks(
    doc: ResumeDoc, jd: Any, rubric: Rubric, dimension: str, checks: list[Check]
) -> tuple[float, list[Finding]]:
    """Runs checks for a single dimension and computes the dimension score."""
    results = []
    applicable_checks = []
    
    for check in checks:
        if check.id in rubric.disabled_checks:
            continue
        if doc.profile.seniority not in check.applies_to:
            continue
        if check.requires_jd and not jd:
            continue
            
        res = check.run(doc, jd, rubric)
        if res.score is not None:
            results.append(res)
            applicable_checks.append(check)
            
    if not results:
        return None, []  # No applicable checks → weight will be redistributed

    n = len(results)
    check_weight = 1.0 / n
    dim_score = sum(r.score for r in results) / n

    return dim_score, results

def score_resume(doc: ResumeDoc, jd: Any = None, is_archetype: bool = False) -> ScoreReport:
    rubric = get_rubric(doc.profile.seniority)
    
    # 1. Group checks by dimension
    dim_checks = {d: [] for d in rubric.dimension_weights.keys()}
    match_checks = []
    
    for check in CHECK_REGISTRY.values():
        if check.dimension == "MATCH":
            match_checks.append(check)
        elif check.dimension in dim_checks:
            dim_checks[check.dimension].append(check)
            
    # 2. Score Base Dimensions (Strength) with weight redistribution
    strength_basis = 100.0
    all_findings: list[Finding] = []

    # First pass: collect dimension scores
    dim_scores: dict[str, float | None] = {}
    dim_results_map: dict[str, list] = {}
    for dim, checks in dim_checks.items():
        dim_w = rubric.dimension_weights[dim]
        dim_s, results = _run_dimension_checks(doc, jd, rubric, dim, checks)
        dim_scores[dim] = dim_s
        dim_results_map[dim] = results

    # Redistribute weights: dimensions with None score (no applicable checks)
    # share their weight proportionally among the remaining dimensions
    active_dims = {d: w for d, w in rubric.dimension_weights.items() if dim_scores.get(d) is not None}
    inactive_weight = sum(w for d, w in rubric.dimension_weights.items() if dim_scores.get(d) is None)
    total_active_w = sum(active_dims.values()) or 1.0
    # Scale active weights so they absorb the inactive share
    scale = (total_active_w + inactive_weight) / total_active_w

    strength_score = 0.0
    for dim, dim_s in dim_scores.items():
        if dim_s is None:
            continue
        effective_w = rubric.dimension_weights[dim] * scale
        strength_score += dim_s * effective_w * strength_basis
        results = dim_results_map[dim]
        for res in results:
            assign_points(dim, res, effective_w, 1.0 / max(1, len(results)), strength_basis)
            all_findings.extend(res.findings)
    # 3. Penalty Ledger
    ledger = PenaltyLedger()
    ledger_findings = ledger.evaluate(doc, jd)
    total_ledger = sum(f.points for f in ledger_findings)
    
    # Deduct ledger from strength
    strength_final = max(0.0, strength_score - total_ledger)
    
    # 4. Parseability (Extracted from layout facts and specific formatting checks)
    parseability = 100.0
    if doc.layout.is_scanned:
        parseability = 0.0
    elif doc.layout.has_columns:
        parseability -= 20.0
        
    # 5. Match / RoleFit
    match_score: float | None = None
    role_fit_score: float | None = None
    match_fallback = False

    if jd:
        m_s, m_results = _run_dimension_checks(doc, jd, rubric, "MATCH", match_checks)
        if not jd.keywords:
            # A title/seniority guess cannot establish a skill match for an unreadable JD.
            m_s, m_results = None, []

        # Bug 1 fix: m_s is None when ALL match checks returned None (e.g. JD has no keywords)
        if m_s is not None:
            if is_archetype:
                role_fit_score = m_s * 100.0
            else:
                match_score = m_s * 100.0
        else:
            # JD was supplied but unreadable — flag it, do NOT treat as 0% match
            match_fallback = True

        for res in m_results:
            all_findings.extend(res.findings)

    # 6. Headline formula
    parse_gate = 0.75 + 0.25 * (parseability / 100.0)
    strength_gated = strength_final * parse_gate

    if jd and not is_archetype:
        if match_score is not None:
            # Normal targeted mode: blend match + strength
            headline = 0.45 * match_score + 0.55 * strength_gated
        else:
            # Bug 1 fix: JD supplied but unreadable — fall back to baseline formula
            # Do NOT compute 0.45*None or 0.45*0; the user still has a valid strength score
            headline = strength_gated
    elif jd and is_archetype:
        if role_fit_score is not None:
            headline = 0.25 * role_fit_score + 0.75 * strength_gated
        else:
            headline = strength_gated
    else:
        headline = strength_gated
        
    return ScoreReport(
        version=SCORING_VERSION,
        parseability=round(parseability, 1),
        strength=round(calibrate(strength_final), 1),
        match=round(calibrate(match_score), 1) if match_score is not None else None,
        role_fit=round(calibrate(role_fit_score), 1) if role_fit_score is not None else None,
        headline=round(calibrate(headline), 1),
        findings=tuple(all_findings),
        ledger_applied=tuple(ledger_findings),
        match_fallback=match_fallback,
    )
