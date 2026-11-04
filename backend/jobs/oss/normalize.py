"""Convert plain upstream records to the stable Listing-compatible contract."""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import hashlib
import ipaddress
import math
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from .contracts import NormalizedJob


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts: list[str] = []; self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}: self.hidden += 1
        elif tag in {"p", "li", "br", "div", "h1", "h2", "h3", "h4", "section"}: self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}: self.hidden = max(0, self.hidden - 1)
        elif tag in {"p", "li", "div", "h1", "h2", "h3", "h4", "section"}: self.parts.append("\n")
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def plain_text(value: Any, limit: int = 50000) -> str:
    if value is None: return ""
    if isinstance(value, (list, tuple)): value = "\n".join(str(part) for part in value if part is not None)
    if isinstance(value, dict): value = value.get("text") or value.get("description") or ""
    text = str(value)
    parser = _Text()
    try: parser.feed(unescape(unescape(text)))
    except Exception: parser.parts.append(text)
    return re.sub(r"[\t\r ]+", " ", re.sub(r"\n{3,}", "\n\n", "".join(parser.parts))).strip()[:limit]


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)): return value
    if isinstance(value, float): return value if math.isfinite(value) else None
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, (list, tuple)): return [_scalar(x) for x in value[:40]]
    if isinstance(value, Mapping): return {str(k)[:80]: _scalar(v) for k, v in list(value.items())[:80]}
    if hasattr(value, "item"):
        try: return _scalar(value.item())
        except (TypeError, ValueError): pass
    return str(value)[:1000]


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}): return value
    return None


def _name(value: Any) -> str:
    if isinstance(value, Mapping): return str(_first(value, "name", "company_name", "company", "title") or "")
    return str(value or "")


def _public_https(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2048: return None
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
        if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password or port not in (None, 443): return None
        if any(re.search(r"(?:access[_-]?token|api[_-]?key|authorization|auth[_-]?token|client[_-]?secret|cookie|password|session(?:id)?|signature|^sig$|^token$|^key$)", key, re.I)
               for key, _ in parse_qsl(parsed.query, keep_blank_values=True)): return None
        if host == "localhost" or host.endswith((".local", ".internal", ".test", ".invalid")): return None
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global: return None
        except ValueError:
            if "." not in host: return None
        return urlunsplit(("https", parsed.netloc.lower(), parsed.path, parsed.query, ""))
    except ValueError:
        return None


def _date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and math.isfinite(float(value)):
        try: parsed = datetime.fromtimestamp(float(value) / (1000 if value > 10_000_000_000 else 1), tz=timezone.utc)
        except (ValueError, OverflowError, OSError): return None
    elif isinstance(value, str):
        candidate = value.strip()
        if not candidate: return None
        try: parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError: return None
    else: return None
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def normalize_job(record: Mapping[str, Any], *, source_id: str, tool: str,
                  company_fallback: str = "") -> NormalizedJob | None:
    if not isinstance(record, Mapping): return None
    title = plain_text(_first(record, "title", "job_title", "text", "position"), 300)
    company = plain_text(_name(_first(record, "company", "company_name", "employer", "companyName")) or company_fallback, 240)
    location_value = _first(record, "location", "locations", "job_location", "raw_location")
    if isinstance(location_value, Mapping): location_value = _first(location_value, "name", "city", "label", "display_name")
    if isinstance(location_value, (list, tuple)): location_value = ", ".join(plain_text(x, 100) for x in location_value if x)
    location = plain_text(location_value, 300)
    source_url = _public_https(_first(record, "source_url", "job_url", "url", "link", "public_url"))
    apply_url = _public_https(_first(record, "apply_url", "job_url_direct", "application_url", "link", "public_url", "url")) or source_url
    if not title or not company or not apply_url: return None
    native = _first(record, "native_id", "id", "job_id", "jobId", "requisition_id", "ats_id")
    native_id = str(native).strip()[:240] if native not in (None, "") else ""
    if not native_id:
        native_id = hashlib.sha256(f"{source_id}|{title}|{apply_url}".encode()).hexdigest()[:32]
    description = plain_text(_first(record, "description", "description_text", "job_description", "content"))
    explicit_complete = _first(record, "description_complete", "complete")
    complete = bool(explicit_complete) if explicit_complete is not None else False
    published_value = _first(record, "published_at", "date_posted", "posted_at", "datePosted", "publication_date")
    published_at = _date(published_value)
    salary_obj = _first(record, "salary", "compensation", "stipend")
    salary_obj = salary_obj if isinstance(salary_obj, Mapping) else {}
    salary_min = _first(record, "salary_min", "min_amount", "salary_min_amount")
    salary_max = _first(record, "salary_max", "max_amount", "salary_max_amount")
    salary_min = salary_min if salary_min is not None else _first(salary_obj, "min_amount", "min", "minimum")
    salary_max = salary_max if salary_max is not None else _first(salary_obj, "max_amount", "max", "maximum")
    currency = _first(record, "salary_currency", "currency") or _first(salary_obj, "currency")
    period = _first(record, "salary_period", "interval", "period") or _first(salary_obj, "period", "interval")
    original_source = str(_first(record, "original_salary_source", "salary_source") or "").strip().lower()
    facts: dict[str, Any] = {
        "source_id": source_id,
        "collector_tool": tool,
        "source_url": source_url or apply_url,
        "original_application_url": apply_url,
        "description_complete": complete,
    }
    if original_source:
        facts["original_salary_source"] = original_source
        facts["salary_source"] = original_source
    normalized_source = original_source.replace("-", "_")
    if normalized_source in {"estimate", "estimated", "salary_estimate"}:
        facts["original_salary_source"] = "estimated"
    else:
        if salary_min is not None: facts["salary_min"] = _scalar(salary_min)
        if salary_max is not None: facts["salary_max"] = _scalar(salary_max)
        if currency: facts["salary_currency"] = str(currency).upper()[:3]
        if period: facts["salary_period"] = str(getattr(period, "value", period)).lower()[:24]
        if normalized_source in {"description", "description_text", "text"}:
            facts["salary_evidence"] = "description"
            facts["original_salary_source"] = "description"
        elif salary_min is not None or salary_max is not None:
            facts["salary_evidence"] = "source_fields"
            facts.setdefault("original_salary_source", "direct_data")
    for key in ("employment_type", "job_type", "experience", "experience_range", "job_level", "skills", "is_remote", "work_mode",
                "expires_at", "expiry_date", "application_deadline", "stipend", "duration",
                "country_iso", "source_family", "requisition_id"):
        value = record.get(key)
        if value is not None:
            facts[key] = _scalar(value)
    if published_value is not None:
        facts["source_published_at"] = _scalar(published_value)
    application_deadline = _first(record, "application_deadline", "expires_at", "expiry_date",
                                  "validThrough", "valid_through")
    apply_by = record.get("apply_by")
    if application_deadline is None and isinstance(apply_by, Mapping):
        application_deadline = apply_by.get("date")
    if application_deadline is not None:
        facts["application_deadline"] = _scalar(application_deadline)
    if record.get("updated_at") is not None:
        facts["source_updated_at"] = _scalar(record.get("updated_at"))
    return NormalizedJob(native_id, title, company, location, apply_url, description,
                         complete, published_at, facts)


def normalize_jobs(records: Any, *, source_id: str, tool: str,
                   company_fallback: str = "", max_results: int = 20) -> tuple[list[NormalizedJob], int]:
    if not isinstance(records, list):
        raise ValueError("Collector jobs field must be a list.")
    jobs: list[NormalizedJob] = []
    seen: set[str] = set()
    skipped = 0
    for record in records[: max_results * 5]:
        job = normalize_job(record, source_id=source_id, tool=tool, company_fallback=company_fallback)
        if job is None:
            skipped += 1
            continue
        if job.native_id in seen:
            skipped += 1
            continue
        seen.add(job.native_id)
        jobs.append(job)
        if len(jobs) >= max_results:
            if len(records) > len(jobs): skipped += len(records) - len(jobs)
            break
    return jobs, skipped
