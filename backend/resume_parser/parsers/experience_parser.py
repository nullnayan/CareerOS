"""
Module 5 — Work Experience Parser
===================================
Phase 3 (hardest parser, built last).

Extracts experience entries:
    company, title, location, start_date, end_date, is_current,
    duration_months, bullets, technologies_mentioned

Also computes derived fields:
    total_years_experience, career_progression, employment_gaps

Output:
[
  {
    "company": "Google",
    "title": "Senior Software Engineer",
    "location": "Mountain View, CA",
    "startDate": "2020-03",
    "endDate": "2023-09",
    "isCurrent": false,
    "durationMonths": 42,
    "bullets": ["Led team of 5...", "Reduced latency by 40%..."],
    "technologiesMentioned": ["Python", "Kubernetes"],
    "_confidence": {...}
  },
  ...
],
"_derived": {
  "totalYearsExperience": 6.5,
  "employmentGaps": [{"from": "2019-01", "to": "2019-06", "months": 5}],
  "careerProgression": "ascending"
}
"""

import re
from datetime import datetime
from typing import Optional
from dateutil import parser as dateutil_parser

# ─── Month abbreviations map ───────────────────────────────────────────────────
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
}

# ─── Date patterns ─────────────────────────────────────────────────────────────
_DATE_RANGE = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}|\d{4})"
    r"\s*(?:[-–—]|to)\s*"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}|\d{4}|Present|Current|Now)",
    re.IGNORECASE
)

_YEAR_ONLY = re.compile(r"\b(20\d{2}|19\d{2})\b")

# ─── Entry split heuristic: blank lines between entries ───────────────────────
_BLANK_LINE = re.compile(r"\n{2,}")

# ─── Bullet point detection ───────────────────────────────────────────────────
_BULLET = re.compile(r"^\s*[•\-–—▸▶►✦✧★●■□▪◆◇*]\s+", re.MULTILINE)

# ─── Location ─────────────────────────────────────────────────────────────────
_LOCATION = re.compile(r"\b([A-Z][a-zA-Z\s]+),\s*([A-Z]{2}|[A-Z][a-zA-Z\s]+)\b")

# ─── Senior titles (for career progression detection) ─────────────────────────
_SENIOR_TITLES = {"senior", "lead", "principal", "staff", "architect", "director", "vp", "head", "chief", "manager"}
_JUNIOR_TITLES = {"junior", "intern", "associate", "trainee", "assistant"}


# ─── Public entry point ────────────────────────────────────────────────────────

def parse(experience_text: str) -> dict:
    """
    Parse the experience section into structured entries + derived fields.
    """
    if not experience_text.strip():
        return {"entries": [], "_derived": _empty_derived()}

    blocks = _split_into_blocks(experience_text)
    entries = []

    for block in blocks:
        entry = _parse_block(block)
        if entry:
            entries.append(entry)

    derived = _compute_derived(entries)

    return {
        "entries": entries,
        "_derived": derived
    }


# ─── Block parsing ─────────────────────────────────────────────────────────────

def _split_into_blocks(text: str) -> list[str]:
    """
    Split on double blank lines first. If that yields only 1 block,
    try splitting on date-range lines (common in dense resumes).
    """
    blocks = [b.strip() for b in _BLANK_LINE.split(text.strip()) if b.strip()]

    if len(blocks) <= 1:
        # Fallback: split on lines that contain a date range
        blocks = _split_by_date_anchors(text)

    return [b for b in blocks if len(b) > 20]


def _split_by_date_anchors(text: str) -> list[str]:
    """Split text into blocks using date-range lines, keeping the title/company lines above it in the same block."""
    lines = text.split("\n")
    blocks = []
    current = []

    for line in lines:
        if _DATE_RANGE.search(line) and current:
            # Pull back the 1-2 lines preceding the date range that are likely title/company
            lookback_lines = []
            while current and len(lookback_lines) < 2:
                prev_line = current[-1].strip()
                # Don't pull back bullet points, empty lines, or other date ranges
                if not prev_line or _BULLET.match(prev_line) or _DATE_RANGE.search(prev_line):
                    break
                lookback_lines.insert(0, current.pop())
            
            # Flush the current block
            if current:
                blocks.append("\n".join(current))
            
            # Start the new block with the lookback lines + the date line
            current = lookback_lines + [line]
        else:
            current.append(line)

    if current:
        blocks.append("\n".join(current))

    return blocks


def _parse_block(block: str) -> Optional[dict]:
    """Parse a single experience block."""
    if len(block.strip()) < 15:
        return None

    lines = [l.strip() for l in block.split("\n") if l.strip()]
    confidence = {}

    # ── Dates ──────────────────────────────────────────────────────────────────
    start_date, end_date, is_current = _extract_dates(block)
    if start_date or end_date:
        confidence["dates"] = "high"

    # ── Duration ───────────────────────────────────────────────────────────────
    duration_months = _calc_duration(start_date, end_date, is_current)

    # ── Title & Company (typically in first 2-3 lines) ─────────────────────────
    title, company = _extract_title_company(lines[:4], block)
    if title:
        confidence["title"] = "medium"
    if company:
        confidence["company"] = "medium"

    # ── Location ───────────────────────────────────────────────────────────────
    location = None
    loc_m = _LOCATION.search("\n".join(lines[:3]))
    if loc_m:
        location = loc_m.group(0).strip()
        confidence["location"] = "medium"

    # ── Bullets ────────────────────────────────────────────────────────────────
    bullets = _extract_bullets(block)
    if bullets:
        confidence["bullets"] = "high"

    # ── Technologies mentioned in bullets ─────────────────────────────────────
    from resume_parser.parsers import skills_parser
    skills_found = skills_parser.parse("", [block])
    technologies = skills_found.get("all", [])

    return {
        "company": company,
        "title": title,
        "location": location,
        "startDate": start_date,
        "endDate": end_date,
        "isCurrent": is_current,
        "durationMonths": duration_months,
        "bullets": bullets,
        "technologiesMentioned": technologies,
        "_confidence": confidence,
        "_raw": block
    }


# ─── Field extractors ──────────────────────────────────────────────────────────

def _extract_dates(text: str) -> tuple[Optional[str], Optional[str], bool]:
    """
    Returns (start_date, end_date, is_current) as ISO-ish strings "YYYY-MM" or None.
    """
    m = _DATE_RANGE.search(text)
    if not m:
        return None, None, False

    start_raw = m.group(1)
    end_raw = m.group(2)

    start = _parse_date_str(start_raw)
    is_current = end_raw.strip().lower() in ("present", "current", "now")
    end = None if is_current else _parse_date_str(end_raw)

    return start, end, is_current


def _parse_date_str(raw: str) -> Optional[str]:
    """Parse a date string like 'Jan 2020' or '2020' into 'YYYY-MM' format."""
    raw = raw.strip()
    if not raw:
        return None

    # Year only
    m = re.match(r"^(\d{4})$", raw)
    if m:
        return f"{m.group(1)}-01"

    try:
        dt = dateutil_parser.parse(raw, default=datetime(2000, 1, 1))
        return f"{dt.year:04d}-{dt.month:02d}"
    except Exception:
        return None


def _calc_duration(start: Optional[str], end: Optional[str], is_current: bool) -> Optional[int]:
    """Calculate duration in months between two 'YYYY-MM' strings."""
    if not start:
        return None

    try:
        sy, sm = map(int, start.split("-"))
        if is_current:
            now = datetime.now()
            ey, em = now.year, now.month
        elif end:
            ey, em = map(int, end.split("-"))
        else:
            return None
        return (ey - sy) * 12 + (em - sm)
    except Exception:
        return None


def _extract_title_company(lines: list[str], block: str) -> tuple[Optional[str], Optional[str]]:
    """
    Heuristic: In most resumes, the job title and company appear in the first 2 lines.
    Common patterns:
        Line 1: "Software Engineer at Google"
        Line 1: "Software Engineer"  Line 2: "Google"
        Line 1: "Google | Software Engineer"
    """
    title = None
    company = None

    if not lines:
        return None, None

    # Pattern: "Title at Company" or "Title @ Company"
    for line in lines[:3]:
        m = re.match(r"^(.+?)\s+(?:at|@|–|-|—)\s+(.+)$", line, re.IGNORECASE)
        if m:
            candidate_title = m.group(1).strip()
            candidate_company = m.group(2).strip()
            # Sanity: title shouldn't be super long
            if len(candidate_title) < 80 and len(candidate_company) < 80:
                title = candidate_title
                company = candidate_company
                return title, company

        # Pattern: "Company | Title" or "Company — Title"
        m2 = re.match(r"^(.+?)\s*[|]\s*(.+)$", line)
        if m2:
            part1, part2 = m2.group(1).strip(), m2.group(2).strip()
            # Heuristic: title usually contains job-related words
            if _looks_like_title(part2):
                company = part1
                title = part2
            elif _looks_like_title(part1):
                title = part1
                company = part2
            if title or company:
                return title, company

    # Fallback: first two lines are title / company (in order)
    if len(lines) >= 2:
        if _looks_like_title(lines[0]):
            title = lines[0]
            if not _looks_like_date(lines[1]):
                company = lines[1]
        elif not _looks_like_date(lines[0]):
            company = lines[0]
            if len(lines) >= 2 and _looks_like_title(lines[1]):
                title = lines[1]

    return title, company


def _looks_like_title(s: str) -> bool:
    """Heuristic: does this string look like a job title?"""
    title_keywords = {
        "engineer", "developer", "manager", "analyst", "designer", "consultant",
        "specialist", "lead", "intern", "architect", "scientist", "researcher",
        "officer", "director", "coordinator", "executive", "head", "staff",
        "associate", "principal", "vice", "president", "founder", "co-founder"
    }
    s_lower = s.lower()
    return any(kw in s_lower for kw in title_keywords) and len(s) < 80


def _looks_like_date(s: str) -> bool:
    """Does this string look like a date?"""
    return bool(_DATE_RANGE.search(s) or _YEAR_ONLY.search(s))


def _extract_bullets(block: str) -> list[str]:
    """Extract bullet point lines from a block."""
    bullets = []
    for line in block.split("\n"):
        stripped = line.strip()
        if _BULLET.match(line):
            bullet_text = _BULLET.sub("", line).strip()
            if bullet_text and len(bullet_text) > 10:
                bullets.append(bullet_text)
        elif stripped and len(stripped) > 30 and stripped[0].islower():
            # Unnumbered continuation lines that are clearly sentences
            if bullets:  # Append as continuation
                bullets[-1] += " " + stripped
    return bullets


# ─── Derived field computation ─────────────────────────────────────────────────

def _compute_derived(entries: list[dict]) -> dict:
    """Compute total experience, gaps, and career progression across all entries."""
    if not entries:
        return _empty_derived()

    total_months = 0
    dated_entries = []

    for e in entries:
        if e.get("durationMonths"):
            total_months += e["durationMonths"]
        if e.get("startDate"):
            dated_entries.append(e)

    # Sort by start date
    dated_entries.sort(key=lambda e: e.get("startDate") or "")

    # Employment gaps
    gaps = []
    for i in range(1, len(dated_entries)):
        prev_end = dated_entries[i - 1].get("endDate")
        curr_start = dated_entries[i].get("startDate")
        if prev_end and curr_start and not dated_entries[i - 1].get("isCurrent"):
            gap_months = _month_diff(prev_end, curr_start)
            if gap_months >= 2:  # Only flag gaps >= 2 months
                gaps.append({
                    "from": prev_end,
                    "to": curr_start,
                    "months": gap_months
                })

    # Career progression heuristic
    progression = _detect_progression(entries)

    return {
        "totalYearsExperience": round(total_months / 12, 1) if total_months else None,
        "totalMonthsExperience": total_months or None,
        "employmentGaps": gaps,
        "careerProgression": progression
    }


def _month_diff(date1: str, date2: str) -> int:
    """Months between two 'YYYY-MM' strings."""
    try:
        y1, m1 = map(int, date1.split("-"))
        y2, m2 = map(int, date2.split("-"))
        return (y2 - y1) * 12 + (m2 - m1)
    except Exception:
        return 0


def _detect_progression(entries: list[dict]) -> str:
    """
    Heuristic: ascending if later titles contain senior keywords,
    lateral if titles are similar seniority, descending otherwise.
    """
    if not entries or len(entries) < 2:
        return "unknown"

    titles = [e.get("title", "").lower() for e in entries if e.get("title")]
    if not titles:
        return "unknown"

    first_title = titles[0]
    last_title = titles[-1]

    first_is_senior = any(kw in first_title for kw in _SENIOR_TITLES)
    last_is_senior = any(kw in last_title for kw in _SENIOR_TITLES)
    first_is_junior = any(kw in first_title for kw in _JUNIOR_TITLES)

    if not first_is_senior and last_is_senior:
        return "ascending"
    elif first_is_senior and not last_is_senior:
        return "descending"
    elif first_is_junior and not last_is_senior:
        return "ascending"
    return "lateral"


def _empty_derived() -> dict:
    return {
        "totalYearsExperience": None,
        "totalMonthsExperience": None,
        "employmentGaps": [],
        "careerProgression": "unknown"
    }
