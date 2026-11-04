from __future__ import annotations

from datetime import date, datetime
from enum import Enum
import importlib.metadata
import ipaddress
import math
import re
import socket
from typing import Any
from urllib.parse import urlsplit

from _common import RunnerFailure, decode_cursor, serve


ISO_COUNTRY = {
    "AR": "argentina", "AU": "australia", "AT": "austria", "BH": "bahrain", "BE": "belgium",
    "BR": "brazil", "CA": "canada", "CL": "chile", "CN": "china", "CO": "colombia",
    "CR": "costa rica", "CZ": "czech republic", "DK": "denmark", "EC": "ecuador", "EG": "egypt",
    "FI": "finland", "FR": "france", "DE": "germany", "GR": "greece", "HK": "hong kong",
    "HU": "hungary", "IN": "india", "ID": "indonesia", "IE": "ireland", "IL": "israel",
    "IT": "italy", "JP": "japan", "KW": "kuwait", "LU": "luxembourg", "MY": "malaysia",
    "MX": "mexico", "MA": "morocco", "NL": "netherlands", "NZ": "new zealand", "NG": "nigeria",
    "NO": "norway", "OM": "oman", "PK": "pakistan", "PA": "panama", "PE": "peru",
    "PH": "philippines", "PL": "poland", "PT": "portugal", "QA": "qatar", "RO": "romania",
    "SA": "saudi arabia", "SG": "singapore", "ZA": "south africa", "KR": "south korea", "ES": "spain",
    "SE": "sweden", "CH": "switzerland", "TW": "taiwan", "TH": "thailand", "TR": "türkiye",
    "UA": "ukraine", "AE": "united arab emirates", "GB": "uk", "US": "usa", "UY": "uruguay",
    "VE": "venezuela", "VN": "vietnam",
}
FIXED_COUNTRIES = {"naukri": "IN", "bdjobs": "BD", "hellowork": "FR"}


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if type(value).__name__ in {"NAType", "NaTType"}:
        return None
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except (TypeError, ValueError):
            return None
    return str(value)[:2000]


def _safe_warning(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")[:500]
    text = re.sub(r"(?i)(token|api[_-]?key|authorization|cookie|password|proxy)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", text)
    text = re.sub(r"https?://[^\s]+", "[source URL]", text)
    return text


def _country(site: str, iso: str) -> str:
    iso = iso.upper()
    fixed = FIXED_COUNTRIES.get(site)
    if fixed and iso != fixed:
        raise RunnerFailure("unsupported", f"{site} is only configured for {fixed}; the request asked for {iso}.")
    if site in {"indeed", "glassdoor", "linkedin"}:
        country = ISO_COUNTRY.get(iso)
        if not country:
            raise RunnerFailure("unsupported", f"The pinned JobSpy country mapping does not include {iso}.")
        return country
    if site == "zip_recruiter" and iso not in {"US", "CA"}:
        raise RunnerFailure("unsupported", "ZipRecruiter coverage is limited to the United States and Canada.")
    if site == "bayt" and iso not in {"AE", "BH", "EG", "IQ", "JO", "KW", "LB", "LY", "MA", "OM", "QA", "SA", "TN", "YE"}:
        raise RunnerFailure("unsupported", "Bayt is limited to its supported Middle East and North Africa markets.")
    if site == "bayt" and iso not in ISO_COUNTRY:
        raise RunnerFailure("unsupported", f"The pinned JobSpy country mapping does not include Bayt market {iso}.")
    # BDJobs has a hard-coded Bangladesh scraper. This common JobSpy field
    # is ignored by it, but must still receive a valid Country enum.
    return "india" if site == "bdjobs" else ISO_COUNTRY.get(iso, iso)


def _classify_error(error_map: Any, site: str) -> tuple[str, int | None, int | None]:
    message = " ".join(str(value) for value in error_map.values()).lower() if isinstance(error_map, dict) else str(error_map).lower()
    if "429" in message or "rate limit" in message:
        return "rate_limited", 429, None
    if "401" in message or "403" in message or "blocked" in message or "forbidden" in message:
        return "blocked", 403 if "403" in message or "forbidden" in message else None, None
    if "login" in message or "sign in" in message or "authentication" in message:
        return "login_required", 401, None
    if "timeout" in message or "timed out" in message:
        return "timeout", None, None
    if "outside approved" in message or "outside the approved" in message or "proxy use is disabled" in message:
        return "blocked", None, None
    return "transport", None, None


def _scrape(site: str, role: str, location: str, country: str, offset: int,
            results_wanted: int, hours_old: int | None, fetch_description: bool):
    from jobspy import scrape_jobs
    frame = scrape_jobs(site_name=site, search_term=role, location=location,
                        distance=50, is_remote=False, results_wanted=results_wanted,
                        country_indeed=country, offset=offset, hours_old=hours_old,
                        fetch_description=fetch_description, verbose=0,
                        proxies=None, ca_cert=None)
    rows = []
    for row in frame.to_dict(orient="records"):
        rows.append({str(k): _json_value(v) for k, v in row.items()})
    attrs = getattr(frame, "attrs", {}) or {}
    errors = attrs.get("errors") or {}
    warnings = attrs.get("warnings") or {}
    warning_list = []
    if isinstance(warnings, dict):
        for source, values in warnings.items():
            if isinstance(values, (list, tuple)):
                warning_list.extend(f"{source}: {_safe_warning(item)}" for item in values)
            elif values:
                warning_list.append(f"{source}: {_safe_warning(values)}")
    elif warnings:
        warning_list.append(_safe_warning(warnings))
    return rows, errors, warning_list


def _guard_network(site: str, country: str):
    """Patch the two session implementations used by this pinned JobSpy release."""
    from requests import Session as RequestsSession
    from curl_cffi import requests as curl_requests
    from jobspy.model import Country

    suffixes = {
        "linkedin": ("linkedin.com",), "naukri": ("naukri.com",),
        "indeed": ("indeed.com",), "glassdoor": (), "zip_recruiter": ("ziprecruiter.com",),
        "bayt": ("bayt.com",), "bdjobs": ("bdjobs.com",), "hellowork": ("hellowork.com",),
    }[site]
    if site == "indeed":
        from jobspy.indeed.constant import country_codes, subdomains
        market = Country(country)
        regional = subdomains.get(market, country_codes[market].lower())
        suffixes = ("indeed.com", f"{regional}.indeed.com")
    elif site == "glassdoor":
        from jobspy.glassdoor.constant import domains
        suffixes = (domains[Country(country)],)

    budget = {"count": 0, "exceeded": False}
    maximum = 32

    def guarded(original):
        def request(session, method, url, *args, **kwargs):
            if budget["count"] >= maximum:
                budget["exceeded"] = True
                raise RuntimeError("bounded network request ceiling")
            try:
                parsed = urlsplit(str(url))
                host = (parsed.hostname or "").lower().rstrip(".")
                if parsed.scheme.lower() != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
                    raise ValueError
                if not any(host == suffix or host.endswith("." + suffix) for suffix in suffixes):
                    raise ValueError
                addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
                if not addresses or not all(ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                    raise ValueError
            except (ValueError, OSError, socket.gaierror):
                raise RuntimeError("request outside the approved public source hosts") from None
            supplied_proxies = kwargs.get("proxies")
            if supplied_proxies or getattr(session, "proxies", None):
                raise RuntimeError("proxy use is disabled for this collector")
            kwargs.pop("proxies", None)
            kwargs["allow_redirects"] = False
            timeout = kwargs.get("timeout")
            if timeout is None:
                kwargs["timeout"] = 15
            elif isinstance(timeout, (int, float)):
                kwargs["timeout"] = min(float(timeout), 15.0)
            elif isinstance(timeout, tuple):
                kwargs["timeout"] = tuple(min(float(item), 15.0) if item is not None else 15.0 for item in timeout[:2])
            if hasattr(session, "trust_env"):
                session.trust_env = False
            budget["count"] += 1
            response = original(session, method, url, *args, **kwargs)
            final_url = getattr(response, "url", url)
            final_host = (urlsplit(str(final_url)).hostname or "").lower().rstrip(".")
            if not any(final_host == suffix or final_host.endswith("." + suffix) for suffix in suffixes):
                try:
                    response.close()
                except Exception:
                    pass
                raise RuntimeError("response left the approved public source hosts")
            return response
        return request

    originals = [(RequestsSession, RequestsSession.request), (curl_requests.Session, curl_requests.Session.request)]
    for session_class, original in originals:
        session_class.request = guarded(original)
    return budget, originals


def run(request: dict[str, Any]) -> dict[str, Any]:
    site = str(request.get("source_id", "")).lower()
    if site not in {"linkedin", "naukri", "indeed", "glassdoor", "zip_recruiter", "bayt", "bdjobs", "hellowork"}:
        raise RunnerFailure("unsupported", "This JobSpy site is not supported by the pinned release.")
    country = _country(site, str(request.get("country_code", "")))
    cursor = decode_cursor(request)
    offset = int(cursor.get("offset", 0)) if isinstance(cursor, dict) else 0
    if offset < 0 or offset > 10000:
        raise RunnerFailure("invalid_output", "The requested JobSpy offset is outside the bounded result window.")
    max_results = int(request.get("max_results", 20))
    max_details = int(request.get("max_details", 0))
    hours_old = int(request["max_age_days"]) * 24 if request.get("max_age_days") else None
    budget, originals = _guard_network(site, country)
    # The pinned LinkedIn/Naukri loops stop at results_wanted before reading
    # another card. Their inline detail requests are therefore bounded when
    # every requested result fits the explicit detail budget.
    fetch_details = site in {"linkedin", "naukri"} and 0 < max_results <= max_details <= 20
    try:
        rows, errors, warnings = _scrape(site, request["role"], request["location"], country,
                                         offset, max_results, hours_old, fetch_details)
    finally:
        for session_class, original in originals:
            session_class.request = original
    for row in rows:
        row["description_complete"] = bool(fetch_details and len(str(row.get("description") or "")) >= 50)
    if max_details and not fetch_details:
        warnings.append("Description retrieval needs a supported site and a result window no larger than its detail budget; these records remain excerpts.")
    if budget["exceeded"]:
        warnings.append("The hard outbound request ceiling stopped additional requests.")
    if errors and not rows:
        if budget["exceeded"]:
            raise RunnerFailure("timeout", f"{site} reached its bounded outbound request ceiling.")
        reason, status, retry = _classify_error(errors, site)
        raise RunnerFailure(reason, f"{site} did not return usable results; source access or transport failed.", status, retry)
    try:
        version = importlib.metadata.version("python-jobspy")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    if not rows and not errors:
        warnings.append("JobSpy returned no records and no explicit empty-results marker; coverage is unknown.")
    if site == "bdjobs":
        warnings.append("The pinned BDJobs scraper hardcodes Bangladesh; JobSpy's shared country enum is only an internal compatibility value here.")
    return {"jobs": rows, "upstream_errors": {str(k): _safe_warning(v) for k, v in (errors.items() if isinstance(errors, dict) else [])},
            "warnings": warnings[:40], "tool_version": version,
            "offset": offset, "requested": max_results, "request_count": budget["count"]}


if __name__ == "__main__":
    serve(run)
