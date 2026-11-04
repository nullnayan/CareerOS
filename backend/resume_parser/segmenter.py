"""
Module 3 — Section Segmentation
================================
Phase 2 of the resume parser pipeline.

Splits the raw text into labelled sections using a heading-pattern registry.
Each heading variant maps to a canonical section name.

Key design decisions:
- Unknown headings are collected in "unknown_sections" (not silently dropped)
- Failed/malformed headings go in "failed_sections" for debugging
- Sections are stored as plain text strings keyed by canonical name
- If a heading matches multiple canonical names, the first match wins

Output shape:
{
    "experience": "...",
    "education": "...",
    "skills": "...",
    "contact": "...",
    ...
    "unknown_sections": {"My Journey": "...", ...},
    "failed_sections": ["Malformed Heading →", ...],
    "section_order": ["contact", "experience", "education", ...]
}
"""

import re
from typing import Optional

# ─── Heading → Canonical Name Registry ────────────────────────────────────────
#
# Ordered by specificity (more specific patterns first within each group).
# Keys are lowercase regex patterns; values are canonical section names.

HEADING_PATTERNS: list[tuple[str, str]] = [

    # ── Contact / Personal Info ────────────────────────────────────────────────
    (r"contact(\s+info(rmation)?)?", "contact"),
    (r"personal(\s+(info(rmation)?|details|profile))?", "contact"),
    (r"about\s+me", "contact"),
    (r"profile", "contact"),

    # ── Summary / Objective ────────────────────────────────────────────────────
    (r"(professional\s+)?summary", "summary"),
    (r"(career\s+)?objective", "summary"),
    (r"professional\s+profile", "summary"),
    (r"executive\s+summary", "summary"),
    (r"overview", "summary"),
    (r"introduction", "summary"),
    (r"highlights?", "summary"),

    # ── Experience ─────────────────────────────────────────────────────────────
    (r"(work|professional|relevant|industry|job|employment|career)\s+experience", "experience"),
    (r"experience", "experience"),
    (r"employment\s+(history|record|background)?", "experience"),
    (r"work\s+history", "experience"),
    (r"positions?\s+held", "experience"),
    (r"professional\s+background", "experience"),
    (r"professional\s+history", "experience"),

    # ── Education ─────────────────────────────────────────────────────────────
    (r"education(al)?\s*(background|history|qualification)?", "education"),
    (r"academic(s|\s+background|\s+history|\s+qualifications?)?", "education"),
    (r"qualification(s)?", "education"),
    (r"degrees?(\s+earned)?", "education"),
    (r"schooling", "education"),

    # ── Skills ────────────────────────────────────────────────────────────────
    (r"(technical\s+|core\s+|key\s+|professional\s+)?skills?(\s+&\s+expertise)?", "skills"),
    (r"(technical\s+)?competenc(ies|y)", "skills"),
    (r"expertise", "skills"),
    (r"(technical\s+)?proficienc(ies|y)", "skills"),
    (r"technologies?", "skills"),
    (r"tool(s)?(\s+&\s+technologies)?", "skills"),
    (r"(core\s+)?capabilities", "skills"),

    # ── Projects ──────────────────────────────────────────────────────────────
    (r"(key\s+|personal\s+|selected\s+|notable\s+|major\s+)?projects?", "projects"),
    (r"(personal\s+|open.source\s+)?work", "projects"),
    (r"portfolio", "projects"),

    # ── Certifications ────────────────────────────────────────────────────────
    (r"certifications?(\s+[&]\s+(courses?|licenses?))?", "certifications"),
    (r"licenses?\s+([&]\s+certifications?)?", "certifications"),
    (r"credentials?", "certifications"),
    (r"professional\s+development", "certifications"),
    (r"courses?(\s+[&]\s+certifications?)?", "certifications"),
    (r"training(\s+[&]\s+certifications?)?", "certifications"),

    # ── Languages ─────────────────────────────────────────────────────────────
    (r"languages?(\s+(spoken|known|proficiency))?", "languages"),
    (r"linguistic\s+(abilities|skills)", "languages"),

    # ── Awards & Achievements ─────────────────────────────────────────────────
    (r"awards?(\s+&\s+(achievements?|honors?))?", "achievements"),
    (r"achievements?(\s+&\s+awards?)?", "achievements"),
    (r"honors?(\s+&\s+awards?)?", "achievements"),
    (r"accomplishments?", "achievements"),
    (r"recognition", "achievements"),

    # ── Publications ──────────────────────────────────────────────────────────
    (r"publications?", "publications"),
    (r"research(\s+&\s+publications?)?", "publications"),
    (r"papers?(\s+&\s+publications?)?", "publications"),

    # ── Volunteer / Community ─────────────────────────────────────────────────
    (r"volunteer(ing|s?\s+experience|s?\s+work)?", "volunteer"),
    (r"community\s+(service|involvement|engagement)", "volunteer"),
    (r"social\s+(work|impact)", "volunteer"),

    # ── References ────────────────────────────────────────────────────────────
    (r"references?(\s+available(\s+upon\s+request)?)?", "references"),

    # ── Interests / Hobbies ───────────────────────────────────────────────────
    (r"interests?(\s+&\s+hobbies)?", "interests"),
    (r"hobbies(\s+&\s+interests?)?", "interests"),
    (r"extracurricular(s|\s+activities)?", "interests"),
    (r"activities", "interests"),
]

# Compile all patterns once at import time for performance
_COMPILED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^\s*" + pat + r"\s*$", re.IGNORECASE | re.MULTILINE), name)
    for pat, name in HEADING_PATTERNS
]

# Characters a heading line might end with (bold markers, underlines, etc.)
_HEADING_SUFFIX = re.compile(r"[:\-–—_]+$")
_HEADING_PREFIX = re.compile(r"^[•\-–—▸▶►✦✧★●■□▪◆◇\s]+")

# Max characters for a line to be considered a heading candidate
_MAX_HEADING_LENGTH = 60

# Patterns that definitively mark a line as NOT a heading
_DATE_LINE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}"
    r"|\b\d{4}\s*[-–]\s*(?:\d{4}|Present|Current|Now)\b"
    r"|\b\d{4}\s*to\s*(?:\d{4}|Present)\b",
    re.IGNORECASE
)
_CONTACT_LINE = re.compile(r"@|linkedin\.com|github\.com|http[s]?://")
_PIPE_SEPARATOR = re.compile(r"\|")
_HAS_COMMA = re.compile(r",")
_HAS_PARENS_CONTENT = re.compile(r"\([^)]{3,}\)")


# ─── Public entry point ────────────────────────────────────────────────────────

def segment(raw_text: str) -> dict:
    """
    Takes raw extracted text, returns a dict of sections keyed by canonical name,
    plus unknown_sections, failed_sections, and section_order.
    """
    lines = raw_text.split("\n")
    sections: dict[str, str] = {}
    unknown_sections: dict[str, str] = {}
    failed_sections: list[str] = []
    section_order: list[str] = []
    original_section_headings: dict[str, str] = {}

    current_key: Optional[str] = None      # canonical name or None
    current_heading: Optional[str] = None  # original heading text
    current_lines: list[str] = []

    def _flush():
        """Save current buffer into the right bucket."""
        nonlocal current_key, current_heading, current_lines
        if current_heading is None:
            current_lines = []
            return

        content = "\n".join(current_lines).strip()
        if current_key is not None:
            # Known section — merge if already exists (e.g. two "Experience" headings)
            if current_key in sections:
                sections[current_key] += "\n\n" + content
            else:
                sections[current_key] = content
                section_order.append(current_key)
                original_section_headings[current_key] = current_heading
        else:
            # Unknown heading
            unknown_sections[current_heading] = content
            section_order.append(f"unknown:{current_heading}")

        current_key = None
        current_heading = None
        current_lines = []

    for line in lines:
        canonical, original = _classify_line(line)

        if canonical is not False:
            # This line is a heading
            _flush()
            current_heading = original
            current_key = canonical  # None means unknown, False means not a heading
        else:
            current_lines.append(line)

    _flush()  # Flush the last section

    return {
        **sections,
        "unknown_sections": unknown_sections,
        "failed_sections": failed_sections,
        "section_order": section_order,
        "original_section_headings": original_section_headings,
    }


# ─── Heading classifier ────────────────────────────────────────────────────────

def _classify_line(line: str) -> tuple:
    """
    Returns (canonical_name_or_None, cleaned_line) if this line looks like a section heading,
    or (False, None) if it's regular body text.

    canonical_name_or_None:
        - str  → matched a known pattern
        - None → looks like a heading but no pattern matched (unknown section)
        - False → not a heading at all
    """
    stripped = line.strip()

    # Empty lines are not headings
    if not stripped:
        return False, None

    # Too long to be a heading
    if len(stripped) > _MAX_HEADING_LENGTH:
        return False, None

    # --- Hard rejections: lines that are definitely NOT headings ---------------

    # Date lines ("Jan 2020 - Present", "2018 - 2022", etc.)
    if _DATE_LINE.search(stripped):
        return False, None

    # Contact info lines (email, URLs, pipes separating info)
    if _CONTACT_LINE.search(stripped):
        return False, None

    # Pipe-separated lines are almost always contact/header info
    if _PIPE_SEPARATOR.search(stripped):
        return False, None

    # Lines with parenthetical content like "English (Native), Hindi (Fluent)"
    # or "AWS Certified Solutions Architect (2022)" — these are body content
    if _HAS_PARENS_CONTENT.search(stripped):
        return False, None

    # Lines with commas are content, not headings
    if _HAS_COMMA.search(stripped):
        return False, None

    # Clean up heading markers (bullets, dashes, colons)
    cleaned = _HEADING_PREFIX.sub("", stripped)
    cleaned = _HEADING_SUFFIX.sub("", cleaned).strip()

    if not cleaned:
        return False, None

    # Must be mostly letters (headings don't contain lots of special chars or numbers)
    letter_ratio = sum(c.isalpha() or c.isspace() for c in cleaned) / len(cleaned)
    if letter_ratio < 0.70:
        return False, None

    # Headings are short — reject lines with more than 6 words
    words = cleaned.split()
    if len(words) > 6:
        return False, None

    # Try to match against known patterns
    for pattern, canonical in _COMPILED_PATTERNS:
        if pattern.match(cleaned):
            return canonical, cleaned

    # Unknown heading heuristic — only flag if:
    # - Starts with uppercase
    # - All words are purely alphabetic (no numbers, no special chars)
    # - 1-4 words
    # - Does NOT contain prepositions that indicate a content line
    #   (e.g. "Software Engineer at Google", "Massachusetts Institute of Technology")
    _CONTENT_PREPOSITIONS = {"at", "for", "with", "by", "from", "via", "of", "and"}
    if cleaned[0].isupper() and len(words) <= 4:
        if all(w.isalpha() for w in words):
            # Reject if any word is a common preposition (indicates a job title / institution)
            word_set = {w.lower() for w in words}
            if not word_set.intersection(_CONTENT_PREPOSITIONS):
                return None, cleaned

    return False, None
