"""
jd/extract.py — Phase 6: LLM extraction path for JD parsing.

Implements:
- LLM extraction path (Gemini/OpenAI via LLMClient) with structured JSON output
- Keyed file-based cache (replaces unbounded in-process dict that died on restart)
- Falls back to rule-based extractor on LLM failure
- Populates `required` flag and `min_years` from LLM output
- Always returns a JobTarget (never None)

Cache key: SHA-256 of JD text → stored in ats/jd/.cache/ as .json files
"""
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

from ..models import JobTarget, JDKeyword
from .fallback import extract_fallback
from ..ontology.loader import SkillOntology

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

_ontology: Optional[SkillOntology] = None


def _get_ontology() -> SkillOntology:
    global _ontology
    if _ontology is None:
        _ontology = SkillOntology()
    return _ontology


def _cache_key(jd_text: str) -> str:
    return hashlib.sha256(jd_text.encode("utf-8")).hexdigest()


def _load_cache(key: str) -> Optional[dict]:
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _save_cache(key: str, data: dict) -> None:
    try:
        with open(CACHE_DIR / f"{key}.json", "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"JD cache write failed: {e}")


def _build_jt_from_llm(llm_data: dict, source_hash: str) -> Optional[JobTarget]:
    """Convert LLM structured output → JobTarget."""
    onto = _get_ontology()
    keywords = []

    raw_skills = llm_data.get("skills", [])
    for skill_entry in raw_skills:
        term = skill_entry.get("name", "").strip() if isinstance(skill_entry, dict) else str(skill_entry).strip()
        required = skill_entry.get("required", False) if isinstance(skill_entry, dict) else False
        if not term:
            continue

        # Canonicalise against ontology
        skill_id = onto.canonicalize(term)
        if skill_id:
            skill_data = onto._id_map[skill_id]
            kind = skill_data.get("kind", "hard")
            canonical = skill_data["canonical"]
        else:
            skill_id = None
            kind = "hard"
            canonical = term

        # Count frequency in JD text (passed through llm_data)
        jd_lower = llm_data.get("_jd_text_lower", "")
        freq = len(re.findall(r"\b" + re.escape(term.lower()) + r"\b", jd_lower))

        keywords.append(JDKeyword(
            term=canonical,
            skill_id=skill_id,
            kind=kind,
            jd_frequency=max(1, freq),
            required=required,
        ))

    if len(keywords) < 3:
        return None  # LLM didn't extract enough — will fall back

    title = llm_data.get("title", "")
    title_norm = title.lower().strip()
    for prefix in ("senior ", "junior ", "lead ", "sr. ", "jr. ", "staff ", "principal "):
        if title_norm.startswith(prefix):
            title_norm = title_norm[len(prefix):]
            break
    title_norm = title_norm.replace(" ", "_")

    min_years_raw = llm_data.get("min_years")
    try:
        min_years = float(min_years_raw) if min_years_raw is not None else None
    except (TypeError, ValueError):
        min_years = None

    # Bug 4 fix: apply same tri-state vocabulary as fallback.py
    _LOW_CONFIDENCE_THRESHOLD = 5
    if len(keywords) == 0:
        confidence = "failed"
    elif len(keywords) < _LOW_CONFIDENCE_THRESHOLD:
        confidence = "low_confidence"
    else:
        confidence = "ok"

    return JobTarget(
        title=title or "Unknown Title",
        title_normalized=title_norm or "unknown_title",
        seniority=llm_data.get("seniority", "entry"),
        keywords=tuple(keywords),
        min_years=min_years,
        required_degree=llm_data.get("required_degree"),
        source_hash=source_hash,
        extraction_confidence=confidence,
    )


LLM_SYSTEM_PROMPT = """You are an expert at parsing job descriptions.
Extract structured information and return ONLY valid JSON with this schema:
{
  "title": "exact job title from the JD",
  "seniority": "student|entry|mid|senior|exec",
  "min_years": null or number,
  "required_degree": null or "bachelor|master|phd|any",
  "skills": [
    {"name": "Python", "required": true},
    {"name": "Leadership", "required": false}
  ]
}
Include ALL skills, tools, and technologies mentioned. Mark as required=true only if the JD says "required", "must have", or "essential"."""


def _extract_via_llm(jd_text: str, title_hint: str, seniority: str) -> Optional[dict]:
    """Call LLM for structured JD extraction. Returns raw dict or None on failure."""
    try:
        from agents.llm_client import LLMClient
        client = LLMClient("jd_extractor")
        response = client.generate(
            system_prompt=LLM_SYSTEM_PROMPT,
            user_prompt=f"Job Title Hint: {title_hint}\n\nJob Description:\n{jd_text[:3000]}",
            json_mode=True,
        )
        if isinstance(response, str):
            data = json.loads(response)
        elif isinstance(response, dict):
            data = response
        else:
            return None
        data["_jd_text_lower"] = jd_text.lower()
        return data
    except Exception as e:
        logger.info(f"LLM JD extraction failed ({type(e).__name__}): {e} — using fallback")
        return None


def extract_job_target(jd_text: str, title: str, seniority: str) -> JobTarget:
    """
    Extracts a JobTarget from raw JD text.

    Pipeline:
    1. Check file-based cache (keyed by SHA-256 of JD text)
    2. Try LLM extraction (Gemini/OpenAI via LLMClient)
    3. Fall back to rule-based ontology scan
    Always returns a JobTarget — never None.
    """
    source_hash = _cache_key(jd_text)

    # 1. Cache hit
    cached = _load_cache(source_hash)
    if cached:
        try:
            keywords = tuple(
                JDKeyword(**kw) for kw in cached.get("keywords", [])
            )
            return JobTarget(
                title=cached["title"],
                title_normalized=cached["title_normalized"],
                seniority=cached["seniority"],
                keywords=keywords,
                min_years=cached.get("min_years"),
                required_degree=cached.get("required_degree"),
                source_hash=source_hash,
                extraction_confidence=cached.get("extraction_confidence", "ok"),
            )
        except Exception:
            pass  # Corrupted cache — re-extract

    # 2. LLM path
    llm_data = _extract_via_llm(jd_text, title, seniority)
    jt = None
    if llm_data:
        jt = _build_jt_from_llm(llm_data, source_hash)

    # 3. Fallback
    if jt is None:
        jt = extract_fallback(jd_text, title, seniority, source_hash)

    # 4. Persist to cache
    try:
        _save_cache(source_hash, {
            "title": jt.title,
            "title_normalized": jt.title_normalized,
            "seniority": jt.seniority,
            "keywords": [
                {
                    "term": kw.term,
                    "skill_id": kw.skill_id,
                    "kind": kw.kind,
                    "jd_frequency": kw.jd_frequency,
                    "required": kw.required,
                }
                for kw in jt.keywords
            ],
            "min_years": jt.min_years,
            "required_degree": jt.required_degree,
            "extraction_confidence": jt.extraction_confidence,
        })
    except Exception:
        pass

    return jt
