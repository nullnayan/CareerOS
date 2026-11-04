"""
profile.py — Seniority band computation.

Phase 2 fix: replace max(declared, inferred) with bounded reconciliation.
- Users can declare DOWN (career changers, returnees)
- Drift beyond ±1 band attaches an informational finding
- Career-changers with 10 yrs in another field CAN be scored entry-level
"""
import datetime
from .models import ResumeDoc, Seniority, CandidateProfile

def _parse_date(date_str: str) -> datetime.date | None:
    if not date_str:
        return None
    date_str = date_str.lower().strip()
    if date_str in ["present", "current", "now"]:
        return datetime.date.today()
    try:
        if len(date_str) >= 7 and date_str[4] == '-':
            return datetime.date(int(date_str[:4]), int(date_str[5:7]), 1)
        if len(date_str) == 4:
            return datetime.date(int(date_str), 1, 1)
    except ValueError:
        pass
    return None


def compute_years_experience(doc: ResumeDoc) -> float:
    """Calculates total years of formal experience from dated roles (merges overlaps)."""
    intervals = []

    for exp in doc.experience:
        start = _parse_date(exp.start_date)
        end = _parse_date(exp.end_date)

        if start:
            if not end and exp.is_current:
                end = datetime.date.today()
            if not end:
                # Undated partial role: credit 6 months
                end = datetime.date(start.year + (start.month + 5) // 12,
                                    (start.month + 5) % 12 + 1, 1)
            if end < start:
                continue
            intervals.append((start, end))

    if not intervals:
        return 0.0

    # Merge overlapping intervals
    intervals.sort()
    merged = [intervals[0]]
    for curr_start, curr_end in intervals[1:]:
        prev_start, prev_end = merged[-1]
        if curr_start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, curr_end))
        else:
            merged.append((curr_start, curr_end))

    total_days = sum((end - start).days for start, end in merged)
    return round(total_days / 365.25, 2)


BAND_ORDER: dict[str, int] = {
    "student": 0, "entry": 1, "mid": 2, "senior": 3, "exec": 4
}
_ORDER_TO_BAND: dict[int, str] = {v: k for k, v in BAND_ORDER.items()}


def band_from_parsed_dates(years: float) -> Seniority:
    if years < 1.0:
        return "student"
    if years < 4.0:
        return "entry"
    if years < 8.0:
        return "mid"
    if years < 15.0:
        return "senior"
    return "exec"


def get_effective_band(
    declared_band: str | None,
    years_experience: float,
) -> Seniority:
    """
    Bounded reconciliation (Phase 2):
    - If no declaration, use inferred band from dates.
    - Declared band is honoured freely within ±1 level of inferred.
    - Beyond ±1 level: honour declaration but attach a finding code so UI
      can show a caveat (e.g. "Scoring as entry-level — some checks may not apply").
    - Career-changers CAN declare down (e.g. exec with 12 yrs declares entry).
    """
    inferred = band_from_parsed_dates(years_experience)

    if not declared_band:
        return inferred

    declared_lower = declared_band.lower().strip()
    declared_val = BAND_ORDER.get(declared_lower, -1)
    if declared_val == -1:
        return inferred

    inferred_val = BAND_ORDER[inferred]
    drift = abs(declared_val - inferred_val)

    # Allow any drift — honour declaration; drift > 1 just adds a caveat tag
    # (the caller or API can read this via meta.band_drift)
    return _ORDER_TO_BAND.get(declared_val, inferred)


def get_band_drift(declared_band: str | None, years_experience: float) -> int:
    """
    Returns how many bands away the declaration is from the inferred band.
    0 = aligned, 1 = one level off (fine), 2+ = flagged.
    """
    if not declared_band:
        return 0
    inferred = band_from_parsed_dates(years_experience)
    declared_val = BAND_ORDER.get(declared_band.lower().strip(), -1)
    if declared_val == -1:
        return 0
    return abs(declared_val - BAND_ORDER[inferred])
