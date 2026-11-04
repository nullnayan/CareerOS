"""
Whitespace / line-gap checker.

Needs position data, not just extracted text — so this expects
character/line objects with a "top" (y-position) attribute, which is
exactly what pdfplumber gives you via page.chars or page.extract_text_lines().

Usage with pdfplumber:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        lines = []
        for page in pdf.pages:
            lines.extend(page.extract_text_lines())
        result = check_line_gaps(lines)
"""

import statistics
from typing import Dict, List


def check_line_gaps(lines: List[Dict], large_gap_multiplier: float = 2.5) -> Dict:
    """
    lines: list of dicts, each with at least a "top" key (y-position
           of the line, as returned by pdfplumber's extract_text_lines())
    large_gap_multiplier: a gap is flagged if it's this many times
           larger than the median line-to-line gap in the document

    Returns flagged gap locations and a formatting penalty.
    """
    if len(lines) < 3:
        return {"flagged_gaps": [], "median_gap": 0, "penalty": 0.0}

    sorted_lines = sorted(lines, key=lambda l: l["top"])
    gaps = []
    for i in range(1, len(sorted_lines)):
        gap = sorted_lines[i]["top"] - sorted_lines[i - 1]["top"]
        gaps.append(gap)

    median_gap = statistics.median(gaps)
    threshold = median_gap * large_gap_multiplier

    flagged = []
    for i, gap in enumerate(gaps):
        if gap > threshold:
            flagged.append({
                "gap_size": round(gap, 1),
                "after_line_index": i,
                "before_text": sorted_lines[i].get("text", "")[:60],
                "after_text": sorted_lines[i + 1].get("text", "")[:60],
            })

    penalty = min(len(flagged) * 0.07, 0.3)

    return {
        "flagged_gaps": flagged,
        "median_gap": round(median_gap, 1),
        "flagged_count": len(flagged),
        "penalty": round(penalty, 3),
    }
