import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

SENIOR_TITLE_PATTERN = re.compile(
    r"\b(lead|senior|principal|head of|director|manager|chief)\b", re.IGNORECASE
)
DATE_RANGE_PATTERN = re.compile(
    r"(\w{3,9}\s+\d{4})\s*[-–—to]+\s*(\w{3,9}\s+\d{4}|present|current)",
    re.IGNORECASE,
)


def _parse_month_year(s: str) -> Optional[datetime]:
    s = s.strip()
    if s.lower() in ("present", "current"):
        return datetime.now()
    for fmt in ("%B %Y", "%b %Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def check_seniority_mismatch(titles: List[str], total_years_experience: float) -> Dict:
    """
    titles: list of role/title strings found in the resume
    total_years_experience: computed from actual real work-experience
                             date ranges (0 if resume has none, only projects)
    """
    # Bypass for students/entry-level candidates with 0 years of formal experience
    if total_years_experience == 0.0:
        return {
            "flagged_titles": [],
            "total_years_experience": total_years_experience,
            "seniority_mismatch": False,
            "penalty": 0.0,
        }

    flagged_titles = [t for t in titles if t and isinstance(t, str) and SENIOR_TITLE_PATTERN.search(t)]
    # Only mismatch if they have a small amount of formal experience (< 2 years) but claim senior corporate titles
    mismatch = bool(flagged_titles) and (0.1 <= total_years_experience < 2.0)

    return {
        "flagged_titles": flagged_titles,
        "total_years_experience": total_years_experience,
        "seniority_mismatch": mismatch,
        "penalty": 0.3 if mismatch else 0.0,
    }


def check_date_gaps(date_ranges: List[str], gap_threshold_months: int = 6) -> Dict:
    """
    date_ranges: list of strings like "Jan 2023 - May 2023"
    Flags gaps longer than gap_threshold_months between consecutive ranges.
    """
    parsed: List[Tuple[datetime, datetime]] = []
    for r in date_ranges:
        m = DATE_RANGE_PATTERN.search(r)
        if not m:
            continue
        start = _parse_month_year(m.group(1))
        end = _parse_month_year(m.group(2))
        if start and end:
            parsed.append((start, end))

    parsed.sort(key=lambda pair: pair[0])
    gaps = []
    for i in range(1, len(parsed)):
        prev_end = parsed[i - 1][1]
        curr_start = parsed[i][0]
        gap_months = (curr_start.year - prev_end.year) * 12 + (curr_start.month - prev_end.month)
        if gap_months >= gap_threshold_months:
            gaps.append({"gap_months": gap_months, "between": [parsed[i - 1], parsed[i]]})

    return {
        "gaps_found": len(gaps),
        "gap_details": gaps,
        "penalty": min(len(gaps) * 0.1, 0.3),
    }
