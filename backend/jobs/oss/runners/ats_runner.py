from __future__ import annotations

import asyncio
import hashlib
import json
import base64
import zlib
import os
import time
from pathlib import Path
import importlib.metadata
import ipaddress
import re
import socket
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from _common import RunnerFailure, serve, decode_cursor


from ats_scrapers.exceptions import ScraperError


class RequestBudgetReached(ScraperError):
    pass


class BoundaryViolation(ScraperError):
    pass


def _host_allowed(url: str, suffixes: tuple[str, ...]) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        if any(re.search(r"(?:access[_-]?token|api[_-]?key|authorization|auth[_-]?token|client[_-]?secret|cookie|password|session(?:id)?|signature|^sig$|^token$|^key$)", key, re.I)
               for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
            return False
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_global and not suffixes
        except ValueError:
            pass
        if not any(host == suffix or host.endswith("." + suffix) for suffix in suffixes):
            return False
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (ValueError, OSError, socket.gaierror):
        return False


def _matches(job: Any, role: str, location: str) -> bool:
    title = str(getattr(job, "title", "") or "").casefold()
    description = str(getattr(job, "description", "") or "").casefold()
    location_value = str(getattr(job, "location", "") or "").casefold()
    terms = [part for part in re.findall(r"[a-zA-Z0-9+#.]{3,}", role.casefold()) if part not in {"the", "and", "for", "with"}]
    role_match = not terms or any(term in title or term in description[:20000] for term in terms)
    loc_terms = [part.strip().casefold() for part in re.split(r"[,/|]", location) if len(part.strip()) >= 2]
    # India queries often return just a city name. Keep country-wide matches
    # for CareerOS's existing country/city eligibility checks rather than
    # falsely dropping Bengaluru because it does not contain "India".
    location_match = not loc_terms or loc_terms == ["india"] or not location_value or any(term in location_value for term in loc_terms) or "remote" in location_value
    return role_match and location_match


def _snapshot_jobs(request, scraper):
    """Page a bounded immutable local snapshot instead of refetching a board.

    Source adapters have no shared cursor API. A versioned cache retains the
    actual fetched catalogue for one hour; expiry restarts rather than skips.
    """
    from ats_scrapers.models import Job
    state = decode_cursor(request)
    root = Path(__file__).resolve().parents[4] / "oss-tools" / "runtime" / "ats-snapshots"
    root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps([request["entry_url"], request.get("query_fingerprint"), "ats-0.3.0-compact"], sort_keys=True).encode()).hexdigest()
    path = root / (key + ".json")
    cached = None
    if path.is_file() and path.stat().st_size <= 16_000_000 and time.time() - path.stat().st_mtime < 3600:
        try: cached = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError): pass
    if cached and (not state.get("snapshot") or state["snapshot"] == cached.get("version")):
        data = cached.get("jobs")
        if cached.get("encoding") == "zlib":
            decoded = zlib.decompressobj().decompress(base64.b64decode(cached["jobs_z"]), 64_000_001)
            if len(decoded) > 64_000_000: raise RunnerFailure("invalid_output", "Cached ATS snapshot exceeds its decompression budget.")
            data = json.loads(decoded)
        return [Job.model_validate(row) for row in data], int(state.get("offset", 0)), cached["version"], True
    jobs = [job for job in asyncio.run(scraper.afetch()) if _matches(job, request["role"], request["location"])]
    data = [job.model_dump(mode="json", exclude={"raw"}) for job in jobs]
    encoded = json.dumps(data, separators=(",", ":"))
    version = hashlib.sha256(encoded.encode()).hexdigest()
    encoded_bytes = encoded.encode()
    if len(encoded_bytes) > 64_000_000:
        raise RunnerFailure("unsupported", "The matching ATS snapshot exceeds the local size budget; narrow the query.")
    stored = {"version": version, "jobs": data}
    if len(encoded_bytes) > 12_000_000:
        stored = {"version": version, "encoding": "zlib", "jobs_z": base64.b64encode(zlib.compress(encoded_bytes, 3)).decode()}
    serialized = json.dumps(stored, separators=(",", ":"))
    if len(serialized.encode()) > 15_000_000: raise RunnerFailure("unsupported", "Compressed ATS snapshot exceeds its disk budget; narrow the query.")
    # Keep disk use bounded and never follow a cache-supplied path.
    files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for old in files:
        if len(files) <= 12 and time.time() - old.stat().st_mtime < 3600: break
        old.unlink(missing_ok=True); files = files[1:]
    temporary = root / (key + f".{os.getpid()}.tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(path)
    return jobs, 0, version, False


def run(request: dict[str, Any]) -> dict[str, Any]:
    url = request.get("entry_url")
    if not isinstance(url, str):
        raise RunnerFailure("unsupported", "ats-scrapers needs an explicit public careers URL.")
    from ats_scrapers import get_scraper_for_url, resolve_careers_url
    resolved = resolve_careers_url(url)
    custom_sites = {"careers.wipro.com": "successfactors", "southasiacareers.deloitte.com": "successfactors"}
    host = (urlsplit(url).hostname or "").lower()
    explicit_ats = custom_sites.get(host)
    if resolved is None and not explicit_ats:
        raise RunnerFailure("unsupported", "The public careers URL does not match a local ats-scrapers adapter.")
    ats = explicit_ats or resolved.ats.value
    suffixes_by_ats = {
        "greenhouse": ("greenhouse.io",), "lever": ("lever.co",), "ashby": ("ashbyhq.com",),
        "workable": ("workable.com",), "smartrecruiters": ("smartrecruiters.com",),
        "workday": ("myworkdayjobs.com",), "successfactors": ("successfactors.eu", "successfactors.com", "sapsf.eu", "sapsf.com", "jobs2web.com", "careers.wipro.com", "southasiacareers.deloitte.com"),
        "oracle": ("oraclecloud.com", "oracle.com"), "icims": ("icims.com",), "taleo": ("taleo.net",),
        "adp": ("adp.com",), "jobvite": ("jobvite.com",), "amazon": ("amazon.jobs",),
        "apple": ("apple.com",), "google": ("google.com",), "bytedance": ("bytedance.com",),
        "tesla": ("tesla.com",), "tiktok": ("tiktok.com",), "uber": ("uber.com",),
    }
    suffixes = suffixes_by_ats.get(ats)
    if not suffixes or not _host_allowed(url, suffixes):
        raise RunnerFailure("unsupported", "The careers URL is outside the pinned adapter's approved host boundary.")
    import ats_scrapers.fetch as fetch_module
    from ats_scrapers.fetch import Fetcher

    request_budget = {"count": 0}
    max_requests = 24
    original_perform = Fetcher._perform

    async def guarded_perform(self, method, destination, **kwargs):
        request_budget["count"] += 1
        if request_budget["count"] > max_requests:
            raise RequestBudgetReached("bounded request ceiling")
        if not _host_allowed(destination, suffixes):
            raise BoundaryViolation("blocked destination")
        self.follow_redirects = False
        self.proxy = None
        self._retries = 1
        self._retry_base_delay = 0.0
        self._max_retry_delay = 0.0
        response = await original_perform(self, method, destination, **kwargs)
        if destination.endswith("/sitemal.xml") and not re.search(r"<(?:rss|feed|Job-Listing)\b", response.text[:4000], re.I):
            raise RunnerFailure("changed_format", "The advertised ATS feed did not contain a recognized job-feed document.")
        return response

    Fetcher._perform = guarded_perform
    fetch_module.DEFAULT_RETRIES = 1
    fetch_module.DEFAULT_RETRY_BASE_DELAY = 0.0
    fetch_module.DEFAULT_MAX_RETRY_DELAY = 0.0
    try:
        options = dict(timeout=min(20.0, float(request.get("deadline_seconds", 60))), include_descriptions=False, proxy=None)
        if explicit_ats:
            from ats_scrapers.scrapers import get_scraper
            scraper = get_scraper(explicit_ats, url, **options)
        else: scraper = get_scraper_for_url(url, **options)
        try:
            jobs, offset, snapshot_version, from_cache = _snapshot_jobs(request, scraper)
        except RequestBudgetReached:
            raise RunnerFailure("timeout", "ATS adapter reached its bounded request ceiling; narrow the company board or use a source with resumable paging.") from None
        except BoundaryViolation:
            raise RunnerFailure("blocked", "The ATS adapter attempted a redirect or request outside its approved public hosts.") from None
        matched = jobs
        if not 0 <= offset <= len(matched): raise RunnerFailure("invalid_output", "Invalid ATS snapshot offset.")
        selected = matched[offset:offset + int(request.get("max_results", 20))]
        detail_jobs = selected[: int(request.get("max_details", 0))]
        complete_ids = set()
        detail_failures = 0
        for job in detail_jobs:
            try:
                description = scraper.get_description(job)
                if description:
                    job.description = description
                    complete_ids.add(str(getattr(job, "ats_id", None) or getattr(job, "global_id", None) or id(job)))
            except Exception:
                detail_failures += 1
        records = []
        for job in selected:
            try:
                record = job.model_dump(mode="json")
            except Exception:
                record = dict(getattr(job, "__dict__", {}))
            record["source_url"] = record.get("url")
            record["apply_url"] = record.get("apply_url") or record.get("url")
            identity = str(getattr(job, "ats_id", None) or getattr(job, "global_id", None) or id(job))
            record["description_complete"] = identity in complete_ids
            records.append(record)
        version = importlib.metadata.version("ats-scrapers")
        end = offset + len(selected)
        was_truncated = len(matched) > end
        warnings = ["Paging a one-hour local ATS snapshot; source acquisition capped at 24 requests."]
        warnings.append("Cached catalogue reused; details checked in this batch." if from_cache else "Fresh source snapshot acquired; expired or replaced snapshots restart from row zero.")
        if was_truncated:
            warnings.append("More matching snapshot rows remain for continuation.")
        if len(detail_jobs) < len(selected):
            warnings.append("Only max_details records were eligible for description retrieval.")
        if detail_failures:
            warnings.append(f"{detail_failures} optional description lookups failed; those records remain excerpts.")
        return {"jobs": records, "warnings": warnings, "skipped": 0,
                "coverage": "partial" if was_truncated else "exhausted",
                "next_state": {"offset": end, "snapshot": snapshot_version} if was_truncated else None,
                "request_count": request_budget["count"], "tool_version": version,
                "ats": ats, "slug": resolved.slug if resolved else url}
    finally:
        Fetcher._perform = original_perform


if __name__ == "__main__":
    serve(run)
