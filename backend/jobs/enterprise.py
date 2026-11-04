"""Explicit employer connections; no tenant guessing or account access.

Workday CXS is a public career-site transport, NOT a supported Workday API.
Its implementation is fixture-tested; each employer still needs access review.
Other enterprise families consume only an employer-published feed.
"""
import hashlib
import json
import re
import time
from urllib.parse import urlsplit
from jobs.connectors import Listing, Snapshot, SourceError, plain_html
from jobs.feed_transport import feed_url, fetch_public_feed, request_public
from jobs.structured_feeds import parse_feed

FEED_PROVIDERS = {"taleo", "sap_successfactors", "oracle_recruiting", "icims"}
PROVIDERS = FEED_PROVIDERS | {"workday"}


def workday_site(value):
    value = feed_url(value)
    parsed = urlsplit(value)
    if not re.fullmatch(r"[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com", parsed.hostname or ""):
        raise ValueError("Use the exact employer's external myworkdayjobs.com career-site URL.")
    parts = parsed.path.strip("/").split("/")
    if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]): parts.pop(0)
    if len(parts) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", parts[0]) or parsed.query:
        raise ValueError("Supply a career-site root, not a job, login, search, or API URL.")
    return "https://" + parsed.hostname + "/" + parts[0]


def configuration(provider, url, full=False):
    if provider not in PROVIDERS: raise ValueError("Choose a supported enterprise route.")
    if provider == "workday":
        return {"site_url": workday_site(url), "access_reviewed": True}
    return {"feed_url": feed_url(url), "format": "xml" if provider == "taleo" else "auto",
            "full_descriptions": bool(full) and provider != "taleo", "access_reviewed": True}


def fetch(provider, company, config, cursor=None):
    if not config.get("access_reviewed"):
        raise SourceError("Employer public-access review is required before collection.", status_code=403)
    if provider == "workday": return workday(company, config, cursor)
    result = parse_feed(fetch_public_feed(config["feed_url"]), company, config, cursor)
    for job in result.jobs:
        job.facts.update(source_family=provider, access_route="employer_published_feed", feed_url=config["feed_url"])
    if provider == "taleo": result.warnings.append("Taleo RSS is a search window of up to 10 excerpts; it is not the employer's complete catalogue.")
    return result


def workday(company, config, cursor=None):
    site = workday_site(config["site_url"])
    parsed = urlsplit(site)
    tenant = parsed.hostname.split(".")[0]
    base = "https://" + parsed.hostname + "/wday/cxs/" + tenant + parsed.path
    offset, previous, expected = 0, [], 0
    if cursor:
        try:
            state = json.loads(cursor)
            offset, previous = state["offset"], state["pages"]
            expected = state.get("total", 0)
            if type(expected) is not int or expected < 0: raise ValueError()
            if type(offset) is not int or offset < 0 or not isinstance(previous, list) or len(previous) > 100:
                raise ValueError()
        except (ValueError, TypeError, KeyError): raise SourceError("Invalid Workday checkpoint.") from None
    deadline = time.monotonic() + 75
    class BudgetReached(SourceError):
        pass
    def request(url, payload=None):
        if time.monotonic() >= deadline: raise BudgetReached("Workday execution budget reached; checkpoint retained.")
        try: return json.loads(request_public(url, payload=payload))
        except (ValueError, UnicodeError): raise SourceError("Unexpected Workday JSON response; existing jobs preserved.") from None
    # Eight details plus one search request, at most; scheduler paces pages.
    data = request(base + "/jobs", {"appliedFacets": {}, "limit": 8, "offset": offset, "searchText": ""})
    if not isinstance(data, dict) or not isinstance(data.get("jobPostings"), list) or type(data.get("total")) is not int or data["total"] < 0:
        raise SourceError("Unexpected Workday search schema; existing jobs preserved.")
    rows = data["jobPostings"]
    if len(rows) > 8: raise SourceError("Unexpected Workday page size; checkpoint retained.")
    if not rows:
        # Empty success can be a silent provider block. Never use it for closure.
        return Snapshot([], False, scope="rolling_feed", warnings=["Empty Workday response is unconfirmed coverage, not evidence that no jobs exist."],
                        truncation_reason="Empty response requires source review.")
    paths = [row.get("externalPath") if isinstance(row, dict) else None for row in rows]
    if any(not isinstance(path, str) or not re.fullmatch(r"/job/[A-Za-z0-9_./%~-]+", path) or ".." in path for path in paths):
        raise SourceError("Unexpected Workday job path; no supplied links were followed.")
    signature = hashlib.sha256(json.dumps(paths).encode()).hexdigest()
    if signature in previous or len(set(paths)) != len(paths):
        raise SourceError("Repeated Workday page; pagination stopped and existing jobs preserved.")
    jobs, skipped, processed = [], 0, 0
    for row, path in zip(rows, paths):
        try:
            detail = request(base + path)
        except BudgetReached:
            break
        info = detail.get("jobPostingInfo") if isinstance(detail, dict) else None
        if not isinstance(info, dict): raise SourceError("Unexpected Workday detail schema; checkpoint retained.")
        processed += 1
        native, title = info.get("jobReqId"), info.get("title")
        description = plain_html(info.get("jobDescription") or "")
        if not native or not isinstance(title, str) or not title.strip() or not description:
            skipped += 1; continue
        facts = {"source_family": "workday", "access_route": "public_career_site_cxs", "source_url": site + path,
                 "attribution": company, "employment_type": info.get("timeType", "unknown"),
                 "secondary_locations": info.get("additionalLocations", []), "source_start_date": info.get("startDate"),
                 "source_posted_label": row.get("postedOn"), "publication_date_unknown": True}
        # startDate and relative postedOn are not guaranteed publication dates.
        jobs.append(Listing(str(native), title.strip()[:200], company, str(info.get("location") or row.get("locationsText") or ""),
                            site + path, description, 100 <= len(description) < 100000, None, facts))
    end = offset + processed
    total = max(expected, data["total"])
    # Keep the returned window signature even after partial progress: a source
    # ignoring the next offset must still be detected. With no processed rows,
    # leave history unchanged so the same window can be retried.
    history = previous + ([signature] if processed else [])
    # Keep the initial page plus recent signatures to catch capped endpoints
    # looping to page one, without imposing a lifetime catalogue-size quota.
    if len(history) > 100: history = [history[0], *history[-99:]]
    token = json.dumps({"offset": end, "pages": history, "total": total}) if processed < len(rows) or end < total else None
    # Public CXS totals can be capped or change mid-scan. Never infer closure.
    return Snapshot(jobs, False, scope="rolling_feed", cursor=token, skipped=skipped,
                    truncation_reason="Execution budget reached; remaining details will resume." if processed < len(rows) else
                    "More employer pages remain." if token else "Public career-site window; closure unconfirmed.")
