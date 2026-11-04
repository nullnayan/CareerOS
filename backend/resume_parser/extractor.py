"""
Module 1 — File Processing + Text Extraction
============================================
Phase 1 of the resume parser pipeline.

Key design decision: column detection is baked IN here (not Phase 6),
because multi-column PDFs silently corrupt text order if not handled
at the extraction stage. Everything downstream (section segmentation,
entity extraction) depends on correctly-ordered text.

Output shape:
{
    "rawText": "...",
    "pages": [{"pageNumber": 1, "text": "...", "charCount": 123}, ...],
    "metadata": {
        "pageCount": 2,
        "fileType": "pdf",
        "hasColumns": False,
        "hasTables": False,
        "isScannedPdf": False,
        "wordCount": 450,
        "charCount": 2800,
        "parserVersion": "1.0.0"
    }
}
"""

import io
import re
from typing import Optional

# ─── Version tracking ─────────────────────────────────────────────────────────
PARSER_VERSION = "1.0.0"


# ─── Public entry point ────────────────────────────────────────────────────────

def extract(file_bytes: bytes, filename: str) -> dict:
    """
    Main entry point. Takes raw file bytes + original filename,
    returns the canonical output shape defined above.

    Raises ValueError for unsupported file types.
    """
    lower = filename.lower()

    if lower.endswith(".pdf"):
        return _process_pdf(file_bytes)
    elif lower.endswith(".docx"):
        return _process_docx(file_bytes)
    elif lower.endswith(".txt"):
        return _process_txt(file_bytes)
    else:
        raise ValueError(
            f"Unsupported file type: '{filename}'. "
            "Supported: .pdf, .docx, .txt"
        )


# ─── PDF Processing ────────────────────────────────────────────────────────────

def _process_pdf(file_bytes: bytes) -> dict:
    import fitz         # PyMuPDF
    import pdfplumber

    layout = _detect_pdf_layout(file_bytes)
    pages_data = []
    all_text_parts = []
    extracted_links = []

    visual_styles = {"detected_font": "Calibri", "has_borders": False}
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        visual_styles = _detect_pdf_styles(doc)
        for page_index, page in enumerate(doc):
            if layout["hasColumns"]:
                # Column-aware extraction: read left column fully, then right column
                page_text = _extract_columnar_page(page)
            else:
                # Standard block-sorted extraction (top-to-bottom, left-to-right)
                page_text = _extract_standard_page(page)

            page_text = _clean_text(page_text)
            pages_data.append({
                "pageNumber": page_index + 1,
                "text": page_text,
                "charCount": len(page_text)
            })
            all_text_parts.append(page_text)
            
            # Extract PDF link annotations
            for link in page.get_links():
                if link.get("kind") == fitz.LINK_URI:
                    uri = link.get("uri")
                    if uri:
                        extracted_links.append(uri)

    raw_text = "\n\n".join(all_text_parts).strip()
    raw_text = _clean_text(raw_text)

    return _build_output(raw_text, pages_data, "pdf", layout, extracted_links=extracted_links, visual_styles=visual_styles)


def _extract_standard_page(page) -> str:
    """Standard top-to-bottom, left-to-right block extraction."""
    try:
        blocks = page.get_text("blocks", sort=True)
        lines = []
        for block in blocks:
            # block tuple: (x0, y0, x1, y1, text, block_no, block_type)
            if len(block) >= 7 and block[6] == 0:  # block_type 0 = text
                text = block[4].strip()
                if text:
                    lines.append(text)
        return "\n".join(lines)
    except Exception:
        return page.get_text("text")


def _extract_columnar_page(page) -> str:
    """
    Column-aware extraction using x-coordinate splitting.
    Detects the column gutter midpoint, splits words into left and right columns,
    then reads left column top-to-bottom, then right column top-to-bottom.
    This prevents the left-right interleaving bug that corrupts section order.
    """
    try:
        import pdfplumber

        page_bytes = page.get_pixmap().tobytes("png") if False else None  # noqa
        # Use PyMuPDF blocks but sort by column first
        blocks = page.get_text("blocks", sort=False)
        page_width = page.rect.width

        left_blocks = []
        right_blocks = []
        col_midpoint = page_width * 0.5  # Simple midpoint split

        for block in blocks:
            if len(block) >= 7 and block[6] == 0:
                x0, y0 = block[0], block[1]
                text = block[4].strip()
                if not text:
                    continue
                if x0 < col_midpoint:
                    left_blocks.append((y0, text))
                else:
                    right_blocks.append((y0, text))

        # Sort each column by vertical position
        left_blocks.sort(key=lambda b: b[0])
        right_blocks.sort(key=lambda b: b[0])

        left_text = "\n".join(t for _, t in left_blocks)
        right_text = "\n".join(t for _, t in right_blocks)

        # Concatenate: left column first, then right column
        if right_text:
            return left_text + "\n\n" + right_text
        return left_text

    except Exception:
        # Graceful fallback to standard extraction
        return _extract_standard_page(page)


def _detect_pdf_layout(file_bytes: bytes) -> dict:
    """
    Uses pdfplumber to detect multi-column layout, tables, and scanned PDFs.
    This runs BEFORE text extraction so we can route to the correct extractor.
    """
    layout = {
        "hasColumns": False,
        "hasTables": False,
        "isScannedPdf": False,
    }

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if not pdf.pages:
                return layout

            first_page = pdf.pages[0]

            # ── Scanned PDF detection ──────────────────────────────────────
            text = first_page.extract_text() or ""
            if len(text.strip()) < 10 and first_page.images:
                layout["isScannedPdf"] = True

            # ── Table detection ────────────────────────────────────────────
            for page in pdf.pages[:3]:  # Check first 3 pages only for speed
                if page.extract_tables():
                    layout["hasTables"] = True
                    break

            # ── Multi-column detection via x-projection ────────────────────
            words = first_page.extract_words()
            if words and len(words) > 30:
                width = first_page.width
                page_height = first_page.height
                # Ignore header/footer regions (top/bottom 15%)
                margin_y = page_height * 0.15
                content_words = [
                    w for w in words
                    if w["top"] > margin_y and w["bottom"] < (page_height - margin_y)
                ]

                if content_words:
                    coverage = [0] * (int(width) + 2)
                    for w in content_words:
                        x0 = max(0, int(w["x0"]))
                        x1 = min(int(width), int(w["x1"]))
                        for x in range(x0, x1 + 1):
                            coverage[x] += 1

                    # Look for a gap (gutter) in the middle 30% of the page
                    gutter_start = int(width * 0.35)
                    gutter_end = int(width * 0.65)
                    min_gutter_width = 15  # px

                    current_gap = 0
                    max_gap = 0
                    for x in range(gutter_start, gutter_end):
                        if coverage[x] <= 1:
                            current_gap += 1
                            max_gap = max(max_gap, current_gap)
                        else:
                            current_gap = 0

                    if max_gap >= min_gutter_width:
                        layout["hasColumns"] = True

    except Exception:
        pass  # Never crash the pipeline on layout detection failure

    return layout


# ─── DOCX Processing ───────────────────────────────────────────────────────────

def _process_docx(file_bytes: bytes) -> dict:
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    text_parts = []

    # Paragraphs (main body text)
    for p in doc.paragraphs:
        if p.text.strip():
            text_parts.append(p.text)

    # Tables — many resume templates hide contact info or skills in tables,
    # which are completely invisible to paragraph-only extraction
    for table in doc.tables:
        for row in table.rows:
            row_texts = []
            seen = set()
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text and cell_text not in seen:
                    row_texts.append(cell_text)
                    seen.add(cell_text)
            if row_texts:
                text_parts.append("  |  ".join(row_texts))

    raw_text = _clean_text("\n".join(text_parts).strip())

    # DOCX is always single-page from text perspective (no per-page split)
    pages_data = [{
        "pageNumber": 1,
        "text": raw_text,
        "charCount": len(raw_text)
    }]

    layout = {
        "hasColumns": False,
        "hasTables": len(doc.tables) > 0,
        "isScannedPdf": False,
    }

    return _build_output(raw_text, pages_data, "docx", layout)


# ─── TXT Processing ────────────────────────────────────────────────────────────

def _process_txt(file_bytes: bytes) -> dict:
    raw_text = _clean_text(file_bytes.decode("utf-8", errors="ignore").strip())

    pages_data = [{
        "pageNumber": 1,
        "text": raw_text,
        "charCount": len(raw_text)
    }]
    layout = {"hasColumns": False, "hasTables": False, "isScannedPdf": False}
    return _build_output(raw_text, pages_data, "txt", layout)


# ─── Shared helpers ────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """
    Normalize whitespace artifacts from PDF extraction:
    - Collapse 3+ consecutive newlines → 2 (preserve intentional blank lines)
    - Collapse 2+ consecutive spaces → 1
    - Strip trailing/leading whitespace per line
    """
    # Normalize per-line trailing spaces
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _detect_pdf_styles(doc) -> dict:
    """Extract font family, color, and border drawing metadata from PyMuPDF doc."""
    font_counts = {}
    color_counts = {}
    has_borders = False
    
    # Defaults
    dominant_font = "EB Garamond"
    heading_color = "#000000"
    body_color = "#000000"
    heading_font_variant = "normal"
    
    font_usage = {}
    min_y = float('inf')
    max_y = 0
    page_height = doc[0].rect.height if doc.page_count > 0 else 792.0
    
    try:
        for page in doc:
            # Check drawings for horizontal line rules
            drawings = page.get_drawings()
            for dw in drawings:
                for item in dw.get("items", []):
                    if item[0] == "l": # line
                        p1, p2 = item[1], item[2]
                        if abs(p1.y - p2.y) < 2 and abs(p1.x - p2.x) > 100:
                            has_borders = True
                            # Extract color of the line
                            stroke = dw.get("color")
                            if stroke and len(stroke) == 3:
                                r, g, b = [int(c * 255) for c in stroke]
                                hex_color = f"#{r:02x}{g:02x}{b:02x}"
                                if hex_color != "#000000" and hex_color != "#ffffff":
                                    heading_color = hex_color
                            break

            # Check font names and colors across spans
            blocks = page.get_text("dict").get("blocks", [])
            for b in blocks:
                for line in b.get("lines", []):
                    bbox = line.get("bbox", (0, 0, 0, 0))
                    if bbox[1] < min_y: min_y = bbox[1]
                    if bbox[3] > max_y: max_y = bbox[3]

                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text: continue
                        
                        font_name = span.get("font", "").lower()
                        if font_name:
                            # Small caps detection
                            if any(sc in font_name for sc in ["csc", "smcp", "smallcap"]) or font_name.endswith("sc") or font_name.endswith("-sc"):
                                heading_font_variant = "small-caps"
                                
                            clean_font = "EB Garamond"
                            if any(x in font_name for x in ["cmr", "cmbx", "cmti", "cmcsc", "cmss", "cmtt", "lmroman", "garamond"]):
                                clean_font = "EB Garamond"
                            elif "lmsans" in font_name: clean_font = "Arial"
                            elif "georgia" in font_name: clean_font = "Georgia"
                            elif "times" in font_name: clean_font = "Times New Roman"
                            elif "arial" in font_name: clean_font = "Arial"
                            elif "calibri" in font_name: clean_font = "Calibri"
                            elif "helvetica" in font_name: clean_font = "Helvetica"
                            elif "tahoma" in font_name: clean_font = "Tahoma"
                            elif "verdana" in font_name: clean_font = "Verdana"
                            elif "trebuchet" in font_name: clean_font = "Trebuchet MS"
                            font_counts[clean_font] = font_counts.get(clean_font, 0) + len(text)

                            # Track usage for real font extraction
                            orig_font = span.get("font")
                            if orig_font not in font_usage:
                                font_usage[orig_font] = {'total_chars': 0, 'flags': set()}
                            font_usage[orig_font]['total_chars'] += len(text)
                            font_usage[orig_font]['flags'].add(span.get("flags", 0))
                            
                        # Extract color
                        color = span.get("color")
                        if color is not None:
                            # color is typically an integer in PyMuPDF representing RGB
                            r = (color >> 16) & 255
                            g = (color >> 8) & 255
                            b = color & 255
                            hex_c = f"#{r:02x}{g:02x}{b:02x}"
                            color_counts[hex_c] = color_counts.get(hex_c, 0) + len(text)

        if font_counts:
            dominant_font = max(font_counts, key=font_counts.get)
        if color_counts:
            body_color = max(color_counts, key=color_counts.get)
            
    except Exception:
        pass

    # Real Font Extraction removed in favor of template-driven ATS output
    extracted_fonts = {}

    fill_ratio = 1.0
    if min_y < float('inf') and max_y > 0 and page_height > 0:
        content_height = max_y - min_y
        fill_ratio = min(1.0, max(0.1, content_height / page_height))

    return {
        "detected_font": dominant_font,
        "heading_font_variant": heading_font_variant,
        "has_borders": has_borders,
        "heading_color": heading_color,
        "heading_border_color": heading_color,
        "body_color": body_color,
        "extracted_fonts": extracted_fonts,
        "fill_ratio": fill_ratio
    }


def _build_output(raw_text: str, pages_data: list, file_type: str, layout: dict, extracted_links: list = None, visual_styles: dict = None) -> dict:
    """Assembles the canonical output dictionary."""
    word_count = len(raw_text.split())
    styles = visual_styles or {}

    return {
        "rawText": raw_text,
        "pages": pages_data,
        "extracted_links": extracted_links or [],
        "metadata": {
            "pageCount": len(pages_data),
            "fileType": file_type,
            "hasColumns": layout.get("hasColumns", False),
            "hasTables": layout.get("hasTables", False),
            "isScannedPdf": layout.get("isScannedPdf", False),
            "wordCount": word_count,
            "charCount": len(raw_text),
            "parserVersion": PARSER_VERSION,
            "detected_font": styles.get("detected_font", "EB Garamond"),
            "heading_font_variant": styles.get("heading_font_variant", "normal"),
            "has_borders": styles.get("has_borders", False),
            "extracted_fonts": styles.get("extracted_fonts", {}),
            "fill_ratio": styles.get("fill_ratio", 1.0)
        }
    }
