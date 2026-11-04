"""
formatting.py — FORMATTING dimension checks.

Phase 5 rebuild:
- PageCountCheck: now returns None when layout_facts_available=False (pasted text)
- DateFormatConsistencyCheck: improved
- ColumnLayoutCheck: NEW — uses layout.has_columns from probe
- TablesUsedCheck: NEW — uses layout.has_tables
- SpecialCharactersCheck: NEW — bullet glyphs, emoji, unusual symbols
- BulletGlyphConsistencyCheck: NEW — mixed bullet symbols in raw text
"""
import re
from typing import Optional, Any

from .base import register, build_result, ALL_SENIORITIES
from ..models import ResumeDoc, CheckResult, Finding

DATE_FORMATS = [
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b"),  # Jan 2022
    re.compile(r"\b\d{1,2}/\d{4}\b"),        # 01/2022
    re.compile(r"\b\d{4}-\d{2}\b"),           # 2022-01
    re.compile(r"\b\d{4}\b"),                 # 2022
]

SPECIAL_CHARS_PATTERN = re.compile(
    r"[^\x00-\x7F✓→←↑↓●•◦▸▹○–—\-]",  # anything non-ASCII except common safe chars
)

MIXED_BULLETS_THRESHOLD = 2  # more than 2 different glyph types = inconsistent


@register
class PageCountCheck:
    id = "page_count"
    dimension = "FORMATTING"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        # If no PDF was processed, layout facts are unavailable — skip, don't award
        if not hasattr(doc.layout, "page_count") or doc.layout.page_count == 0:
            return build_result(self.id, None, [], {"reason": "layout_not_available"})

        pages = doc.layout.page_count
        max_pages = rubric.max_pages
        findings = []

        if pages > max_pages:
            severity = "high" if pages > max_pages + 1 else "medium"
            findings.append(Finding(
                check_id=self.id, severity=severity,
                title=f"Resume is {pages} pages (max {max_pages} for {rubric.band} level)",
                detail="Trim to the recommended length. Focus on the last 10 years of experience.",
                anchor=None, fix=None,
            ))
            score = max(0.2, max_pages / pages)
        else:
            score = 1.0

        return build_result(self.id, score, findings, {"pages": pages, "max": max_pages})


@register
class DateFormatConsistencyCheck:
    id = "date_format_consistency"
    dimension = "FORMATTING"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        exp_text = doc.text.by_section.get("experience", "")
        if not exp_text.strip():
            return build_result(self.id, None, [], {"reason": "no_experience_text"})

        matched_formats: set[int] = set()
        for i, pattern in enumerate(DATE_FORMATS):
            if pattern.search(exp_text):
                matched_formats.add(i)

        findings = []
        if len(matched_formats) > 1:
            findings.append(Finding(
                check_id=self.id, severity="low",
                title="Inconsistent date formats",
                detail="Use one date format throughout (e.g. 'Jan 2022' or '2022-01').",
                anchor=None, fix=None,
            ))
            score = max(0.4, 1.0 / len(matched_formats))
        else:
            score = 1.0

        return build_result(self.id, score, findings, {"formats_found": len(matched_formats)})


@register
class ColumnLayoutCheck:
    id = "column_layout"
    dimension = "FORMATTING"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not hasattr(doc.layout, "has_columns"):
            return build_result(self.id, None, [], {"reason": "layout_not_available"})

        findings = []
        if doc.layout.has_columns:
            findings.append(Finding(
                check_id=self.id, severity="high",
                title="Multi-column layout detected",
                detail="Most ATS parsers read left-to-right, top-to-bottom. Multi-column resumes often get garbled.",
                anchor=None, fix=None,
            ))
            return build_result(self.id, 0.2, findings, {"has_columns": True})

        return build_result(self.id, 1.0, [], {"has_columns": False})


@register
class TablesUsedCheck:
    id = "tables_used"
    dimension = "FORMATTING"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not hasattr(doc.layout, "has_tables"):
            return build_result(self.id, None, [], {"reason": "layout_not_available"})

        findings = []
        if doc.layout.has_tables:
            findings.append(Finding(
                check_id=self.id, severity="medium",
                title="Tables detected in resume",
                detail="Tables are often skipped or garbled by ATS parsers. Use plain bullet lists instead.",
                anchor=None, fix=None,
            ))
            return build_result(self.id, 0.4, findings, {"has_tables": True})

        return build_result(self.id, 1.0, [], {"has_tables": False})


@register
class SpecialCharactersCheck:
    id = "special_characters"
    dimension = "FORMATTING"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        full_text = doc.text.full
        if not full_text.strip():
            return build_result(self.id, None, [], {"reason": "empty"})

        unusual = SPECIAL_CHARS_PATTERN.findall(full_text)
        unique_unusual = set(unusual)

        findings = []
        if len(unique_unusual) > 5:
            findings.append(Finding(
                check_id=self.id, severity="medium",
                title=f"Unusual characters detected ({len(unique_unusual)} types)",
                detail="Non-standard characters (emoji, special symbols) may not parse correctly in ATS.",
                anchor=None, fix=None,
            ))
            score = max(0.4, 1.0 - len(unique_unusual) * 0.05)
        elif unique_unusual:
            score = 0.8
        else:
            score = 1.0

        return build_result(self.id, score, findings, {"unusual_chars": len(unique_unusual)})


@register
class BulletGlyphConsistencyCheck:
    id = "bullet_glyph_consistency"
    dimension = "FORMATTING"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    GLYPH_PATTERN = re.compile(r"^([\•\●\◦\▸\▹\–\-\*\>])\s", re.MULTILINE)

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        raw_text = doc.text.layout_raw or doc.text.full
        if not raw_text.strip():
            return build_result(self.id, None, [], {"reason": "empty"})

        glyphs = set(self.GLYPH_PATTERN.findall(raw_text))

        findings = []
        if len(glyphs) > MIXED_BULLETS_THRESHOLD:
            findings.append(Finding(
                check_id=self.id, severity="low",
                title=f"Mixed bullet styles ({len(glyphs)} types: {', '.join(repr(g) for g in glyphs)})",
                detail="Use a single consistent bullet glyph throughout the document.",
                anchor=None, fix=None,
            ))
            score = max(0.5, 1.0 - (len(glyphs) - 1) * 0.2)
        else:
            score = 1.0

        return build_result(self.id, score, findings, {"glyph_types": len(glyphs)})
