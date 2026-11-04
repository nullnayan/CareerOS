"""
Pulls plain text out of an uploaded resume file. This is NOT an AI task —
it's just reading the file format, so it lives in services/, not agents/,
per our folder structure convention (see Architecture doc, Section 1.1).
"""

import fitz  # PyMuPDF — the library's internal name, different from its
             # install name (pymupdf), which trips people up the first time
from docx import Document
import io
import os


def extract_text(file_bytes: bytes, filename: str) -> str:
    """
    Takes raw file bytes and the original filename (to detect the type),
    returns plain text. Raises a clear error for unsupported types instead
    of failing silently.
    """
    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):
        return _extract_from_pdf(file_bytes)
    elif lower_name.endswith(".docx"):
        return _extract_from_docx(file_bytes)
    elif lower_name.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore")
    elif lower_name.endswith((".png", ".jpg", ".jpeg")):
        return ""  # Image files contain no direct selectable text
    else:
        raise ValueError(
            f"Unsupported file type: '{filename}'. "
            f"Only .pdf, .docx, .png, .jpg, .jpeg, and .txt are supported right now."
        )


import re

def _extract_from_pdf(file_bytes: bytes) -> str:
    text_parts = []
    links_found = set()
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            for link in page.get_links():
                uri = link.get("uri")
                if uri and uri.startswith(("http://", "https://")):
                    links_found.add(uri)
            
            # Use "blocks" mode for layout-aware extraction.
            # Each block is a tuple: (x0, y0, x1, y1, text, block_no, block_type)
            # Sorting by (y0, x0) gives correct top-to-bottom, left-to-right order
            # which preserves multi-column layouts better than raw stream reading.
            try:
                blocks = page.get_text("blocks", sort=True)
                page_lines = []
                for block in blocks:
                    if len(block) >= 5 and block[6] == 0:  # block_type 0 = text
                        block_text = block[4].strip()
                        if block_text:
                            page_lines.append(block_text)
                text_parts.append("\n".join(page_lines))
            except Exception:
                # Fallback to simple text extraction if blocks mode fails
                text_parts.append(page.get_text("text"))
            
    full_text = "\n".join(text_parts).strip()
    
    if links_found:
        full_text += "\n\n--- EXTRACTED HYPERLINKS ---\n" + "\n".join(sorted(links_found))
    
    # Clean up: normalize multiple blank lines and extra spaces
    full_text = re.sub(r'\n{3,}', '\n\n', full_text)
    full_text = re.sub(r' {2,}', ' ', full_text)
    
    # Normalize unicode ligature characters that PDFs often embed.
    # These break ATS keyword parsers (e.g. \ufb01 for 'fi' looks like an unknown glyph).
    full_text = _normalize_ligatures(full_text)
    return full_text


def _normalize_ligatures(text: str) -> str:
    """Replace unicode typographic ligatures with their ASCII equivalents."""
    ligature_map = {
        '\ufb00': 'ff',
        '\ufb01': 'fi',
        '\ufb02': 'fl',
        '\ufb03': 'ffi',
        '\ufb04': 'ffl',
        '\ufb05': 'st',
        '\ufb06': 'st',
    }
    for ligature, replacement in ligature_map.items():
        text = text.replace(ligature, replacement)
    return text


import pdfplumber
import io

def check_pdf_layout(file_bytes: bytes) -> dict:
    """Uses pdfplumber to detect tables, multiple columns, and scanned text-selectability."""
    layout_info = {
        "has_columns": False,
        "has_tables": False,
        "is_scanned_pdf": False
    }
    
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if not pdf.pages:
                return layout_info
                
            # Check for scanned PDF
            first_page = pdf.pages[0]
            text = first_page.extract_text() or ""
            if len(text.strip()) < 10:
                if first_page.images:
                    layout_info["is_scanned_pdf"] = True
                
            # Check for tables
            for page in pdf.pages:
                tables = page.extract_tables()
                if tables:
                    layout_info["has_tables"] = True
                    break
                    
            # Check for multi-column layout using X-projection
            words = first_page.extract_words()
            if words and len(words) > 30:
                width = first_page.width
                coverage = [0] * int(width + 1)
                
                page_height = first_page.height
                margin_y = page_height * 0.15
                
                content_words = [
                    w for w in words 
                    if w["top"] > margin_y and w["bottom"] < (page_height - margin_y)
                ]
                
                for w in content_words:
                    x0 = max(0, int(w["x0"]))
                    x1 = min(int(width), int(w["x1"]))
                    for x in range(x0, x1 + 1):
                        coverage[x] += 1
                
                # Check for a column gap in the middle 30% of the page
                gutter_search_start = int(width * 0.35)
                gutter_search_end = int(width * 0.65)
                min_gutter_width = 15
                
                current_gap = 0
                max_gap = 0
                for x in range(gutter_search_start, gutter_search_end):
                    if coverage[x] <= 1:
                        current_gap += 1
                        if current_gap > max_gap:
                            max_gap = current_gap
                    else:
                        current_gap = 0
                        
                if max_gap >= min_gutter_width:
                    layout_info["has_columns"] = True
                    
    except Exception:
        # Avoid crashing the upload flow
        pass
        
    return layout_info


def _extract_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    
    text_parts = []
    
    # Extract regular paragraphs
    for p in doc.paragraphs:
        if p.text.strip():
            text_parts.append(p.text)
    
    # Extract table cells — many resume templates put skills and contact info in tables
    # which are completely invisible to paragraph-only extraction
    for table in doc.tables:
        for row in table.rows:
            row_texts = []
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text and cell_text not in row_texts:
                    row_texts.append(cell_text)
            if row_texts:
                text_parts.append(" | ".join(row_texts))
    
    return "\n".join(text_parts).strip()


import zipfile

def extract_zip_files(zip_bytes: bytes) -> list:
    """
    Decompresses zip archive bytes and extracts text files, preserving folder paths.
    Automatically filters out binaries, lockfiles, node_modules, git assets, etc.
    """
    extracted = []
    
    # Ignore system, binary, or dependency folders
    ignored_patterns = {
        '.git', 'node_modules', '__pycache__', '.env', '.venv', 'venv', 
        'dist', 'build', '.next', '.idea', '.vscode'
    }
    
    # Ignore binary files
    ignored_extensions = {
        '.pyc', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip',
        '.tar', '.gz', '.db', '.sqlite', '.exe', '.dll', '.so', '.dylib',
        '.woff', '.woff2', '.eot', '.ttf', '.mp4', '.mp3', '.zip'
    }

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for member in z.infolist():
            # Skip directories
            if member.is_dir():
                continue
                
            parts = member.filename.replace('\\', '/').split('/')
            
            # Check if any folder path segment is ignored
            if any(p in ignored_patterns for p in parts):
                continue
                
            # Check if file has ignored extension
            filename = parts[-1]
            ext = os.path.splitext(filename)[1].lower() if 'os' in globals() or 'import os' in globals() else f".{filename.split('.')[-1]}" if '.' in filename else ""
            if ext in ignored_extensions:
                continue
                
            try:
                content = z.read(member).decode('utf-8', errors='ignore')
                extracted.append({
                    "path": member.filename.replace('\\', '/'),
                    "content": content
                })
            except Exception:
                # If it's a binary file disguised as text, decoding might raise an error
                continue
                
    return extracted


def is_image_file(filename: str) -> bool:
    """Check if the filename points to an image file."""
    ext = os.path.splitext(filename.lower())[1]
    return ext in (".png", ".jpg", ".jpeg")


def render_pdf_to_images(file_bytes: bytes) -> list:
    """Renders all pages of a PDF to list of PNG image bytes."""
    images = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=150)
            images.append(pix.tobytes("png"))
    return images

