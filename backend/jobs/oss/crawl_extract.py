"""Pure extraction and validation helpers for Crawl4AI source profiles."""
from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import json
from typing import Any, Iterable


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__(); self._script = False; self._is_jsonld = False; self._buffer: list[str] = []; self.blocks: list[str] = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            self._script = True
            self._is_jsonld = any(k.lower() == "type" and "ld+json" in str(v).lower() for k, v in attrs)
            self._buffer = []
    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._script:
            if self._is_jsonld: self.blocks.append("".join(self._buffer))
            self._script = False; self._is_jsonld = False; self._buffer = []
    def handle_data(self, data):
        if self._script and self._is_jsonld: self._buffer.append(data)


def _flatten_jsonld(value: Any, depth=0) -> Iterable[dict[str, Any]]:
    if depth > 12: return
    if isinstance(value, list):
        for item in value: yield from _flatten_jsonld(item, depth + 1)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        if isinstance(types, str): types = [types]
        if "JobPosting" in types: yield value
        graph = value.get("@graph")
        if graph is not None: yield from _flatten_jsonld(graph, depth + 1)


def _text(value: Any) -> str:
    if value is None: return ""
    if isinstance(value, dict):
        return str(value.get("name") or value.get("text") or "")
    if isinstance(value, list): return ", ".join(_text(item) for item in value if item)
    return str(value)


def structured_job_records(html: str, page_url: str) -> list[dict[str, Any]]:
    """Read JobPosting JSON-LD without executing source JavaScript."""
    parser = _Scripts()
    parser.feed(html or "")
    out: list[dict[str, Any]] = []
    for block in parser.blocks:
        try: value = json.loads(unescape(block.strip()))
        except (TypeError, ValueError, RecursionError): continue
        for item in _flatten_jsonld(value):
            employer = item.get("hiringOrganization") or {}
            salary = item.get("baseSalary") or {}
            salary_value = salary.get("value") if isinstance(salary, dict) else None
            salary_value = salary_value if isinstance(salary_value, dict) else {}
            address = item.get("jobLocation") or item.get("jobLocationType")
            if isinstance(address, list):
                cities = []
                for place in address:
                    place = place if isinstance(place, dict) else {}
                    addr = place.get("address") or {}
                    cities.append(" ".join(str(addr.get(k) or "") for k in ("addressLocality", "addressRegion", "addressCountry")).strip())
                address = ", ".join(x for x in cities if x)
            elif isinstance(address, dict):
                addr = address.get("address") or {}
                address = " ".join(str(addr.get(k) or "") for k in ("addressLocality", "addressRegion", "addressCountry")).strip()
            out.append({
                "id": _text(item.get("identifier")) or _text(item.get("url")) or page_url,
                "title": _text(item.get("title")),
                "company": _text(employer.get("name")) if isinstance(employer, dict) else _text(employer),
                "location": _text(address),
                "source_url": _text(item.get("url")) or page_url,
                "apply_url": _text(item.get("url")) or page_url,
                "description": item.get("description") or "",
                "description_complete": bool(item.get("description")),
                "date_posted": item.get("datePosted"),
                "expires_at": item.get("validThrough"),
                "employment_type": _text(item.get("employmentType")),
                "salary_min": salary_value.get("minValue"),
                "salary_max": salary_value.get("maxValue"),
                "salary_currency": salary.get("currency") if isinstance(salary, dict) else None,
                "salary_period": salary_value.get("unitText"),
                "original_salary_source": "direct_data" if salary_value else None,
                "source_evidence": "JobPosting JSON-LD",
            })
    return out


def classify_page(status_code: int | None, text: str, profile: dict[str, Any]) -> str | None:
    """Return login_required/blocked/None. Called before extraction or AI fallback."""
    lower = (text or "").casefold()
    if status_code in {401, 407}:
        return "login_required"
    if status_code in {403, 429}:
        return "blocked"
    if any(str(marker).casefold() in lower for marker in profile.get("challenge_indicators", [])):
        return "blocked"
    if any(str(marker).casefold() in lower for marker in profile.get("login_indicators", [])):
        return "login_required"
    return None


def validate_ai_record(record: Any, *, allowed_links: set[str], source_text: str) -> dict[str, Any] | None:
    """Require a known link and exact source evidence for every extracted field."""
    if not isinstance(record, dict): return None
    url = record.get("source_url")
    title = record.get("title")
    company = record.get("company")
    evidence = record.get("evidence")
    if not isinstance(url, str) or url not in allowed_links or not isinstance(title, str) or not title.strip(): return None
    if not isinstance(company, str) or not company.strip() or not isinstance(evidence, dict): return None
    lowered = (source_text or "").casefold()
    for key, value in (("title", title), ("company", company)):
        quote = evidence.get(key)
        if not isinstance(quote, str) or len(quote) < 3 or quote.casefold() not in lowered or value.casefold() not in quote.casefold():
            return None
    description = record.get("description") or ""
    if description:
        quote = evidence.get("description")
        if not isinstance(description, str) or not isinstance(quote, str) or len(quote) < 20 or quote.casefold() not in lowered or description.casefold() not in quote.casefold():
            return None
    out = {"id": record.get("id") or url, "title": title.strip()[:300], "company": company.strip()[:240],
           "source_url": url, "apply_url": url, "location": "", "description": description[:50000],
           "description_complete": False, "source_evidence": "validated local-model excerpt"}
    if isinstance(record.get("location"), str) and record["location"].casefold() in lowered:
        out["location"] = record["location"][:300]
    return out
