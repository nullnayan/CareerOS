"""
Resume Parser — Main Pipeline Orchestrator
==========================================
Wires all modules together in dependency order:

  1. extractor.py       → raw text + layout metadata
  2. segmenter.py       → section text buckets
  3. parsers/
       contact_parser    → name, email, phone, links, location
       education_parser  → education entries
       skills_parser     → categorized skills
       experience_parser → experience entries + derived metrics
       extras_parser     → certifications, languages, achievements
  4. normalizer.py      → cleans/deduplicates/standardizes all fields
  5. quality_scorer.py  → completeness + quality metrics
  6. coverage_diff.py   → calculates text coverage and audits unparsed content

Final output schema (returned from parse_resume()):
{
  "contact": { ... },
  "summary": "...",
  "experience": { "entries": [...], "_derived": {...} },
  "education": [...],
  "skills": { "all": [...], "byCategory": {...} },
  "certifications": [...],
  "languages": [...],
  "achievements": [...],
  "projects": "...",
  "interests": "...",
  "unknown_sections": {...},
  "failed_sections": [...],
  "section_order": [...],
  "metadata": {
    "pageCount": 2,
    "fileType": "pdf",
    "hasColumns": False,
    "hasTables": False,
    "isScannedPdf": False,
    "wordCount": 450,
    "charCount": 2800,
    "parserVersion": "1.0.0"
  },
  "_raw": "..."   ← only included if include_raw=True
}
"""

from resume_parser import extractor
from resume_parser import segmenter
from resume_parser import normalizer
from resume_parser import quality_scorer
from resume_parser import coverage_diff
from resume_parser.parsers import (
    contact_parser,
    education_parser,
    skills_parser,
    experience_parser,
    extras_parser,
)


def parse_resume(file_bytes: bytes, filename: str, include_raw: bool = False) -> dict:
    """
    Main entry point. Takes raw file bytes and filename.
    Returns structured resume data.

    Args:
        file_bytes:  Raw file content as bytes
        filename:    Original filename (used to detect file type)
        include_raw: If True, includes the raw extracted text in output

    Raises:
        ValueError: For unsupported file types
    """

    # ── Phase 1: Text Extraction (with column-aware routing) ──────────────────
    extraction = extractor.extract(file_bytes, filename)
    raw_text = extraction["rawText"]
    metadata = extraction["metadata"]

    # ── Phase 2: Section Segmentation ─────────────────────────────────────────
    sections = segmenter.segment(raw_text)

    # Convenience accessor — returns "" if section missing
    def sec(key: str) -> str:
        return sections.get(key, "") or ""

    # ── Experience reconstruction fallback ────────────────────────────────────
    # Some resumes have company/title lines that look like headings, causing the
    # segmenter to classify them as unknown_sections. When experience is empty,
    # pull those unknown blocks that fall between experience and education.
    experience_text = sec("experience")
    if not experience_text.strip():
        experience_text = _reconstruct_experience_from_unknowns(sections)

    # ── Phase 3: Entity Parsing ────────────────────────────────────────────────

    # Contact (uses dedicated section + top of raw text as fallback)
    contact = contact_parser.parse(
        sec("contact"), 
        raw_text, 
        extracted_links=extraction.get("extracted_links", [])
    )

    # Education
    education = education_parser.parse(sec("education"))

    # Skills (also scans experience + projects for skill mentions)
    skills = skills_parser.parse(
        sec("skills"),
        supplemental_texts=[sec("experience"), sec("projects")]
    )

    # Experience (hardest — built last, parses after simpler parsers are stable)
    experience = experience_parser.parse(experience_text)

    # Certifications, Languages, Achievements
    certifications = extras_parser.parse_certifications(sec("certifications"))
    languages = extras_parser.parse_languages(sec("languages"))
    achievements = extras_parser.parse_achievements(sec("achievements"))

    # ── Assemble final output ──────────────────────────────────────────────────
    output = {
        "contact": contact,
        "summary": sec("summary").strip() or None,
        "experience": experience,
        "education": education,
        "skills": skills,
        "certifications": certifications,
        "languages": languages,
        "achievements": achievements,
        "projects": sec("projects").strip() or None,
        "volunteer": sec("volunteer").strip() or None,
        "interests": sec("interests").strip() or None,
        "references": sec("references").strip() or None,
        "publications": sec("publications").strip() or None,
        "unknown_sections": sections.get("unknown_sections", {}),
        "failed_sections": sections.get("failed_sections", []),
        "section_order": sections.get("section_order", []),
        "original_section_headings": sections.get("original_section_headings", {}),
        "metadata": metadata,
    }

    if include_raw:
        output["_raw"] = raw_text
        output["_pages"] = extraction.get("pages", [])

    # ── Phase 4: Normalize all fields ─────────────────────────────────────────
    output = normalizer.normalize(output)

    # ── Phase 5: Quality scoring ───────────────────────────────────────────────
    output["quality"] = quality_scorer.score(output)

    # ── Phase 6: Coverage Audit (Text subtraction + AI classification) ────────
    missed_info, coverage_ratio = coverage_diff.audit_coverage(raw_text, output)
    output["metadata"]["coverageRatio"] = coverage_ratio
    output["unparsedContent"] = missed_info

    # If any valuable missed info is found, inject a flag warning
    if missed_info:
        if "flags" not in output["quality"]:
            output["quality"]["flags"] = []
        output["quality"]["flags"].append({
            "type": "warning",
            "field": "unparsedContent",
            "message": f"We detected {len(missed_info)} unparsed section(s) containing potentially valuable details (e.g., {', '.join(set(item['suspected_category'] for item in missed_info if item.get('suspected_category')))}). Please review."
        })

    return output


def _reconstruct_experience_from_unknowns(sections: dict) -> str:
    """
    Fallback: when the experience section text is empty because the parser
    misclassified job title/company lines as unknown headings, reconstruct
    experience content by concatenating the unknown_sections blocks that
    appear between 'experience' and the next known major section.
    """
    order = sections.get("section_order", [])
    unknown = sections.get("unknown_sections", {})

    # Major section boundaries after which experience blocks stop
    STOP_SECTIONS = {"education", "skills", "certifications", "languages",
                     "achievements", "publications", "volunteer", "interests", "references"}

    collecting = False
    parts = []

    for item in order:
        if item == "experience":
            collecting = True
            exp_content = sections.get("experience", "")
            if exp_content:
                parts.append(exp_content)
            continue

        if collecting:
            if item in STOP_SECTIONS:
                break  # Reached next major section

            if item.startswith("unknown:"):
                heading = item[len("unknown:"):]
                content = unknown.get(heading, "")
                # Reconstruct: heading + its content as a single block
                block = heading + "\n" + content if content else heading
                parts.append(block)

    return "\n\n".join(parts)
