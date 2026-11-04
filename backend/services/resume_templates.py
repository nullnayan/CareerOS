"""
services/resume_templates.py
============================
V2 Template Registry — 6 visually distinct ATS-friendly resume templates.

All templates use pymupdf built-in fonts embedded via Archive so fonts
render identically in every environment without network access.

Font reality:
  - Serif  → Times-Roman / Times-Bold / Times-Italic  (renders as Nimbus Roman)
  - Sans   → Helvetica / Helvetica-Bold / Helvetica-Oblique (renders as Nimbus Sans)
These are genuinely different typefaces; the templates further differ by:
  heading style (underline / left-border / small-caps / none)
  name alignment (center / left)
  letter-spacing, section-gap, line-height
"""

from typing import Dict, List, Any
import pymupdf


# ─── Font archive builder ──────────────────────────────────────────────────────

def _make_font_archive(family_name: str, regular: str, bold: str, italic: str = None):
    """
    Builds a (css_string, pymupdf.Archive) pair using PyMuPDF built-in fonts.
    The CSS uses @font-face with local filenames; the Archive maps those filenames
    to the in-memory TTF buffers so pymupdf.Story can find them.
    """
    archive = pymupdf.Archive()

    reg_buf  = pymupdf.Font(regular).buffer
    bold_buf = pymupdf.Font(bold).buffer
    archive.add(reg_buf,  f"{family_name}-Regular.ttf")
    archive.add(bold_buf, f"{family_name}-Bold.ttf")

    css = (
        f"@font-face {{ font-family: '{family_name}'; "
        f"src: url('{family_name}-Regular.ttf'); "
        f"font-weight: normal; font-style: normal; }}\n"
        f"@font-face {{ font-family: '{family_name}'; "
        f"src: url('{family_name}-Bold.ttf'); "
        f"font-weight: bold; font-style: normal; }}\n"
    )

    if italic:
        ital_buf = pymupdf.Font(italic).buffer
        archive.add(ital_buf, f"{family_name}-Italic.ttf")
        css += (
            f"@font-face {{ font-family: '{family_name}'; "
            f"src: url('{family_name}-Italic.ttf'); "
            f"font-weight: normal; font-style: italic; }}\n"
        )

    return css, archive


# Build font packages once at module load
_SERIF_CSS,  _SERIF_ARCHIVE  = _make_font_archive("ResumeSerif", "Times-Roman",  "Times-Bold",       "Times-Italic")
_SANS_CSS,   _SANS_ARCHIVE   = _make_font_archive("ResumeSans",  "helv",          "Helvetica-Bold",   "Helvetica-Oblique")


# ─── Template Registry ─────────────────────────────────────────────────────────

TEMPLATES: Dict[str, Dict[str, Any]] = {

    # ── Classic ────────────────────────────────────────────────────────────────
    # Jake's-LaTeX-inspired. Dense, serif, thin underline heading.
    # Best for: students, new grads, CS/engineering.
    "classic": {
        "id": "classic",
        "name": "Classic",
        "description": "Traditional serif — students, freshers, CS & engineering.",
        "best_for": "Students, new grads, CS/engineering",
        "font_family": "'ResumeSerif', Times, serif",
        "font_face_css": _SERIF_CSS,
        "archive": _SERIF_ARCHIVE,
        "default_font_id": "times_new_roman",

        "name_align": "center",
        "name_letterspacing": "0pt",

        # heading_style drives _heading_css():
        #   bold_underline | accent_left_border | bold_plain | smallcaps_thick_border | plain_line
        "heading_style": "bold_underline",
        "heading_case": "none",          # none | upper | smallcaps (CSS-only)

        "sizes": {
            "name":    20.0,
            "contact":  9.5,
            "heading": 11.5,
            "body":    10.0,
            "meta":     9.5,
        },
        "spacing": {
            "margin_pt":      46.0,
            "line_height":     1.15,
            "section_gap_pt": 10.0,
            "bullet_indent":  14.0,
        },
        "colors": {
            "body":    "#000000",
            "muted":   "#444444",
            "heading": "#000000",
        },

        # Section order for freshers (education & projects lead)
        "section_order": ["summary", "education", "projects", "experience", "skills", "certifications"],

        # Page-fitting ceilings for _expand_to_fill_page
        "fit_overrides": {
            "gap_ceiling":  16.0,
            "lh_ceiling":   1.30,
            "font_ceiling": 10.8,
        },
    },

    # ── Modern Tech ────────────────────────────────────────────────────────────
    # Sans-serif, left-aligned name, bold left-border heading, uppercase.
    # Best for: software / product / startup roles.
    "modern_tech": {
        "id": "modern_tech",
        "name": "Modern Tech",
        "description": "Clean sans-serif — tech, startup & product roles.",
        "best_for": "Software, product, startup roles",
        "font_family": "'ResumeSans', Helvetica, Arial, sans-serif",
        "font_face_css": _SANS_CSS,
        "archive": _SANS_ARCHIVE,
        "default_font_id": "calibri",

        "name_align": "left",
        "name_letterspacing": "0pt",

        "heading_style": "accent_left_border",
        "heading_case": "upper",

        "sizes": {
            "name":    22.0,
            "contact":  9.5,
            "heading": 11.0,
            "body":    10.0,
            "meta":     9.5,
        },
        "spacing": {
            "margin_pt":      40.0,
            "line_height":     1.20,
            "section_gap_pt": 12.0,
            "bullet_indent":  14.0,
        },
        "colors": {
            "body":    "#111111",
            "muted":   "#555555",
            "heading": "#000000",
        },

        # Skills-forward: recruiters scan for stack match first
        "section_order": ["summary", "skills", "experience", "projects", "education", "certifications"],

        "fit_overrides": {
            "gap_ceiling":  20.0,
            "lh_ceiling":   1.40,
            "font_ceiling": 11.0,
        },
    },

    # ── Minimal ────────────────────────────────────────────────────────────────
    # Sans-serif, no borders, wide letter-spacing, high whitespace.
    # Best for: design-adjacent, product managers, mid-career.
    "minimal": {
        "id": "minimal",
        "name": "Minimal",
        "description": "Ultra-clean whitespace — design, product & mid-career.",
        "best_for": "Design, product management, mid-career",
        "font_family": "'ResumeSans', Helvetica, Arial, sans-serif",
        "font_face_css": _SANS_CSS,
        "archive": _SANS_ARCHIVE,
        "default_font_id": "arial",

        "name_align": "left",
        "name_letterspacing": "1.5pt",

        "heading_style": "bold_plain",
        "heading_case": "upper",

        "sizes": {
            "name":    20.0,
            "contact":  9.5,
            "heading": 11.0,
            "body":    10.0,
            "meta":     9.5,
        },
        "spacing": {
            "margin_pt":      50.0,
            "line_height":     1.30,
            "section_gap_pt": 16.0,
            "bullet_indent":  16.0,
        },
        "colors": {
            "body":    "#222222",
            "muted":   "#777777",
            "heading": "#000000",
        },

        "section_order": ["summary", "experience", "education", "projects", "skills", "certifications"],

        "fit_overrides": {
            "gap_ceiling":  24.0,
            "lh_ceiling":   1.45,
            "font_ceiling": 11.2,
        },
    },

    # ── Professional ───────────────────────────────────────────────────────────
    # Serif, small-caps headings with thick underline, centered name.
    # Best for: finance, consulting, senior/executive roles.
    "professional": {
        "id": "professional",
        "name": "Professional",
        "description": "Executive serif — finance, consulting & senior roles.",
        "best_for": "Finance, consulting, senior/executive",
        "font_family": "'ResumeSerif', Times, serif",
        "font_face_css": _SERIF_CSS,
        "archive": _SERIF_ARCHIVE,
        "default_font_id": "georgia",

        "name_align": "center",
        "name_letterspacing": "0.5pt",

        "heading_style": "smallcaps_thick_border",
        "heading_case": "smallcaps",

        "sizes": {
            "name":    22.0,
            "contact":  9.5,
            "heading": 12.0,
            "body":    10.5,
            "meta":     9.5,
        },
        "spacing": {
            "margin_pt":      42.0,
            "line_height":     1.20,
            "section_gap_pt": 12.0,
            "bullet_indent":  14.0,
        },
        "colors": {
            "body":    "#111111",
            "muted":   "#555555",
            "heading": "#000000",
        },

        # Experience-first: seniority is the selling point
        "section_order": ["summary", "experience", "skills", "education", "projects", "certifications"],

        "fit_overrides": {
            "gap_ceiling":  20.0,
            "lh_ceiling":   1.35,
            "font_ceiling": 11.0,
        },
    },

    # ── ATS Safe ───────────────────────────────────────────────────────────────
    # Zero decoration. Plain bold headings + thin line, no colour, system fonts.
    # Best for: bulk applications, large enterprises, older ATS (Taleo/iCIMS).
    "ats_safe": {
        "id": "ats_safe",
        "name": "ATS Safe",
        "description": "Zero-decoration plain — maximum ATS compatibility.",
        "best_for": "Bulk applications, enterprise ATS, Taleo/iCIMS",
        "font_family": "'ResumeSans', Helvetica, Arial, sans-serif",
        "font_face_css": _SANS_CSS,
        "archive": _SANS_ARCHIVE,
        "default_font_id": "tahoma",

        "name_align": "left",
        "name_letterspacing": "0pt",

        "heading_style": "plain_line",
        "heading_case": "none",

        "sizes": {
            "name":    19.0,
            "contact":  9.5,
            "heading": 11.0,
            "body":    10.0,
            "meta":     9.5,
        },
        "spacing": {
            "margin_pt":      44.0,
            "line_height":     1.15,
            "section_gap_pt":  8.0,
            "bullet_indent":  14.0,
        },
        "colors": {
            "body":    "#000000",
            "muted":   "#333333",
            "heading": "#000000",
        },

        # Most ATS-parser-friendly conventional order
        "section_order": ["summary", "skills", "experience", "education", "certifications", "projects"],

        "fit_overrides": {
            "gap_ceiling":  18.0,
            "lh_ceiling":   1.30,
            "font_ceiling": 11.0,
        },
    },

    # ── Academic ───────────────────────────────────────────────────────────────
    # Traditional serif CV style. Education leads. No decoration beyond underline.
    # Best for: research roles, grad school, PhD/postdoc, academic-adjacent tech.
    "academic": {
        "id": "academic",
        "name": "Academic",
        "description": "Traditional CV serif — research, grad school & academia.",
        "best_for": "Research, grad school, PhD/postdoc",
        "font_family": "'ResumeSerif', Times, serif",
        "font_face_css": _SERIF_CSS,
        "archive": _SERIF_ARCHIVE,
        "default_font_id": "cambria",

        "name_align": "center",
        "name_letterspacing": "0pt",

        "heading_style": "bold_underline",
        "heading_case": "none",

        "sizes": {
            "name":    19.0,
            "contact":  9.5,
            "heading": 11.5,
            "body":    10.0,
            "meta":     9.5,
        },
        "spacing": {
            "margin_pt":      46.0,
            "line_height":     1.20,
            "section_gap_pt": 10.0,
            "bullet_indent":  14.0,
        },
        "colors": {
            "body":    "#000000",
            "muted":   "#3a3a3a",
            "heading": "#000000",
        },

        # Education always leads in academic CVs
        "section_order": ["summary", "education", "experience", "projects", "skills", "certifications"],

        "fit_overrides": {
            "gap_ceiling":  16.0,
            "lh_ceiling":   1.30,
            "font_ceiling": 10.8,
        },
    },
}


# ─── Public API ────────────────────────────────────────────────────────────────

def get_template(template_id: str, font_id: str = None) -> Dict[str, Any]:
    """
    Return template config by ID, falling back to 'classic' if unknown.
    If font_id is provided (and valid), overrides the template's default font
    with the requested font package from font_registry.
    """
    import copy
    from services.font_registry import get_font_package, is_valid_font_id, DEFAULT_FONT_ID

    template = copy.copy(TEMPLATES.get(template_id, TEMPLATES["classic"]))

    # Determine which font to use
    effective_font_id = font_id if (font_id and is_valid_font_id(font_id)) else template.get("default_font_id", DEFAULT_FONT_ID)

    # Load font package and override the template's font fields
    font_face_css, archive, css_family = get_font_package(effective_font_id)
    template["font_face_css"] = font_face_css
    template["archive"]       = archive
    template["font_family"]   = css_family

    return template


def list_templates() -> List[Dict[str, Any]]:
    """Return metadata list for the frontend template picker."""
    return [
        {
            "id":             t["id"],
            "name":           t["name"],
            "description":    t["description"],
            "best_for":       t["best_for"],
            "font_family":    t["font_family"],
            "default_font_id": t.get("default_font_id", "times_new_roman"),
        }
        for t in TEMPLATES.values()
    ]


def get_default_section_order(template_id: str) -> List[str]:
    """Return the default section order for a given template."""
    return list(TEMPLATES.get(template_id, TEMPLATES["classic"])["section_order"])


def get_fit_overrides(template_id: str) -> Dict[str, float]:
    """Return page-fitting ceilings for _expand_to_fill_page."""
    return TEMPLATES.get(template_id, TEMPLATES["classic"])["fit_overrides"]
