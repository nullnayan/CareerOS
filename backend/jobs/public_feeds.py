"""Ongoing public access only. Rolling windows never authorize closure."""
from jobs.connectors import Listing, Snapshot, SourceError, plain_html, public_url, timestamp, request_json
from datetime import datetime, timezone


def public_feed(provider, cursor=None):
    params = {}
    if provider == "remotive":
        data = request_json("https://remotive.com/api/remote-jobs")
    elif provider == "jobicy":
        params = {"count": 100}
        if cursor: params["cursor"] = cursor
        data = request_json("https://jobicy.com/api/jobs", params)
    elif provider == "himalayas":
        params = {"limit": 20}
        if cursor: params["cursor"] = cursor
        data = request_json("https://himalayas.app/jobs/api", params)
    else:
        raise SourceError("Public feed not supported.")
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list) or data.get("success") is False:
        raise SourceError("Unexpected public-feed response; prior listings preserved.")
    jobs, skipped = [], 0
    for item in data["jobs"]:
        try:
            if provider == "himalayas":
                url = public_url(item["applicationLink"])
                guid = public_url(item["guid"])
                from urllib.parse import urlsplit
                if urlsplit(guid).hostname != "himalayas.app": raise ValueError("Unexpected source guid")
                description = plain_html(item.get("description") or item.get("excerpt", ""))
                expiry = datetime.fromtimestamp(item["expiryDate"], timezone.utc).replace(tzinfo=None)
                if expiry <= datetime.utcnow(): continue
                jobs.append(Listing(guid, str(item["title"])[:200], str(item["companyName"]),
                    "Remote - " + (", ".join(item.get("locationRestrictions") or []) or "Worldwide"), url, description,
                    bool(item.get("description")) and 100 <= len(description) < 100000, None,
                    {"employment_type": item.get("employmentType", "unknown"), "work_mode": "remote",
                     "attribution": "Himalayas", "source_url": guid, "preserve_apply_url": url,
                     "source_updated_at": item.get("pubDate"), "source_expiry_at": expiry.isoformat(),
                     "timezone_restrictions": item.get("timezoneRestrictions"),
                     "salary_max": item.get("maxSalary"), "salary_currency": item.get("currency"),
                     "salary_period": item.get("salaryPeriod")}))
                continue
            if provider == "remotive":
                native, title, company, location = item["id"], item["title"], item["company_name"], item.get("candidate_required_location", "")
                description = plain_html(item.get("description", ""))
                published, employment = item.get("publication_date"), item.get("job_type", "unknown")
            else:
                native, title, company, location = item["id"], item["jobTitle"], item["companyName"], item.get("jobGeo", "")
                description = plain_html(item.get("jobDescription") or item.get("jobExcerpt", ""))
                published, employment = item.get("pubDate"), " ".join(item.get("jobType") or [])
            url = public_url(item["url"])
            # Keep source links for attribution and free access; no commercial ATS resolution.
            from urllib.parse import urlsplit
            if urlsplit(url).hostname not in ({"remotive.com", "www.remotive.com"} if provider == "remotive" else {"jobicy.com", "www.jobicy.com"}):
                raise ValueError("Unexpected public listing URL")
            if not native or not title or not company: raise ValueError("Missing identity")
            full = bool(item.get("description" if provider == "remotive" else "jobDescription"))
            jobs.append(Listing(str(native), str(title)[:200], str(company), str(location), url, description,
                full and 100 <= len(description) < 100000, timestamp(published),
                {"employment_type": employment, "work_mode": "remote", "attribution": provider.title(),
                 "source_url": url, "publication_delay_hours": 24 if provider == "remotive" else 3,
                 "salary_max": item.get("salaryMax"), "salary_currency": item.get("salaryCurrency"),
                 "salary_period": "annual" if item.get("salaryPeriod") == "yearly" else item.get("salaryPeriod")}))
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError): skipped += 1
    next_cursor = data.get("nextCursor")
    if next_cursor is not None and (not isinstance(next_cursor, str) or len(next_cursor) > 8192):
        raise SourceError("Unexpected feed cursor.")
    warnings = ["Public feed: attribution/link-back required; no third-party syndication."]
    if next_cursor and next_cursor == cursor:
        next_cursor = None
        warnings.append("Repeated cursor; needs review.")
    return Snapshot(jobs, False, scope="rolling_feed", cursor=next_cursor, skipped=skipped, warnings=warnings,
        truncation_reason="More rolling-window pages available." if next_cursor else None)
