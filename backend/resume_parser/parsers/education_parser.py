"""
Module 6 — Education Parser
============================
Phase 3 (second parser).

Extracts education entries:
    degree, field of study, institution, start year, end year,
    GPA, honors, location

Output:
[
  {
    "degree": "Bachelor of Science",
    "field": "Computer Science",
    "institution": "MIT",
    "startYear": 2018,
    "endYear": 2022,
    "gpa": "3.8",
    "honors": "Magna Cum Laude",
    "location": "Cambridge, MA",
    "_confidence": {"degree": "high", "institution": "medium", ...}
  },
  ...
]
"""

import re
from typing import Optional

# ─── Degree keywords → canonical names ────────────────────────────────────────

DEGREE_PATTERNS = [
    (r"doctor\s+of\s+philosophy|ph\.?\s*d\.?", "Doctor of Philosophy (PhD)"),
    (r"doctor\s+of\s+(medicine|dental|veterinary|pharmacy|law)", "Doctoral Degree"),
    (r"master\s+of\s+science|\bm\.?\s*s\.?c?\.?\b", "Master of Science"),
    (r"master\s+of\s+arts|\bm\.?\s*a\.?\b", "Master of Arts"),
    (r"master\s+of\s+business\s+administration|\bm\.?\s*b\.?\s*a\.?\b", "Master of Business Administration (MBA)"),
    (r"master\s+of\s+engineering|\bm\.?\s*e\.?(?:ng)?\.?\b", "Master of Engineering"),
    (r"\bmaster(?:'?s)?\s+(?:degree|in\b)", "Master's Degree"),
    (r"bachelor\s+of\s+science|\bb\.?\s*s\.?c?\.?\b|\bb\.?\s*s\.?\s+in\b", "Bachelor of Science"),
    (r"bachelor\s+of\s+arts|\bb\.?\s*a\.?\s+in\b|\bb\.?\s*a\.?\b", "Bachelor of Arts"),
    (r"bachelor\s+of\s+engineering|\bb\.?\s*e\.?(?:ng)?\.?\b", "Bachelor of Engineering"),
    (r"bachelor\s+of\s+technology|\bb\.?\s*tech\.?\b", "Bachelor of Technology"),
    (r"\bbachelor(?:'?s)?\s+(?:degree|in\b)", "Bachelor's Degree"),
    (r"associate\s+of\s+(?:science|arts|applied\s+science)?", "Associate Degree"),
    (r"associate(?:'?s)?\s+degree", "Associate Degree"),
    (r"high\s+school\s+diploma|h\.?\s*s\.?\s*d\.?", "High School Diploma"),
    (r"g\.?e\.?d\.?", "GED"),
    (r"diploma", "Diploma"),
    (r"certificate", "Certificate"),
]

_DEGREE_RE = [(re.compile(pat, re.IGNORECASE), name) for pat, name in DEGREE_PATTERNS]

# ── Date patterns ─────────────────────────────────────────────────────────────
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_DATE_RANGE_RE = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*)?(\d{4})"
    r"\s*(?:[-–—]|to)\s*"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*)?(Present|\d{4})",
    re.IGNORECASE
)

# ── GPA patterns ──────────────────────────────────────────────────────────────
_GPA_RE = re.compile(r"(?:gpa|grade\s+point\s+average)[:\s]*([0-9]\.[0-9]{1,2}(?:/[0-9]\.[0-9])?)", re.IGNORECASE)

# ── Honors ────────────────────────────────────────────────────────────────────
_HONORS_RE = re.compile(
    r"\b(summa\s+cum\s+laude|magna\s+cum\s+laude|cum\s+laude|"
    r"with\s+(?:high\s+)?honors?|dean'?s?\s+list|first\s+class\s+honours?|"
    r"distinction)\b",
    re.IGNORECASE
)

# ── Entry splitting ────────────────────────────────────────────────────────────
# Education sections often have multiple entries separated by blank lines
_BLANK_LINE = re.compile(r"\n{2,}")


def parse(education_text: str) -> list[dict]:
    """
    Parse the education section text into a list of education entries.
    """
    if not education_text.strip():
        return []

    entries = []
    # Split on double newlines to separate multiple education entries
    blocks = _BLANK_LINE.split(education_text.strip())

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 10:
            continue

        entry = _parse_block(block)
        if entry:
            entries.append(entry)

    return entries


def _parse_block(block: str) -> Optional[dict]:
    """Parse a single education block into structured fields."""
    confidence = {}

    # ── Degree ────────────────────────────────────────────────────────────────
    degree = None
    for pattern, canonical in _DEGREE_RE:
        m = pattern.search(block)
        if m:
            degree = canonical
            confidence["degree"] = "high"
            break

    # Skip blocks with no degree-like content (likely noise)
    if not degree:
        # Still try if block has a year (might be a truncated entry)
        if not _YEAR_RE.search(block):
            return None
        confidence["degree"] = "low"

    # ── Field of Study ────────────────────────────────────────────────────────
    field = _extract_field(block)
    if field:
        confidence["field"] = "medium"

    # ── Institution ───────────────────────────────────────────────────────────
    institution = _extract_institution(block)
    if institution:
        confidence["institution"] = "medium"

    # ── Dates ─────────────────────────────────────────────────────────────────
    start_year, end_year = _extract_dates(block)
    if start_year or end_year:
        confidence["dates"] = "high"

    # ── GPA ───────────────────────────────────────────────────────────────────
    gpa = None
    gpa_m = _GPA_RE.search(block)
    if gpa_m:
        gpa = gpa_m.group(1)
        confidence["gpa"] = "high"

    # ── Honors ────────────────────────────────────────────────────────────────
    honors = None
    hon_m = _HONORS_RE.search(block)
    if hon_m:
        honors = hon_m.group(0).strip()
        confidence["honors"] = "high"

    return {
        "degree": degree,
        "field": field,
        "institution": institution,
        "startYear": start_year,
        "endYear": end_year,
        "gpa": gpa,
        "honors": honors,
        "location": None,  # populated by Phase 4 normalization if needed
        "_confidence": confidence,
        "_raw": block  # keep raw for debugging
    }


def _extract_field(block: str) -> Optional[str]:
    """
    Extract field of study using "in/of [Field]" patterns.
    """
    m = re.search(r"\b(?:in|of)\s+([A-Z][a-z]+(?: [A-Za-z]+){0,4})", block)
    if m:
        field = m.group(1).strip()
        # Filter out institution keywords
        if not any(kw in field.lower() for kw in ["university", "college", "institute", "school"]):
            return field
    return None


def _extract_institution(block: str) -> Optional[str]:
    """
    Extract institution name by looking for keywords like University, College,
    Institute, School in the block.
    """
    m = re.search(
        r"([A-Z][a-zA-Z\s&'\-]+(?:University|College|Institute|School|Academy|Polytechnic)[a-zA-Z\s]*)",
        block
    )
    if m:
        return m.group(1).strip()

    # Fallback: look for lines that start with a capital word and don't match degree or date patterns
    for line in block.split("\n"):
        line = line.strip()
        if not line or len(line) < 4:
            continue
        # Skip lines with year numbers (date lines)
        if re.search(r"\b\d{4}\b", line):
            continue
        # Skip lines that match degree patterns
        if any(p.search(line) for p, _ in _DEGREE_RE):
            continue
        # Skip lines that look like field-of-study "in X" lines alone
        if re.match(r"^in\s+\w", line, re.IGNORECASE):
            continue
        # Skip GPA/grade lines
        if re.match(r"^(gpa|grade|honors?|cum\s+laude)", line, re.IGNORECASE):
            continue
        # Match: starts with capital, reasonable length, mostly letters
        if re.match(r"^[A-Z][a-zA-Z\s&'\-]{3,60}$", line):
            letter_ratio = sum(c.isalpha() or c.isspace() for c in line) / len(line)
            if letter_ratio >= 0.8:
                return line
    return None


def _extract_dates(block: str) -> tuple[Optional[int], Optional[int]]:
    """Extract start and end year from date ranges or standalone years."""
    # Try date range first
    m = _DATE_RANGE_RE.search(block)
    if m:
        start = int(m.group(2)) if m.group(2) else None
        end_raw = m.group(4)
        end = None if (end_raw and end_raw.lower() == "present") else (int(end_raw) if end_raw else None)
        return start, end

    # Fallback: grab all 4-digit years
    years = [int(y) for y in _YEAR_RE.findall(block)]
    if len(years) == 1:
        # Single year is usually graduation year
        return None, years[0]
    elif len(years) >= 2:
        years.sort()
        return years[0], years[-1]

    return None, None
