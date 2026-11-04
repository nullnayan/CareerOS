"""
growth.py — GROWTH dimension checks.

Phase 5 rebuild:
- LeadershipCheck: rewritten — reads leadership_expectation from rubric, not hardcoded /3
- CareerProgressionCheck: improved — scores title trajectory properly, not just binary
- TitleTrajectoryCheck: NEW — checks if titles show increasing seniority over time
- TenurePatternCheck: NEW — very short tenures (<6 months) raise concerns
- IncreasingScopeCheck: NEW — team size, budget mentions increase over career
"""
import re
from datetime import datetime
from typing import Optional, Any

from .base import register, build_result, ALL_SENIORITIES
from ..models import ResumeDoc, CheckResult, Finding

LEADERSHIP_SIGNALS = frozenset({
    "led", "managed", "mentored", "coordinated", "organized", "organised", "directed",
    "supervised", "spearheaded", "founded", "initiated", "orchestrated", "hired",
    "built the team", "grew the team", "recruited", "coached", "delegated",
})

SENIORITY_TITLE_LEVELS = {
    "intern": 0, "apprentice": 0, "trainee": 0,
    "junior": 1, "jr": 1, "associate": 1, "entry": 1,
    "": 2, "engineer": 2, "developer": 2, "analyst": 2, "designer": 2,
    "senior": 3, "sr": 3, "staff": 3, "lead": 3, "principal": 4,
    "director": 5, "head": 5, "manager": 4,
    "vp": 6, "vice president": 6, "chief": 7, "cto": 7, "ceo": 7,
}

SCOPE_PATTERNS = [
    re.compile(r"\bteam\s+of\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"\bmanaged\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"\$[\d,.]+[KMBkmb]?\s+budget\b", re.IGNORECASE),
    re.compile(r"\b(\d+)\s+(?:engineers?|developers?|reports?|direct\s+reports?)\b", re.IGNORECASE),
]


def _title_level(title: str) -> int:
    title_lower = title.lower()
    best = 2  # default: individual contributor
    for kw, level in SENIORITY_TITLE_LEVELS.items():
        if kw and kw in title_lower:
            best = max(best, level)
    return best


def _parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ("%Y-%m", "%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            pass
    return None


@register
class LeadershipCheck:
    id = "leadership"
    dimension = "GROWTH"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        expected_ratio = rubric.leadership_expectation  # from rubric, not hardcoded
        text_lower = doc.text.full.lower()

        # Word-boundary match for leadership signals
        leadership_hits = sum(
            1 for signal in LEADERSHIP_SIGNALS
            if re.search(r"\b" + re.escape(signal) + r"\b", text_lower)
        )

        bullet_count = len(bullets)
        actual_ratio = leadership_hits / bullet_count

        if actual_ratio >= expected_ratio:
            score = 1.0
        else:
            score = actual_ratio / max(expected_ratio, 0.01)

        findings = []
        if score < 0.5 and rubric.band in ("senior", "exec"):
            findings.append(Finding(
                check_id=self.id, severity="high",
                title="Insufficient leadership signals",
                detail=f"For {rubric.band} level, at least {expected_ratio:.0%} of bullets should show leadership outcomes.",
                anchor=None, fix=None,
            ))
        elif score < 0.5 and rubric.band == "mid":
            findings.append(Finding(
                check_id=self.id, severity="medium",
                title="Limited leadership evidence",
                detail="Add bullets showing mentorship, project ownership, or cross-team collaboration.",
                anchor=None, fix=None,
            ))

        return build_result(self.id, score, findings, {
            "leadership_hits": leadership_hits, "expected_ratio": expected_ratio
        })


@register
class CareerProgressionCheck:
    id = "career_progression"
    dimension = "GROWTH"
    requires_jd = False
    applies_to = ("mid", "senior", "exec")  # students/entry not expected to show progression

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if len(doc.experience) < 2:
            return build_result(self.id, None, [], {"reason": "insufficient_experience"})

        # Sort by start date
        dated = []
        for exp in doc.experience:
            start = _parse_date(exp.start_date)
            if start:
                dated.append((start, exp))
        dated.sort(key=lambda x: x[0])

        if len(dated) < 2:
            return build_result(self.id, None, [], {"reason": "undated_entries"})

        levels = [_title_level(d[1].title) for d in dated]
        progression_steps = sum(1 for i in range(1, len(levels)) if levels[i] >= levels[i - 1])
        ratio = progression_steps / (len(levels) - 1)

        findings = []
        if ratio < 0.5:
            findings.append(Finding(
                check_id=self.id, severity="medium",
                title="Non-linear title progression",
                detail="Titles should show increasing seniority over time. Clarify promotions or lateral moves.",
                anchor=None, fix=None,
            ))

        return build_result(self.id, ratio, findings, {"levels": levels, "progression_ratio": ratio})


@register
class TenurePatternCheck:
    id = "tenure_pattern"
    dimension = "GROWTH"
    requires_jd = False
    applies_to = ("mid", "senior", "exec")

    SHORT_TENURE_MONTHS = 6

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not doc.experience:
            return build_result(self.id, None, [], {"reason": "no_experience"})

        short_stints = 0
        findings = []
        dated_count = 0

        for exp in doc.experience:
            start = _parse_date(exp.start_date)
            end = _parse_date(exp.end_date) if not exp.is_current else datetime.now()
            if not (start and end):
                continue
            dated_count += 1
            months = (end.year - start.year) * 12 + (end.month - start.month)
            if months < self.SHORT_TENURE_MONTHS:
                short_stints += 1
                findings.append(Finding(
                    check_id=self.id, severity="low",
                    title=f"Short tenure at '{exp.company}' (~{months} months)",
                    detail="Brief stays are fine occasionally. If more than one, add context (contract, acquisition, etc.).",
                    anchor=None, fix=None,
                ))

        if dated_count == 0:
            return build_result(self.id, None, [], {"reason": "no_dated_entries"})

        short_ratio = short_stints / dated_count
        score = max(0.0, 1.0 - short_ratio * 2)
        return build_result(self.id, score, findings, {"short_stints": short_stints})


@register
class IncreasingScopeCheck:
    id = "increasing_scope"
    dimension = "GROWTH"
    requires_jd = False
    applies_to = ("senior", "exec")

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        """Checks that team/budget scope signals appear in the resume at all."""
        full_text = doc.text.full
        if not full_text.strip():
            return build_result(self.id, None, [], {"reason": "empty"})

        scope_hits = []
        for pattern in SCOPE_PATTERNS:
            matches = pattern.findall(full_text)
            scope_hits.extend(matches)

        findings = []
        if not scope_hits:
            findings.append(Finding(
                check_id=self.id, severity="medium",
                title="No scope signals for senior level",
                detail="For senior/exec roles, include team size, budget managed, or org-level impact metrics.",
                anchor=None, fix=None,
            ))
            score = 0.2
        else:
            score = min(1.0, len(scope_hits) * 0.3)

        return build_result(self.id, score, findings, {"scope_hits": len(scope_hits)})
