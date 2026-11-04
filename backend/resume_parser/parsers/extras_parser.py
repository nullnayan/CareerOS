"""
Modules 9, 10, 11 — Certifications, Languages, Achievements Parsers
=====================================================================
Smaller/simpler parsers batched together.

certifications_parser.parse(text) → [{"name": ..., "issuer": ..., "year": ..., "credentialId": ...}]
languages_parser.parse(text)      → [{"language": ..., "proficiency": ...}]
achievements_parser.parse(text)   → [{"text": ..., "year": ..., "type": ...}]
"""

import re
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 9 — Certifications Parser
# ══════════════════════════════════════════════════════════════════════════════

# Known certificate issuers for confidence boosting
_KNOWN_ISSUERS = {
    "google", "aws", "amazon", "microsoft", "azure", "meta", "coursera",
    "udemy", "linkedin", "oracle", "cisco", "pmi", "scrum", "comptia",
    "salesforce", "databricks", "nvidia", "ibm", "redhat", "hashicorp",
    "mongodb", "elastic", "cncf", "isaca", "isc2", "gcp"
}

_CERT_YEAR = re.compile(r"\b(20\d{2}|19\d{2})\b")
_CREDENTIAL_ID = re.compile(r"(?:credential\s*id|certificate\s*id|license\s*#?)[:\s]*([A-Za-z0-9\-]{6,30})", re.IGNORECASE)
_CERT_ENTRY_SPLIT = re.compile(r"\n{2,}|(?=^\s*[•\-\*\u2013\u2014]\s*)|\n(?=[A-Z])", re.MULTILINE)


def parse_certifications(text: str) -> list[dict]:
    if not text.strip():
        return []

    entries = []
    blocks = _CERT_ENTRY_SPLIT.split(text.strip())

    for block in blocks:
        block = block.strip().lstrip("•- ").strip()
        if not block or len(block) < 5:
            continue

        year = None
        y_m = _CERT_YEAR.search(block)
        if y_m:
            year = int(y_m.group(0))

        credential_id = None
        cid_m = _CREDENTIAL_ID.search(block)
        if cid_m:
            credential_id = cid_m.group(1)

        # Issuer: look for "by X" or "from X" or well-known issuer name
        issuer = None
        issuer_m = re.search(r"\b(?:by|from|issued\s+by|via)\s+([A-Z][a-zA-Z\s&]+)", block)
        if issuer_m:
            issuer = issuer_m.group(1).strip()
        else:
            for known in _KNOWN_ISSUERS:
                if known in block.lower():
                    issuer = known.title()
                    break

        # Check if block is a valid certification vs a misplaced skill (Bug 2 Fix)
        has_cert_indicator = bool(
            year or credential_id or issuer or
            re.search(r"\b(certif|license|credential|course|exam|badge|passed|completed)\b", block, re.IGNORECASE)
        )
        if not has_cert_indicator:
            # Standalone skill phrase without cert indicator is NOT a certification
            continue

        # Extract name line and description lines (Bug 3 Fix)
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        name_line = lines[0] if lines else block
        description = " ".join(lines[1:]).strip() if len(lines) > 1 else None

        # Check for inline dash separator like "Google Cybersecurity Course – Learned threat detection..."
        if not description and (" – " in name_line or " - " in name_line or " — " in name_line):
            dash_parts = re.split(r"\s+[–—\-]\s+", name_line, maxsplit=1)
            if len(dash_parts) == 2:
                name_line, description = dash_parts[0], dash_parts[1]

        name = _CERT_YEAR.sub("", name_line).strip().rstrip("|-–,")

        if name:
            entries.append({
                "name": name,
                "issuer": issuer,
                "year": year,
                "credentialId": credential_id,
                "description": description,
                "_confidence": "high" if (issuer or year) else "medium"
            })

    return entries


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 10 — Languages Parser
# ══════════════════════════════════════════════════════════════════════════════

# Proficiency level keywords → canonical levels (CEFR-aligned)
_PROFICIENCY_MAP = {
    "native": "Native",
    "mother tongue": "Native",
    "first language": "Native",
    "bilingual": "Native",
    "fluent": "Fluent (C2)",
    "c2": "Fluent (C2)",
    "advanced": "Advanced (C1)",
    "c1": "Advanced (C1)",
    "professional": "Professional (B2)",
    "upper intermediate": "Professional (B2)",
    "b2": "Professional (B2)",
    "intermediate": "Intermediate (B1)",
    "b1": "Intermediate (B1)",
    "conversational": "Intermediate (B1)",
    "elementary": "Elementary (A2)",
    "a2": "Elementary (A2)",
    "basic": "Basic (A1)",
    "beginner": "Basic (A1)",
    "a1": "Basic (A1)",
    "working proficiency": "Professional (B2)",
    "limited": "Basic (A1)",
}

# Common world languages
_KNOWN_LANGUAGES = {
    "english", "hindi", "spanish", "french", "german", "mandarin", "chinese",
    "arabic", "portuguese", "russian", "japanese", "korean", "italian",
    "dutch", "turkish", "polish", "swedish", "danish", "norwegian", "finnish",
    "bengali", "punjabi", "urdu", "tamil", "telugu", "marathi", "gujarati",
    "kannada", "malayalam", "nepali", "sinhala", "thai", "vietnamese",
    "indonesian", "malay", "swahili", "hebrew", "persian", "farsi", "greek",
    "czech", "hungarian", "romanian", "ukrainian", "catalan", "latin"
}

_LANG_SEPARATOR = re.compile(r"[,;|•\n]+")


def parse_languages(text: str) -> list[dict]:
    if not text.strip():
        return []

    results = []
    seen = set()
    parts = _LANG_SEPARATOR.split(text)

    for part in parts:
        part = part.strip().lstrip("•- ").strip()
        if not part or len(part) < 2:
            continue

        # Try to split "Language (Proficiency)" or "Language - Proficiency"
        lang = None
        proficiency = None

        # Pattern: "English (Native)" or "English – Fluent"
        m = re.match(r"([A-Za-z\s]+?)[\s\-–(]+([A-Za-z\s]+)\)?$", part)
        if m:
            lang_candidate = m.group(1).strip()
            prof_candidate = m.group(2).strip().lower()
            if lang_candidate.lower() in _KNOWN_LANGUAGES:
                lang = lang_candidate.title()
                proficiency = _PROFICIENCY_MAP.get(prof_candidate)
        
        if not lang:
            # Direct language name only
            part_lower = part.lower()
            for known_lang in _KNOWN_LANGUAGES:
                if known_lang in part_lower:
                    lang = known_lang.title()
                    # Try to find proficiency in the same part
                    for kw, level in _PROFICIENCY_MAP.items():
                        if kw in part_lower:
                            proficiency = level
                            break
                    break

        if lang and lang.lower() not in seen:
            seen.add(lang.lower())
            results.append({
                "language": lang,
                "proficiency": proficiency,
                "_confidence": "high" if proficiency else "medium"
            })

    return results


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 11 — Achievements Parser
# ══════════════════════════════════════════════════════════════════════════════

_ACH_YEAR = re.compile(r"\b(20\d{2}|19\d{2})\b")
_ACH_SPLIT = re.compile(r"\n+|(?=•|-\s)")

# Achievement type classifiers
_AWARD_KW = {"award", "prize", "winner", "finalist", "scholarship", "fellowship", "grant", "honour", "honor"}
_PUBLICATION_KW = {"paper", "published", "conference", "journal", "proceedings", "ieee", "acm", "arxiv"}
_COMPETITION_KW = {"hackathon", "competition", "olympiad", "championship", "contest", "rank", "first", "second", "third"}


def parse_achievements(text: str) -> list[dict]:
    if not text.strip():
        return []

    results = []
    parts = _ACH_SPLIT.split(text.strip())

    for part in parts:
        part = part.strip().lstrip("•-*► ").strip()
        if not part or len(part) < 10:
            continue

        year = None
        y_m = _ACH_YEAR.search(part)
        if y_m:
            year = int(y_m.group(0))

        # Classify type
        part_lower = part.lower()
        ach_type = "achievement"
        if any(kw in part_lower for kw in _AWARD_KW):
            ach_type = "award"
        elif any(kw in part_lower for kw in _PUBLICATION_KW):
            ach_type = "publication"
        elif any(kw in part_lower for kw in _COMPETITION_KW):
            ach_type = "competition"

        results.append({
            "text": part,
            "year": year,
            "type": ach_type,
            "_confidence": "medium"
        })

    return results
