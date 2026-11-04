"""
services/font_registry.py
=========================
Font Registry for CareerOS Resume Builder

Manages 8 professional resume fonts loaded from Windows system fonts.
Each font is loaded lazily and cached in-memory after first use.

Fonts available:
  Serif:      times_new_roman, georgia, cambria
  Sans-Serif: arial, calibri, verdana, tahoma, trebuchet_ms
"""

import os
import logging
from typing import Dict, Any, Optional, Tuple
import pymupdf

logger = logging.getLogger(__name__)

# ─── Font Definitions ─────────────────────────────────────────────────────────
# Maps font_id -> metadata + file paths on Windows
# On Linux/Mac, these paths would differ — future enhancement to bundle fonts.

FONT_DEFS: Dict[str, Dict[str, Any]] = {
    "times_new_roman": {
        "id":          "times_new_roman",
        "name":        "Times New Roman",
        "type":        "serif",
        "description": "Traditional serif — classic, formal, academic",
        "css_family":  "'TimesNewRoman', 'Times New Roman', Times, serif",
        "files": {
            "regular": "C:/Windows/Fonts/times.ttf",
            "bold":    "C:/Windows/Fonts/timesbd.ttf",
            "italic":  "C:/Windows/Fonts/timesi.ttf",
        },
    },
    "georgia": {
        "id":          "georgia",
        "name":        "Georgia",
        "type":        "serif",
        "description": "Warm readable serif — professional and approachable",
        "css_family":  "'Georgia', Georgia, serif",
        "files": {
            "regular": "C:/Windows/Fonts/georgia.ttf",
            "bold":    "C:/Windows/Fonts/georgiab.ttf",
            "italic":  "C:/Windows/Fonts/georgiai.ttf",
        },
    },
    "cambria": {
        "id":          "cambria",
        "name":        "Cambria",
        "type":        "serif",
        "description": "Modern crisp serif — excellent for print",
        "css_family":  "'Cambria', Cambria, 'Georgia', serif",
        "files": {
            "regular": "C:/Windows/Fonts/cambria.ttc",
            "bold":    "C:/Windows/Fonts/cambriab.ttf",
            "italic":  "C:/Windows/Fonts/cambriai.ttf",
        },
    },
    "arial": {
        "id":          "arial",
        "name":        "Arial",
        "type":        "sans-serif",
        "description": "Clean universal sans-serif — widely recognized",
        "css_family":  "'Arial', Arial, Helvetica, sans-serif",
        "files": {
            "regular": "C:/Windows/Fonts/arial.ttf",
            "bold":    "C:/Windows/Fonts/arialbd.ttf",
            "italic":  "C:/Windows/Fonts/ariali.ttf",
        },
    },
    "calibri": {
        "id":          "calibri",
        "name":        "Calibri",
        "type":        "sans-serif",
        "description": "Soft modern sans-serif — Microsoft default, professional",
        "css_family":  "'Calibri', Calibri, Arial, sans-serif",
        "files": {
            "regular": "C:/Windows/Fonts/calibri.ttf",
            "bold":    "C:/Windows/Fonts/calibrib.ttf",
            "italic":  "C:/Windows/Fonts/calibrii.ttf",
        },
    },
    "verdana": {
        "id":          "verdana",
        "name":        "Verdana",
        "type":        "sans-serif",
        "description": "Wide readable sans-serif — excellent clarity",
        "css_family":  "'Verdana', Verdana, Geneva, sans-serif",
        "files": {
            "regular": "C:/Windows/Fonts/verdana.ttf",
            "bold":    "C:/Windows/Fonts/verdanab.ttf",
            "italic":  "C:/Windows/Fonts/verdanai.ttf",
        },
    },
    "tahoma": {
        "id":          "tahoma",
        "name":        "Tahoma",
        "type":        "sans-serif",
        "description": "Compact clean sans-serif — great ATS compatibility",
        "css_family":  "'Tahoma', Tahoma, Geneva, sans-serif",
        "files": {
            "regular": "C:/Windows/Fonts/tahoma.ttf",
            "bold":    "C:/Windows/Fonts/tahomabd.ttf",
            "italic":  None,   # Tahoma has no italic variant
        },
    },
    "trebuchet_ms": {
        "id":          "trebuchet_ms",
        "name":        "Trebuchet MS",
        "type":        "sans-serif",
        "description": "Distinctive modern sans-serif — stands out subtly",
        "css_family":  "'TrebuchetMS', 'Trebuchet MS', Arial, sans-serif",
        "files": {
            "regular": "C:/Windows/Fonts/trebuc.ttf",
            "bold":    "C:/Windows/Fonts/trebucbd.ttf",
            "italic":  "C:/Windows/Fonts/trebucit.ttf",
        },
    },
}

# Default font when no font_id is specified
DEFAULT_FONT_ID = "times_new_roman"

# ─── In-memory cache ──────────────────────────────────────────────────────────
# Stores (css_string, pymupdf.Archive) per font_id after first load
_font_cache: Dict[str, Tuple[str, Any]] = {}


# ─── Font package builder ─────────────────────────────────────────────────────

def _build_font_package(font_def: Dict[str, Any]) -> Tuple[str, Any]:
    """
    Build a (css_string, pymupdf.Archive) pair for a given font definition.
    Equivalent to the old _make_font_archive() in resume_templates.py.
    """
    font_id    = font_def["id"]
    files      = font_def["files"]
    css_family = font_def["css_family"]
    # Use the font name as the CSS family name for @font-face
    # Derive a safe CSS name by removing spaces
    safe_name = font_def["name"].replace(" ", "")

    archive = pymupdf.Archive()
    css_parts = []

    # Regular
    reg_path = files.get("regular")
    if reg_path and os.path.exists(reg_path):
        reg_buf = pymupdf.Font(fontfile=reg_path).buffer
        archive.add(reg_buf, f"{safe_name}-Regular.ttf")
        css_parts.append(
            f"@font-face {{ font-family: '{safe_name}'; "
            f"src: url('{safe_name}-Regular.ttf'); "
            f"font-weight: normal; font-style: normal; }}"
        )
    else:
        logger.warning(f"Font {font_id}: regular file not found at {reg_path}")

    # Bold
    bold_path = files.get("bold")
    if bold_path and os.path.exists(bold_path):
        bold_buf = pymupdf.Font(fontfile=bold_path).buffer
        archive.add(bold_buf, f"{safe_name}-Bold.ttf")
        css_parts.append(
            f"@font-face {{ font-family: '{safe_name}'; "
            f"src: url('{safe_name}-Bold.ttf'); "
            f"font-weight: bold; font-style: normal; }}"
        )
    else:
        logger.warning(f"Font {font_id}: bold file not found at {bold_path}")

    # Italic (optional — Tahoma has none)
    ital_path = files.get("italic")
    if ital_path and os.path.exists(ital_path):
        ital_buf = pymupdf.Font(fontfile=ital_path).buffer
        archive.add(ital_buf, f"{safe_name}-Italic.ttf")
        css_parts.append(
            f"@font-face {{ font-family: '{safe_name}'; "
            f"src: url('{safe_name}-Italic.ttf'); "
            f"font-weight: normal; font-style: italic; }}"
        )

    css_string = "\n".join(css_parts)
    return css_string, archive


# ─── Public API ───────────────────────────────────────────────────────────────

def get_font_package(font_id: Optional[str] = None) -> Tuple[str, Any, str]:
    """
    Return (font_face_css, pymupdf.Archive, css_font_family) for the given font_id.
    Results are cached in-memory after first call.

    Falls back to DEFAULT_FONT_ID if the font_id is unknown.
    """
    fid = font_id if font_id in FONT_DEFS else DEFAULT_FONT_ID

    if fid not in _font_cache:
        font_def = FONT_DEFS[fid]
        css, archive = _build_font_package(font_def)
        css_family   = f"'{font_def['name'].replace(' ', '')}', {font_def['css_family']}"
        _font_cache[fid] = (css, archive, css_family)
        logger.info(f"Font package built and cached: {fid}")

    return _font_cache[fid]


def list_fonts() -> list:
    """Return font metadata list for the frontend font picker."""
    return [
        {
            "id":          f["id"],
            "name":        f["name"],
            "type":        f["type"],
            "description": f["description"],
        }
        for f in FONT_DEFS.values()
    ]


def is_valid_font_id(font_id: str) -> bool:
    """Check if a font_id is known."""
    return font_id in FONT_DEFS
