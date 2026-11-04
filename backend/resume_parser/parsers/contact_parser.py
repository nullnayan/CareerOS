"""
Module 4 — Contact Information Parser
=====================================
Phase 3 (first parser, easiest).

Extracts: name, email(s), phone(s), LinkedIn URL, GitHub URL,
          portfolio/website URL, location (city, state, country).

Strategy:
- Email & phone: pure regex (very reliable)
- URLs: regex with platform detection
- Location: regex heuristics + spaCy GPE fallback
- Name: spaCy NER PERSON entity on the first ~5 lines (most resumes
  put the name at the top — this avoids false positives from body text)

Confidence scoring:
- regex match → "high"
- spaCy NER → "medium"
- positional heuristic → "low"
- not found → None
"""

import re
from typing import Optional

# ─── Regex Patterns ────────────────────────────────────────────────────────────

_EMAIL = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE
)

_PHONE = re.compile(
    r"""
    (?:
        (?:\+?\d{1,3}[\s\-.])?          # optional country code
        (?:\(?\d{2,4}\)?[\s\-.])?        # optional area code
        \d{3,4}[\s\-.]                   # first group
        \d{3,4}                          # second group
        (?:[\s\-\.]\d{2,4})?             # optional extension
    )
    """,
    re.VERBOSE
)

_LINKEDIN = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+/?",
    re.IGNORECASE
)

_GITHUB = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9\-_%]+/?",
    re.IGNORECASE
)

_PORTFOLIO = re.compile(
    r"(?:https?://)?(?:www\.)?[A-Za-z0-9\-]+\.[A-Za-z]{2,}(?:/[^\s]*)?",
    re.IGNORECASE
)

# Location heuristic: "City, State" or "City, Country" patterns
_LOCATION = re.compile(
    r"\b([A-Z][a-zA-Z\s]+),\s*([A-Z]{2}|[A-Z][a-zA-Z\s]+)\b"
)


# ─── Public entry point ────────────────────────────────────────────────────────

def parse(contact_text: str, raw_text: str, extracted_links: list = None) -> dict:
    """
    contact_text: the "contact" section text (may be empty for resumes
                  that put contact info inline at the top)
    raw_text:     the full resume text (used for name extraction + fallback)
    extracted_links: list of URLs extracted directly from PDF hyperlink annotations
    """
    # Combine — many resumes don't have an explicit "Contact" section heading
    search_text = contact_text + "\n" + raw_text[:800]  # First 800 chars for name

    result = {
        "name": None,
        "email": None,
        "phone": None,
        "linkedin": None,
        "github": None,
        "portfolio": None,
        "location": None,
        "links": [],
        "_confidence": {}
    }

    # ── Email ──────────────────────────────────────────────────────────────────
    emails = _EMAIL.findall(search_text)
    if emails:
        result["email"] = emails[0].lower()
        result["_confidence"]["email"] = "high"

    # ── Phone ──────────────────────────────────────────────────────────────────
    raw_phones = _PHONE.findall(search_text)
    phones = [_normalize_phone(p.strip()) for p in raw_phones if len(re.sub(r"\D", "", p)) >= 7]
    if phones:
        result["phone"] = phones[0]
        result["_confidence"]["phone"] = "high"

    # ── LinkedIn ───────────────────────────────────────────────────────────────
    linkedin_matches = _LINKEDIN.findall(search_text)
    if linkedin_matches:
        result["linkedin"] = _normalize_url(linkedin_matches[0])
        result["_confidence"]["linkedin"] = "high"

    # ── GitHub ─────────────────────────────────────────────────────────────────
    github_matches = _GITHUB.findall(search_text)
    if github_matches:
        result["github"] = _normalize_url(github_matches[0])
        result["_confidence"]["github"] = "high"

    # ── Portfolio / Website ────────────────────────────────────────────────────
    all_urls = _PORTFOLIO.findall(search_text)
    for url in all_urls:
        normalized = _normalize_url(url)
        if "linkedin.com" in normalized or "github.com" in normalized:
            continue
        if any(d in normalized for d in ["gmail.com", "yahoo.com", "outlook.com"]):
            continue
        result["portfolio"] = normalized
        result["_confidence"]["portfolio"] = "high"
        break

    # ── PDF Link Annotations Fallback ──────────────────────────────────────────
    if extracted_links:
        for url in extracted_links:
            if _LINKEDIN.search(url) and not result["linkedin"]:
                result["linkedin"] = _normalize_url(url)
                result["_confidence"]["linkedin"] = "high"
            elif _GITHUB.search(url) and not result["github"]:
                result["github"] = _normalize_url(url)
                result["_confidence"]["github"] = "high"
            elif _PORTFOLIO.search(url) and not result["portfolio"]:
                normalized = _normalize_url(url)
                if not any(d in normalized for d in ["linkedin.com", "github.com", "gmail.com", "yahoo.com", "outlook.com"]):
                    result["portfolio"] = normalized
                    result["_confidence"]["portfolio"] = "high"

    # ── Collect ALL Generic Links ──────────────────────────────────────────────
    # 1. Grab links from extracted links
    all_found_links = []
    if extracted_links:
        for l in extracted_links:
            normalized = _normalize_url(l)
            if normalized not in all_found_links:
                all_found_links.append(normalized)
    
    # 2. Extract standard URLs from text using regex
    url_pattern = re.compile(r"\bhttps?://[^\s<>\"']+\b", re.IGNORECASE)
    for m in url_pattern.findall(search_text):
        normalized = _normalize_url(m)
        if normalized not in all_found_links:
            all_found_links.append(normalized)

    # 3. Add explicit parsed fields if they aren't already in the list
    for key in ["linkedin", "github", "portfolio"]:
        if result[key]:
            normalized = _normalize_url(result[key])
            if normalized not in all_found_links:
                all_found_links.append(normalized)

    result["links"] = all_found_links

    # ── Location ───────────────────────────────────────────────────────────────
    loc_match = _LOCATION.search(search_text[:600])
    if loc_match:
        result["location"] = loc_match.group(0).strip()
        result["_confidence"]["location"] = "medium"

    # ── Name (spaCy NER on first few lines) ────────────────────────────────────
    name, conf = _extract_name(raw_text)
    if name:
        result["name"] = name
        result["_confidence"]["name"] = conf

    return result


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _extract_name(raw_text: str) -> tuple[Optional[str], str]:
    """
    Try to extract the candidate's name from the top of the resume.
    Strategy 1: spaCy PERSON entity in first 5 lines.
    Strategy 2: Heuristic — first non-email, non-URL, short line at top
                that looks like a proper name (Title Case, 2-4 words).
    """
    first_lines = "\n".join(raw_text.strip().split("\n")[:5])

    # Strategy 1: spaCy NER
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        doc = nlp(first_lines)
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                # Split by newline in case spaCy merged lines
                name_candidate = ent.text.split("\n")[0].strip()
                if 2 <= len(name_candidate.split()) <= 4:
                    return name_candidate, "medium"
    except Exception:
        pass

    # Strategy 2: Heuristic positional name detection
    for line in first_lines.split("\n"):
        line = line.strip()
        if not line or len(line) > 50:
            continue
        if _EMAIL.search(line) or _LINKEDIN.search(line):
            continue
        words = line.split()
        if 2 <= len(words) <= 4:
            if all(w[0].isupper() for w in words if w.isalpha()):
                return line, "low"

    return None, "low"


def _normalize_phone(phone: str) -> str:
    """Strip non-digit chars and format as E.164-ish."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == "1":
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return phone  # return as-is if we can't normalize


def _normalize_url(url: str) -> str:
    """Ensure URL starts with https://"""
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    return url
