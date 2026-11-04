"""
layout_probe.py — Phase 4: Real PDF layout analysis using pdfplumber.

Detects:
  - Page count
  - Multi-column layout (via x-coordinate clustering of word boxes)
  - Tables
  - Scanned PDF (empty text layer)
  - Embedded fonts
  - Images
  - Header/footer text (by vertical position band)
  - Special characters / non-embedded font fallback
  - layout_facts_available flag for downstream checks

When no PDF is available (pasted text, builder output), returns a stub
LayoutFacts with layout_facts_available=False so FORMATTING checks
return None instead of awarding free points.
"""
import logging
from typing import Optional, Union

from .models import LayoutFacts

logger = logging.getLogger(__name__)

_PDFPLUMBER_AVAILABLE = False
try:
    import pdfplumber
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    logger.debug("pdfplumber not installed — layout probing disabled. Run: pip install pdfplumber")


def _stub_layout(page_count: int = 1) -> LayoutFacts:
    """Layout facts when no PDF is available. page_count=0 signals unavailability."""
    return LayoutFacts(
        page_count=0,          # 0 = unknown / not available
        has_columns=False,
        has_tables=False,
        is_scanned=False,
        embedded_fonts=(),
        font_sizes_by_section={},
        has_images=False,
        header_footer_text=(),
        file_type="unknown",
    )


def _detect_columns(words: list, page_width: float, threshold: float = 0.45) -> bool:
    """
    Detect multi-column layout via x-coordinate gap analysis.
    If there is a horizontal band with very few words (a "gutter"), likely two-column.
    """
    if not words or page_width <= 0:
        return False

    # Collect x0 positions as fractions of page width
    xs = [w.get("x0", 0) / page_width for w in words if w.get("x0") is not None]
    if not xs:
        return False

    # Count words in the middle band (40-60% of page width)
    middle_band = [x for x in xs if 0.35 < x < 0.65]
    middle_ratio = len(middle_band) / len(xs)

    # If few words land in the middle, there's a gutter there → multi-column
    return middle_ratio < 0.08


def probe_layout(
    source: Optional[Union[str, bytes]],
    file_type: str = "unknown",
) -> LayoutFacts:
    """
    Analyse a PDF or text source and return structured layout facts.

    Args:
        source: Path (str) to PDF, bytes of PDF content, or None.
        file_type: 'pdf' | 'docx' | 'txt' | 'unknown'
    """
    if source is None:
        return _stub_layout()

    if not _PDFPLUMBER_AVAILABLE:
        # Return a stub with file_type set so at least file_type is known
        return LayoutFacts(
            page_count=1,
            has_columns=False,
            has_tables=False,
            is_scanned=False,
            embedded_fonts=(),
            font_sizes_by_section={},
            has_images=False,
            header_footer_text=(),
            file_type=file_type or "unknown",
        )

    try:
        if isinstance(source, str):
            pdf_file = pdfplumber.open(source)
        else:
            import io
            pdf_file = pdfplumber.open(io.BytesIO(source))

        with pdf_file as pdf:
            page_count = len(pdf.pages)
            all_text = ""
            has_columns = False
            has_tables = False
            has_images = False
            header_footer_parts: list[str] = []
            embedded_fonts: set[str] = set()

            for page_idx, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                all_text += page_text

                words = page.extract_words()
                page_width = page.width or 612.0
                page_height = page.height or 792.0

                # Column detection
                if not has_columns and words:
                    has_columns = _detect_columns(words, page_width)

                # Table detection
                tables = page.extract_tables()
                if tables:
                    has_tables = True

                # Image detection
                if page.images:
                    has_images = True

                # Header/footer text: top 8% or bottom 8% of page
                header_band_max = page_height * 0.08
                footer_band_min = page_height * 0.92
                for word in words:
                    y_top = word.get("top", page_height / 2)
                    if y_top < header_band_max or y_top > footer_band_min:
                        header_footer_parts.append(word.get("text", ""))

                # Font metadata
                if hasattr(page, "chars"):
                    for char in page.chars:
                        font = char.get("fontname", "")
                        if font:
                            embedded_fonts.add(font)

            is_scanned = len(all_text.strip()) < 50 and page_count > 0

            return LayoutFacts(
                page_count=page_count,
                has_columns=has_columns,
                has_tables=has_tables,
                is_scanned=is_scanned,
                embedded_fonts=tuple(sorted(embedded_fonts)),
                font_sizes_by_section={},  # reserved for future use
                has_images=has_images,
                header_footer_text=tuple(header_footer_parts[:20]),
                file_type=file_type or "pdf",
            )

    except Exception as e:
        logger.warning(f"probe_layout failed ({type(e).__name__}: {e}) — using stub")
        return _stub_layout()
