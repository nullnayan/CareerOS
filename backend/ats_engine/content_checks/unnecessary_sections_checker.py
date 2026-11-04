"""
Unnecessary sections checker.

Flags sections that are either outdated conventions or add no ATS/
recruiter value, and are commonly recommended for removal.
"""

import re
from typing import Dict, List

UNNECESSARY_SECTIONS = {
    "references": re.compile(r"references\s+available\s+upon\s+request", re.IGNORECASE),
    "objective_statement": re.compile(r"^\s*objective\s*:?\s*$", re.IGNORECASE | re.MULTILINE),
    "hobbies_interests": re.compile(r"^\s*(hobbies|interests)\s*:?\s*$", re.IGNORECASE | re.MULTILINE),
    "declaration": re.compile(r"^\s*declaration\s*:?\s*$", re.IGNORECASE | re.MULTILINE),
    "personal_details_excess": re.compile(
        r"(marital\s+status|father'?s\s+name|religion|nationality)", re.IGNORECASE
    ),
}


def check_unnecessary_sections(resume_text: str, section_headers: List[str] = None) -> Dict:
    """
    resume_text: full extracted text
    section_headers: optional list of detected section header strings,
                      if your section_detector.py already extracts these
                      (more reliable than regex-scanning the whole text)
    """
    flagged = []

    for name, pattern in UNNECESSARY_SECTIONS.items():
        if pattern.search(resume_text):
            flagged.append(name)

    if section_headers:
        for header in section_headers:
            h_lower = header.strip().lower()
            if h_lower in ("objective", "hobbies", "interests", "declaration", "references"):
                if header not in flagged:
                    flagged.append(f"section_header:{header}")

    penalty = min(len(flagged) * 0.05, 0.2)

    return {
        "flagged_sections": flagged,
        "penalty": round(penalty, 3),
    }
