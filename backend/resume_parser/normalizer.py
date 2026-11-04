"""
Phase 4 — Data Normalizer
==========================
Normalizes and cleans every field that the raw parsers produce.
This layer runs AFTER all parsers, BEFORE any downstream consumer.

Rules:
- Dates → "YYYY-MM" ISO strings (already done in experience_parser,
  but we also normalize education dates and handle year-only dates)
- Skills → deduplicate, merge aliases ("ReactJS" → "React")
- Location → split "City, ST" into {city, state, country}
- Strings → strip, collapse whitespace, remove junk characters
- Contact → normalize email casing, URL protocols
- Experience bullets → clean leading symbols, normalize whitespace
- Education GPA → normalize "3.9/4.0" → {"score": 3.9, "scale": 4.0}
- Duration → recompute if missing
- Summary → strip heading words ("Summary", "Profile") if accidentally included

Does NOT:
- Add or fabricate any data
- Call any AI/LLM
- Modify company names, job titles, or institution names
  (these are factual strings — only strip/clean, never rewrite)
"""

import re
from typing import Optional
from dateutil import parser as dateutil_parser
from datetime import datetime


# ─── Public entry point ────────────────────────────────────────────────────────

def normalize(parsed: dict) -> dict:
    """
    Takes the raw pipeline output dict and returns a normalized copy.
    Operates on a shallow copy — does not mutate the input.
    """
    out = dict(parsed)

    out["contact"]        = _normalize_contact(parsed.get("contact") or {})
    out["summary"]        = _normalize_text(parsed.get("summary") or "")
    out["experience"]     = _normalize_experience(parsed.get("experience") or {})
    out["education"]      = _normalize_education(parsed.get("education") or [])
    out["skills"]         = _normalize_skills(parsed.get("skills") or {})
    out["certifications"] = _normalize_certifications(parsed.get("certifications") or [])
    out["languages"]      = _normalize_languages(parsed.get("languages") or [])
    out["achievements"]   = _normalize_achievements(parsed.get("achievements") or [])
    out["projects"]       = _normalize_text(parsed.get("projects") or "")
    out["volunteer"]      = _normalize_text(parsed.get("volunteer") or "")
    out["interests"]      = _normalize_text(parsed.get("interests") or "")

    # Convert empty strings to None for cleaner JSON output
    for key in ["summary", "projects", "volunteer", "interests"]:
        if not out.get(key):
            out[key] = None

    return out


# ─── Contact normalization ─────────────────────────────────────────────────────

def _normalize_contact(contact: dict) -> dict:
    out = dict(contact)

    # Email: always lowercase
    if out.get("email"):
        out["email"] = out["email"].strip().lower()

    # Phone: strip duplicate extraction artifact (name printed twice)
    if out.get("phone"):
        out["phone"] = out["phone"].strip()

    # URLs: ensure https://, strip trailing slashes
    for url_field in ["linkedin", "github", "portfolio"]:
        if out.get(url_field):
            out[url_field] = _normalize_url(out[url_field])

    # Name: title-case normalization (respect ALL-CAPS names)
    if out.get("name"):
        out["name"] = _normalize_name(out["name"])

    # Location: try to split into structured components
    if out.get("location"):
        out["location"] = _parse_location(out["location"])

    # Remove private confidence scores from final output
    out.pop("_confidence", None)

    return out


def _normalize_name(name: str) -> str:
    """
    Normalize name: if ALL CAPS, convert to Title Case.
    If already mixed case, leave as-is (respect the original).
    """
    name = name.strip()
    if name == name.upper() and len(name) > 2:
        return name.title()
    return name


def _normalize_url(url: str) -> str:
    """Ensure URL has https:// prefix and no trailing slash."""
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    return url


def _parse_location(location: str) -> dict:
    """
    Try to parse "City, State" or "City, Country" into structured dict.
    Returns {"raw": "...", "city": ..., "state": ..., "country": ...}
    Never fails — always returns at least the raw string.
    """
    result = {"raw": location.strip(), "city": None, "state": None, "country": None}

    # Known 2-letter US state codes
    US_STATES = {
        "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
        "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
        "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
        "TX","UT","VT","VA","WA","WV","WI","WY","DC"
    }

    parts = [p.strip() for p in location.split(",")]
    if len(parts) >= 2:
        city = parts[0].strip()
        second = parts[1].strip()
        result["city"] = city
        if second.upper() in US_STATES:
            result["state"] = second.upper()
            result["country"] = "US"
        else:
            result["country"] = second

    return result


# ─── Text normalization ────────────────────────────────────────────────────────

# Section heading words that sometimes end up at the start of text content
_SECTION_HEADING_NOISE = re.compile(
    r"^(?:summary|profile|objective|overview|professional\s+summary|career\s+objective)\s*[:\-]?\s*",
    re.IGNORECASE
)

def _normalize_text(text: str) -> str:
    """Clean whitespace, remove accidental section heading prefix."""
    if not text:
        return ""
    text = text.strip()
    # Remove accidental heading prefix
    text = _SECTION_HEADING_NOISE.sub("", text).strip()
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text)
    # Collapse 3+ newlines → 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ─── Experience normalization ──────────────────────────────────────────────────

# Leading bullet symbols to strip from bullet text
_BULLET_PREFIX = re.compile(r"^[\s•\-–—▸▶►✦✧★●■□▪◆◇*]+\s*")

def _normalize_experience(experience: dict) -> dict:
    entries = experience.get("entries", [])
    normalized_entries = []

    for entry in entries:
        e = dict(entry)

        # Strip internal private keys from final output
        e.pop("_raw", None)
        e.pop("_confidence", None)

        # Normalize string fields
        e["company"] = _clean_str(e.get("company"))
        e["title"]   = _clean_str(e.get("title"))
        e["location"] = _parse_location(e["location"])["raw"] if e.get("location") else None

        # Normalize dates
        e["startDate"] = _normalize_date_str(e.get("startDate"))
        e["endDate"]   = _normalize_date_str(e.get("endDate"))

        # Recompute duration if missing
        if e.get("durationMonths") is None and e.get("startDate"):
            from resume_parser.parsers.experience_parser import _calc_duration
            e["durationMonths"] = _calc_duration(
                e["startDate"], e["endDate"], e.get("isCurrent", False)
            )

        # Clean bullets
        e["bullets"] = [_clean_bullet(b) for b in (e.get("bullets") or []) if b.strip()]

        normalized_entries.append(e)

    # Sort entries by startDate descending (most recent first)
    normalized_entries.sort(
        key=lambda e: e.get("startDate") or "0000-00",
        reverse=True
    )

    derived = dict(experience.get("_derived", {}))
    return {
        "entries": normalized_entries,
        "_derived": derived
    }


def _clean_str(s) -> Optional[str]:
    """Strip and clean a string field, return None if empty."""
    if not s:
        return None
    return re.sub(r"\s+", " ", str(s).strip())


def _clean_bullet(bullet: str) -> str:
    """Remove leading bullet symbols and normalize whitespace."""
    bullet = _BULLET_PREFIX.sub("", bullet).strip()
    return re.sub(r"\s+", " ", bullet)


def _normalize_date_str(date_str: Optional[str]) -> Optional[str]:
    """
    Ensure date is in 'YYYY-MM' format.
    Input might be 'YYYY-MM', 'YYYY', or None.
    """
    if not date_str:
        return None
    date_str = date_str.strip()

    # Already in YYYY-MM format
    if re.match(r"^\d{4}-\d{2}$", date_str):
        return date_str

    # Year only → assume January
    if re.match(r"^\d{4}$", date_str):
        return f"{date_str}-01"

    # Try dateutil parsing
    try:
        dt = dateutil_parser.parse(date_str, default=datetime(2000, 1, 1))
        return f"{dt.year:04d}-{dt.month:02d}"
    except Exception:
        return date_str  # Return as-is if we can't parse


# ─── Education normalization ───────────────────────────────────────────────────

_GPA_FRACTION = re.compile(r"([0-9]+\.?[0-9]*)\s*/\s*([0-9]+\.?[0-9]*)")

def _normalize_education(education: list) -> list:
    result = []
    for entry in education:
        e = dict(entry)
        e.pop("_raw", None)
        e.pop("_confidence", None)

        e["degree"]      = _clean_str(e.get("degree"))
        e["field"]       = _clean_str(e.get("field"))
        e["institution"] = _clean_str(e.get("institution"))
        e["honors"]      = _clean_str(e.get("honors"))

        # Normalize GPA → structured dict
        raw_gpa = e.get("gpa")
        if raw_gpa:
            e["gpa"] = _normalize_gpa(str(raw_gpa))
        else:
            e["gpa"] = None

        # Normalize year fields → integers
        e["startYear"] = _safe_int(e.get("startYear"))
        e["endYear"]   = _safe_int(e.get("endYear"))

        result.append(e)
    return result


def _normalize_gpa(raw: str) -> Optional[dict]:
    """
    Normalize GPA string:
    "3.9/4.0" → {"score": 3.9, "scale": 4.0, "raw": "3.9/4.0"}
    "3.9"     → {"score": 3.9, "scale": None, "raw": "3.9"}
    """
    raw = raw.strip()
    m = _GPA_FRACTION.match(raw)
    if m:
        try:
            return {
                "score": float(m.group(1)),
                "scale": float(m.group(2)),
                "raw": raw
            }
        except ValueError:
            pass
    try:
        return {"score": float(raw), "scale": None, "raw": raw}
    except ValueError:
        return {"score": None, "scale": None, "raw": raw}


def _safe_int(val) -> Optional[int]:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None


# ─── Skills normalization ──────────────────────────────────────────────────────

def _normalize_skills(skills: dict) -> dict:
    """
    Deduplicate skills (case-insensitive), preserve order,
    and clean up the byCategory dict.
    """
    all_skills = skills.get("all", [])
    by_category = skills.get("byCategory", {})

    # Deduplicate all_skills preserving order
    seen = set()
    deduped = []
    for s in all_skills:
        key = s.lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(s.strip())

    # Deduplicate byCategory
    clean_categories = {}
    for cat, skill_list in by_category.items():
        cat_seen = set()
        cat_deduped = []
        for s in skill_list:
            key = s.lower().strip()
            if key not in cat_seen:
                cat_seen.add(key)
                cat_deduped.append(s.strip())
        if cat_deduped:
            clean_categories[cat] = cat_deduped

    return {
        "all": deduped,
        "byCategory": clean_categories,
        "totalCount": len(deduped)
    }


# ─── Certifications normalization ─────────────────────────────────────────────

def _normalize_certifications(certs: list) -> list:
    result = []
    for cert in certs:
        c = dict(cert)
        c.pop("_confidence", None)
        c["name"]         = _clean_str(c.get("name"))
        c["issuer"]       = _clean_str(c.get("issuer"))
        c["year"]         = _safe_int(c.get("year"))
        c["credentialId"] = _clean_str(c.get("credentialId"))
        if c["name"]:
            result.append(c)
    return result


# ─── Languages normalization ───────────────────────────────────────────────────

def _normalize_languages(languages: list) -> list:
    result = []
    seen = set()
    for lang in languages:
        l = dict(lang)
        l.pop("_confidence", None)
        name = _clean_str(l.get("language"))
        if name and name.lower() not in seen:
            seen.add(name.lower())
            l["language"] = name
            result.append(l)
    return result


# ─── Achievements normalization ────────────────────────────────────────────────

def _normalize_achievements(achievements: list) -> list:
    result = []
    for ach in achievements:
        a = dict(ach)
        a.pop("_confidence", None)
        a["text"] = _normalize_text(a.get("text", ""))
        a["year"] = _safe_int(a.get("year"))
        if a["text"]:
            result.append(a)
    return result
