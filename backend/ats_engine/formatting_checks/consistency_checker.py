"""
Formatting consistency checker.

Catches the "copy-paste residue" pattern: a resume built by
combining content from different templates/sources ends up with
mixed bullet styles, mixed date formats, or a stray font size —
all signs of a document that will parse inconsistently.
"""

import re
from collections import Counter
from typing import Dict, List, Optional

BULLET_CHARS = ["•", "-", "*", "▪", "◦", "‣", "○"]

DATE_FORMAT_PATTERNS = {
    "month_year_full": re.compile(r"\b[A-Z][a-z]{2,8}\s+\d{4}\b"),      # "January 2023"
    "month_year_abbr": re.compile(r"\b[A-Z][a-z]{2}\s+\d{4}\b"),         # "Jan 2023"
    "numeric_slash": re.compile(r"\b\d{1,2}/\d{4}\b"),                   # "01/2023"
    "numeric_dash": re.compile(r"\b\d{1,2}-\d{4}\b"),                    # "01-2023"
}


def check_bullet_consistency(bullet_lines: List[str]) -> Dict:
    """
    bullet_lines: raw lines that start with a bullet character
    """
    found_chars = Counter()
    for line in bullet_lines:
        stripped = line.strip()
        for ch in BULLET_CHARS:
            if stripped.startswith(ch):
                found_chars[ch] += 1
                break

    distinct_bullets_used = len(found_chars)
    penalty = 0.1 if distinct_bullets_used > 1 else 0.0

    return {
        "bullet_chars_found": dict(found_chars),
        "distinct_styles": distinct_bullets_used,
        "penalty": penalty,
    }


def check_date_format_consistency(resume_text: str) -> Dict:
    format_counts = {
        name: len(pattern.findall(resume_text))
        for name, pattern in DATE_FORMAT_PATTERNS.items()
    }
    formats_used = [name for name, count in format_counts.items() if count > 0]
    penalty = 0.1 if len(formats_used) > 1 else 0.0

    return {
        "format_counts": format_counts,
        "formats_used": formats_used,
        "penalty": penalty,
    }


def check_font_size_consistency(char_sizes_by_section: Dict[str, List[float]]) -> Dict:
    """
    char_sizes_by_section: dict like {"experience": [10.0, 10.0, 14.0, 10.0], ...}
    (font sizes of each character/line in a section — pdfplumber's
    page.chars gives you a "size" field per character)

    Flags a section if it contains a size that deviates from that
    section's own dominant size — catches stray copy-paste font sizes.
    """
    flagged_sections = {}
    for section, sizes in char_sizes_by_section.items():
        if not sizes:
            continue
        dominant = Counter(round(s, 1) for s in sizes).most_common(1)[0][0]
        outliers = [s for s in sizes if abs(s - dominant) > 0.5]
        if outliers:
            flagged_sections[section] = {
                "dominant_size": dominant,
                "outlier_count": len(outliers),
            }

    penalty = min(len(flagged_sections) * 0.05, 0.15)
    return {"flagged_sections": flagged_sections, "penalty": penalty}


def combined_consistency_score(
    bullet_lines: List[str],
    resume_text: str,
    char_sizes_by_section: Optional[Dict[str, List[float]]] = None,
) -> Dict:
    bullet_result = check_bullet_consistency(bullet_lines)
    date_result = check_date_format_consistency(resume_text)
    font_result = check_font_size_consistency(char_sizes_by_section or {})

    total_penalty = min(
        bullet_result["penalty"] + date_result["penalty"] + font_result["penalty"], 0.35
    )
    score = round(1.0 - total_penalty, 3)

    return {
        "score": score,  # feed into formatting_parsability bucket
        "bullet_check": bullet_result,
        "date_format_check": date_result,
        "font_check": font_result,
    }
