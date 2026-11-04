"""
authenticity.py — AUTHENTICITY dimension checks.

Phase 5 rebuild:
- DuplicateBulletsCheck: existing, improved
- KeywordStuffingCheck: existing, improved  
- DateGapsCheck: NEW — detects unexplained employment gaps > 6 months
- DateOverlapsCheck: NEW — flags impossible overlapping dates
- TitleInflationCheck: NEW — "Chief", "Principal" at entry level
- UnverifiableSuperlativesCheck: NEW — "best", "top 1%", "world-class"
"""
import re
from datetime import datetime
from typing import Optional, Any

from .base import register, build_result, ALL_SENIORITIES
from ..models import ResumeDoc, CheckResult, Finding

SUPERLATIVE_PATTERNS = [
    re.compile(r"\bbest\s+in\s+class\b", re.IGNORECASE),
    re.compile(r"\btop\s+\d+\s*%\b", re.IGNORECASE),
    re.compile(r"\bworld[\s-]?class\b", re.IGNORECASE),
    re.compile(r"\b#1\b|\bnumber\s+one\b", re.IGNORECASE),
    re.compile(r"\bunrivalled\b|\bunparalleled\b", re.IGNORECASE),
    re.compile(r"\bexpert\s+in\s+all\b", re.IGNORECASE),
]

INFLATED_TITLES_FOR_JUNIOR = frozenset({
    "chief", "vp", "vice president", "director", "principal", "distinguished",
    "fellow", "c-suite", "cto", "ceo", "cfo", "coo", "svp", "evp",
})


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse YYYY-MM or YYYY date strings."""
    if not date_str:
        return None
    for fmt in ("%Y-%m", "%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            pass
    return None


@register
class DuplicateBulletsCheck:
    id = "duplicate_bullets"
    dimension = "AUTHENTICITY"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        texts = [b.text.strip().lower() for b in bullets]
        seen: set[str] = set()
        duplicates = 0
        findings = []

        for i, (text, bullet) in enumerate(zip(texts, bullets)):
            if text in seen:
                duplicates += 1
                findings.append(Finding(
                    check_id=self.id, severity="medium",
                    title="Duplicate bullet",
                    detail="This bullet appears more than once. Replace with distinct accomplishments.",
                    anchor=None, fix=None,
                ))
            seen.add(text)

        dup_ratio = duplicates / len(bullets)
        score = max(0.0, 1.0 - dup_ratio * 3)
        return build_result(self.id, score, findings, {"duplicates": duplicates})


@register
class KeywordStuffingCheck:
    id = "keyword_stuffing"
    dimension = "AUTHENTICITY"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    SKILLS_SECTION_THRESHOLD = 60  # more than 60 comma/slash-separated tokens = stuffed

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        skills_text = doc.text.by_section.get("skills", "")
        if not skills_text:
            return build_result(self.id, None, [], {"reason": "no_skills_section"})

        # Count tokens (split by , | / ·)
        tokens = re.split(r"[,|/·•]+", skills_text)
        token_count = len([t for t in tokens if t.strip()])

        findings = []
        if token_count > self.SKILLS_SECTION_THRESHOLD:
            findings.append(Finding(
                check_id=self.id, severity="medium",
                title=f"Skills section overloaded ({token_count} items)",
                detail="Limit skills to the 20–30 most relevant. Keyword stuffing reads as dishonest.",
                anchor=None, fix=None,
            ))
            score = max(0.3, self.SKILLS_SECTION_THRESHOLD / token_count)
        else:
            score = 1.0

        return build_result(self.id, score, findings, {"token_count": token_count})


@register
class DateGapsCheck:
    id = "date_gaps"
    dimension = "AUTHENTICITY"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    GAP_MONTHS_THRESHOLD = 7  # gaps of 7+ months get flagged

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not doc.experience:
            return build_result(self.id, None, [], {"reason": "no_experience"})

        experiences = doc.experience
        # Sort by start date
        dated = []
        for exp in experiences:
            start = _parse_date(exp.start_date)
            end = _parse_date(exp.end_date) if not exp.is_current else datetime.now()
            if start and end:
                dated.append((start, end, exp))

        if len(dated) < 2:
            return build_result(self.id, None, [], {"reason": "insufficient_dated_entries"})

        dated.sort(key=lambda x: x[0])

        findings = []
        gaps_found = 0

        for i in range(1, len(dated)):
            prev_end = dated[i - 1][1]
            curr_start = dated[i][0]
            gap_months = (curr_start.year - prev_end.year) * 12 + (curr_start.month - prev_end.month)

            if gap_months > self.GAP_MONTHS_THRESHOLD:
                gaps_found += 1
                findings.append(Finding(
                    check_id=self.id, severity="medium",
                    title=f"Employment gap of ~{gap_months} months",
                    detail="Consider briefly explaining gaps with freelance work, education, or personal projects.",
                    anchor=None, fix=None,
                ))

        score = max(0.0, 1.0 - gaps_found * 0.25)
        return build_result(self.id, score, findings, {"gaps_found": gaps_found})


@register
class DateOverlapsCheck:
    id = "date_overlaps"
    dimension = "AUTHENTICITY"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not doc.experience:
            return build_result(self.id, None, [], {"reason": "no_experience"})

        dated = []
        for exp in doc.experience:
            start = _parse_date(exp.start_date)
            end = _parse_date(exp.end_date) if not exp.is_current else datetime.now()
            if start and end and start < end:
                dated.append((start, end, exp))

        if len(dated) < 2:
            return build_result(self.id, None, [], {"reason": "insufficient_dated_entries"})

        dated.sort(key=lambda x: x[0])
        findings = []
        overlaps = 0

        for i in range(1, len(dated)):
            prev_end = dated[i - 1][1]
            curr_start = dated[i][0]
            # Overlap if the next role starts before the previous one ends by more than 1 month
            overlap_months = (prev_end.year - curr_start.year) * 12 + (prev_end.month - curr_start.month)
            if overlap_months > 1:  # 1 month tolerance for rounding
                overlaps += 1
                findings.append(Finding(
                    check_id=self.id, severity="high",
                    title=f"Overlapping dates detected",
                    detail=f"'{dated[i][2].title}' overlaps with '{dated[i-1][2].title}' by ~{overlap_months} months. Verify your dates.",
                    anchor=None, fix=None,
                ))

        score = max(0.0, 1.0 - overlaps * 0.4)
        return build_result(self.id, score, findings, {"overlaps": overlaps})


@register
class UnverifiableSuperlativesCheck:
    id = "unverifiable_superlatives"
    dimension = "AUTHENTICITY"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        full_text = doc.text.full
        if not full_text.strip():
            return build_result(self.id, None, [], {"reason": "empty"})

        found = []
        for pattern in SUPERLATIVE_PATTERNS:
            m = pattern.search(full_text)
            if m:
                found.append(m.group())

        findings = []
        if found:
            findings.append(Finding(
                check_id=self.id, severity="medium",
                title=f"Unverifiable superlative: '{found[0]}'",
                detail="Remove claims that can't be verified. Back claims with data instead.",
                anchor=None, fix=None,
            ))

        score = max(0.0, 1.0 - len(found) * 0.25)
        return build_result(self.id, score, findings, {"superlatives_found": found})
