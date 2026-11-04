"""
match.py — MATCH dimension checks (JD-required).

Phase 5/6 rebuild:
- KeywordMatchCheck: rewritten with word-boundary regex (no 'Go' inside 'Django')
- TitleMatchCheck: uses real extracted title now (Bug 5 was fixed in api_adapter)
- SeniorityFitCheck: NEW — checks if resume years match JD seniority expectation
- HardSkillsCoverageCheck: NEW — separates hard skill coverage from general keyword match
"""
import re
from typing import Optional, Any

from .base import register, build_result, ALL_SENIORITIES
from ..models import ResumeDoc, CheckResult, Finding

SENIORITY_YEAR_MAP = {
    "junior": (0, 2),
    "entry": (0, 3),
    "mid": (2, 6),
    "senior": (5, 15),
    "lead": (5, 15),
    "principal": (8, 20),
    "staff": (6, 18),
    "exec": (10, 40),
    "director": (8, 30),
}


def _word_boundary_match(term: str, text: str) -> bool:
    """Match term at word boundaries to avoid 'Go' inside 'Django'."""
    try:
        return bool(re.search(r"\b" + re.escape(term.lower()) + r"\b", text.lower()))
    except re.error:
        return term.lower() in text.lower()


@register
class KeywordMatchCheck:
    id = "keyword_match"
    dimension = "MATCH"
    requires_jd = True
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not jd or not jd.keywords:
            return build_result(self.id, None, [], {"reason": "no_jd"})

        text = doc.text.full
        matched = []
        missing = []

        for kw in jd.keywords:
            if _word_boundary_match(kw.term, text):
                matched.append(kw.term)
            else:
                missing.append(kw)

        if not jd.keywords:
            return build_result(self.id, 0.5, [], {"reason": "no_keywords_in_jd"})

        match_ratio = len(matched) / len(jd.keywords)

        findings = []
        # Only report top-5 missing keywords to avoid noise
        for kw in missing[:5]:
            sev = "high" if kw.required else "medium"
            findings.append(Finding(
                check_id=self.id,
                severity=sev,
                title=f"Missing keyword: '{kw.term}'",
                detail=f"Add '{kw.term}' naturally to a bullet point, skills section, or summary.",
                anchor=None,
                fix=None,
            ))

        return build_result(self.id, match_ratio, findings, {
            "matched": len(matched),
            "missing": len(missing),
            "total": len(jd.keywords),
        })


@register
class TitleMatchCheck:
    id = "title_match"
    dimension = "MATCH"
    requires_jd = True
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not jd:
            return build_result(self.id, None, [], {"reason": "no_jd"})

        jd_title_norm = jd.title_normalized.lower().replace("_", " ")
        if not jd_title_norm or jd_title_norm == "unknown title":
            return build_result(self.id, None, [], {"reason": "jd_title_unknown"})

        full_text = doc.text.full.lower()
        # Check title variants in experience titles + summary
        exp_titles = [e.title.lower() for e in doc.experience]
        summary = (doc.summary or "").lower()

        # Score: 1.0 if exact title found, 0.6 if keyword found in context
        if any(jd_title_norm in t for t in exp_titles):
            score = 1.0
        elif jd_title_norm in summary:
            score = 0.8
        elif _word_boundary_match(jd_title_norm.split()[0], full_text) if jd_title_norm.split() else False:
            score = 0.5
        else:
            score = 0.2

        findings = []
        if score < 0.6:
            findings.append(Finding(
                check_id=self.id, severity="medium",
                title=f"Title mismatch: JD expects '{jd.title}'",
                detail="Add the target job title to your summary or most recent experience.",
                anchor=None, fix=None,
            ))

        return build_result(self.id, score, findings, {"jd_title": jd.title, "score": score})


@register
class SeniorityFitCheck:
    id = "seniority_fit"
    dimension = "MATCH"
    requires_jd = True
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not jd:
            return build_result(self.id, None, [], {"reason": "no_jd"})

        jd_title_lower = jd.title.lower()
        years = doc.profile.years_experience

        # Find expected years range from JD title
        expected_range = None
        for keyword, (min_y, max_y) in SENIORITY_YEAR_MAP.items():
            if keyword in jd_title_lower:
                expected_range = (min_y, max_y)
                break

        # Also use jd.min_years if set
        if jd.min_years is not None:
            expected_range = (jd.min_years, 99)

        if expected_range is None:
            return build_result(self.id, None, [], {"reason": "seniority_not_inferable"})

        min_y, max_y = expected_range
        findings = []

        if years < min_y:
            gap = min_y - years
            score = max(0.3, 1.0 - gap * 0.15)
            findings.append(Finding(
                check_id=self.id, severity="medium",
                title=f"Experience gap: {years:.0f} yrs vs {min_y}+ yrs expected",
                detail="You may be under-qualified. Strengthen project and impact bullets to compensate.",
                anchor=None, fix=None,
            ))
        elif years > max_y:
            score = 0.7  # over-qualified — soft flag
            findings.append(Finding(
                check_id=self.id, severity="low",
                title=f"Possibly over-qualified ({years:.0f} yrs)",
                detail="Consider tailoring your summary to clarify why you're targeting this level.",
                anchor=None, fix=None,
            ))
        else:
            score = 1.0

        return build_result(self.id, score, findings, {"years": years, "expected": expected_range})


@register
class HardSkillsCoverageCheck:
    id = "hard_skills_coverage"
    dimension = "MATCH"
    requires_jd = True
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not jd or not jd.keywords:
            return build_result(self.id, None, [], {"reason": "no_jd"})

        # Filter to hard skills and tools only
        hard_kws = [kw for kw in jd.keywords if kw.kind in ("hard", "tool", "certification")]
        if not hard_kws:
            return build_result(self.id, None, [], {"reason": "no_hard_skills_in_jd"})

        text = doc.text.full
        matched = [kw for kw in hard_kws if _word_boundary_match(kw.term, text)]
        ratio = len(matched) / len(hard_kws)

        findings = []
        missing = [kw for kw in hard_kws if kw not in matched]
        for kw in missing[:3]:
            findings.append(Finding(
                check_id=self.id, severity="high" if kw.required else "medium",
                title=f"Missing hard skill: '{kw.term}'",
                detail=f"Add '{kw.term}' to your skills section or in a bullet if you have used it.",
                anchor=None, fix=None,
            ))

        return build_result(self.id, ratio, findings, {
            "hard_matched": len(matched),
            "hard_total": len(hard_kws),
        })
