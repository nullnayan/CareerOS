from __future__ import annotations

from pathlib import Path
import ipaddress
import re
import socket
import sys
from typing import Any
from urllib.parse import urlsplit

from _common import RunnerFailure, decode_cursor, serve


REPO_ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOT = REPO_ROOT / "oss-tools" / "runtime" / "sources"
ROOTS = {
    "instahyre": SOURCE_ROOT / "instahyre-scraper",
    "internshala": SOURCE_ROOT / "internshala-scraper",
    "shine": SOURCE_ROOT / "shine-scraper",
}


def _page(request: dict[str, Any], page: int) -> dict[str, Any]:
    source_id = request["source_id"]
    role, location = request["role"], request["location"]
    if source_id == "instahyre":
        from instahyre import jobs
        # This endpoint searches skills, not job-title phrases. Broad software
        # roles must not be sent as an exact skill called 'software engineer'.
        skill = None if re.search(r"\b(?:engineer|developer)\b", role, re.I) else role
        city = None if location.strip().lower() == "india" else location
        result = jobs.search(query=skill, location=city, page=page, include_details=False)
        rows = result.get("jobs") if isinstance(result, dict) else None
        pagination = (result or {}).get("pagination", {})
        total_pages = pagination.get("total_pages") if isinstance(pagination, dict) else None
        if not isinstance(rows, list) or not isinstance(total_pages, int):
            raise RunnerFailure("changed_format", "Instahyre returned an unrecognized jobs page.")
        return {"jobs": rows, "has_more": page < total_pages, "next_page": page + 1 if page < total_pages else None}

    if source_id in {"internshala_jobs", "internshala_internships"}:
        if str(request.get("country_code", "")).upper() != "IN":
            raise RunnerFailure("unsupported", "Internshala's local board is India-specific.")
        from internshala import listings
        if source_id == "internshala_internships":
            result = listings.internships(query=role, location=location, page=page)
            rows = result.get("internships") if isinstance(result, dict) else None
        else:
            result = listings.jobs(query=role, location=location, experience="fresher", page=page)
            rows = result.get("jobs") if isinstance(result, dict) else None
        pagination = (result or {}).get("pagination", {})
        if not isinstance(rows, list) or not isinstance(pagination, dict) or not isinstance(pagination.get("is_last_page"), bool):
            raise RunnerFailure("changed_format", "Internshala returned an unrecognized jobs page.")
        return {"jobs": rows, "has_more": not pagination["is_last_page"],
                "next_page": page + 1 if not pagination["is_last_page"] else None}

    if source_id == "shine":
        from shine import jobs
        page_size = min(50, max(1, int(request.get("max_results", 20))))
        result = jobs.search(query=role, location=location, page=page, page_size=page_size,
                             posted_within_days=request.get("max_age_days"), include_description=False)
        rows = result.get("jobs") if isinstance(result, dict) else None
        pagination = (result or {}).get("pagination", {})
        total_pages = pagination.get("total_pages") if isinstance(pagination, dict) else None
        if not isinstance(rows, list) or not isinstance(total_pages, int):
            raise RunnerFailure("changed_format", "Shine returned an unrecognized jobs page.")
        return {"jobs": rows, "has_more": page < total_pages, "next_page": page + 1 if page < total_pages else None}
    raise RunnerFailure("unsupported", "No local OmkarCloud implementation exists for this source.")


def _detail(request: dict[str, Any], row: dict[str, Any]) -> dict[str, Any] | None:
    source_id = request["source_id"]
    if source_id == "instahyre":
        from instahyre import jobs
        detail = jobs.details(row.get("id"), include_company=False)
        return detail if isinstance(detail, dict) else None
    if source_id == "shine":
        from shine import jobs
        detail = jobs.details(row.get("id"))
        return detail if isinstance(detail, dict) else None
    if source_id in {"internshala_jobs", "internshala_internships"}:
        from internshala import details
        link = str(row.get("link") or "")
        match = re.search(r"https://(?:www\.)?internshala\.com/(internship|job)/detail/([^/?#]+)", link)
        if not match:
            return None
        kind = match.group(1)
        ref = {"kind": kind, "slug": match.group(2)}
        detail = details.internship(ref) if kind == "internship" else details.job(ref)
        return detail if isinstance(detail, dict) else None
    return None


def _clean(row: dict[str, Any], source_id: str) -> dict[str, Any]:
    clean = dict(row)
    clean["source_url"] = clean.get("link") or clean.get("url")
    clean.setdefault("apply_url", clean.get("link") or clean.get("url"))
    clean["description_complete"] = bool(clean.get("description_complete"))
    # Recruiter names, contact details and profile data are not part of the
    # jobs catalogue, even when upstream detail shapes include them.
    for key in ("recruiter", "recruiter_name", "recruiter_email", "recruiter_phone",
                "email", "phone", "phone_number", "recruiter_profile_url"):
        clean.pop(key, None)
    if source_id.startswith("internshala"):
        if isinstance(clean.get("stipend"), dict):
            clean["salary"] = clean["stipend"]
        clean["employment_type"] = "internship" if source_id.endswith("internships") else clean.get("employment_type", "full_time")
    if source_id == "instahyre" and clean.get("is_internship"):
        clean["employment_type"] = "internship"
    return clean


def _guard_shine_requests(tool="shine"):
    """Restrict the local Shine client to public HTTPS hosts with no proxy/redirect."""
    from curl_cffi import requests as curl_requests

    original = curl_requests.Session.request
    domain = {"shine": "shine.com", "instahyre": "instahyre.com", "internshala": "internshala.com"}[tool]
    budget = {"count": 0, "exceeded": False, "outside": False}
    maximum = 24

    def guarded(session, method, url, *args, **kwargs):
        if budget["count"] >= maximum:
            budget["exceeded"] = True
            raise RuntimeError("bounded network request ceiling")
        try:
            parsed = urlsplit(str(url))
            host = (parsed.hostname or "").lower().rstrip(".")
            if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password or parsed.port not in (None, 443):
                raise ValueError
            if host != domain and not host.endswith("." + domain):
                raise ValueError
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            if not addresses or not all(ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                raise ValueError
        except (ValueError, OSError, socket.gaierror):
            budget["outside"] = True
            raise RuntimeError("request outside approved public Shine hosts") from None
        if kwargs.get("proxies") or getattr(session, "proxies", None):
            raise RuntimeError("proxy use is disabled for this collector")
        kwargs.pop("proxies", None)
        kwargs["allow_redirects"] = False
        timeout = kwargs.get("timeout")
        if timeout is None:
            kwargs["timeout"] = 12
        elif isinstance(timeout, (int, float)):
            kwargs["timeout"] = min(float(timeout), 12.0)
        budget["count"] += 1
        response = original(session, method, url, *args, **kwargs)
        final_host = (urlsplit(str(getattr(response, "url", url))).hostname or "").lower().rstrip(".")
        if final_host != domain and not final_host.endswith("." + domain):
            try:
                response.close()
            except Exception:
                pass
            budget["outside"] = True
            raise RuntimeError("response left approved Shine hosts")
        return response

    curl_requests.Session.request = guarded
    return budget, original


def run(request: dict[str, Any]) -> dict[str, Any]:
    tool = request.get("tool")
    source_id = request.get("source_id")
    if tool not in ROOTS or source_id not in {"instahyre", "internshala_jobs", "internshala_internships", "shine"}:
        raise RunnerFailure("unsupported", "This OmkarCloud source is not registered for local collection.")
    if source_id.startswith("internshala"):
        raise RunnerFailure("blocked", "Source terms reviewed for Part 1 restrict automated data mining and copying; a permitted export or agreement is required.")
    # The direct local HTTP functions are used; demo route modules and every
    # RapidAPI hostname are intentionally absent from this runner.
    source_root = ROOTS[tool]
    if not source_root.is_dir():
        raise RunnerFailure("runtime_missing", "Pinned local source checkout is missing.")
    sys.path.insert(0, str(source_root))
    if tool == "instahyre":
        import config
        config.INSTAHYRE_PROXY = None
        config.INSTAHYRE_ALLOW_DIRECT = True
        config.INSTAHYRE_MAX_ATTEMPTS = 1
        config.INSTAHYRE_WORKERS = 1
        from instahyre import fetch
        fetch.config = config
    elif tool == "internshala":
        import config
        config.INTERNSHALA_PROXY = None
        config.INTERNSHALA_MAX_ATTEMPTS = 1
        config.INTERNSHALA_WORKERS = 1
        from internshala import fetch
        fetch.config = config
    elif tool == "shine":
        import config
        config.SHINE_PROXY = None
        config.SHINE_MAX_ATTEMPTS = 1
        config.SHINE_BATCH_WORKERS = 1
        config.SHINE_BROWSER_FALLBACK = False
        from shine import fetch
        fetch.config = config

    from _common import decode_cursor
    state = decode_cursor(request)
    page = int(state.get("page", 1))
    if page < 1 or page > 500:
        raise RunnerFailure("invalid_output", "Source pagination exceeds the pinned page limit.")
    network_budget = None
    original_request = None
    if tool in {"shine", "instahyre"}:
        network_budget, original_request = _guard_shine_requests(tool) if tool != "shine" else _guard_shine_requests()
    detail_errors = 0
    clean_rows = []
    try:
        result = _page(request, page)
        rows = result["jobs"]
        if not rows and result.get("has_more") is True:
            raise RunnerFailure("changed_format", "The source returned an empty page while claiming more results.")
        max_details = min(int(request.get("max_details", 0)), len(rows), 8)
        item_offset = int(state.get("item_offset", 0))
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            item = dict(row)
            if item_offset <= index < item_offset + max_details:
                try:
                    detail = _detail(request, item)
                    if detail:
                        merged = {**item, **detail}
                        if detail.get("description_text") and not detail.get("description"):
                            merged["description"] = detail["description_text"]
                        if detail.get("description_html") and not detail.get("description"):
                            merged["description"] = detail["description_html"]
                        merged["description_complete"] = bool(merged.get("description"))
                        item = merged
                    else:
                        detail_errors += 1
                except Exception:
                    detail_errors += 1
                    if network_budget and (network_budget["exceeded"] or network_budget["outside"]):
                        max_details = 0
            clean_rows.append(_clean(item, source_id))
    except RunnerFailure:
        raise
    except Exception:
        if network_budget and network_budget["exceeded"]:
            raise RunnerFailure("timeout", "The local Shine client reached its bounded request ceiling.") from None
        if network_budget and network_budget["outside"]:
            raise RunnerFailure("blocked", "The local Shine client attempted to leave its approved public HTTPS hosts.") from None
        raise
    finally:
        if original_request is not None:
            from curl_cffi import requests as curl_requests
            curl_requests.Session.request = original_request
    warnings = []
    if detail_errors:
        warnings.append(f"{detail_errors} optional detail lookups failed; those records remain excerpts.")
    if network_budget and network_budget["exceeded"]:
        warnings.append("The hard Shine request ceiling was reached; remaining details were not fetched.")
    if network_budget and network_budget["outside"]:
        warnings.append("An out-of-domain detail request was blocked; affected descriptions remain excerpts.")
    return {"jobs": clean_rows, "has_more": bool(result.get("has_more")),
            "next_page": result.get("next_page"), "warnings": warnings,
            "tool_version": None, "page": page,
            "request_count": network_budget["count"] if network_budget else 0}


if __name__ == "__main__":
    serve(run)
