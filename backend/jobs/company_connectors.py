"""Documented public company boards; fixed hosts, bounded work, no credentials."""
from urllib.parse import quote
from jobs.connectors import Listing, Snapshot, SourceError, plain_html, public_url, timestamp, request_json


def _listing(item, native, title, company, location, url, description, published=None, facts=None):
    if not native or not title or not url:
        raise ValueError("Missing listing identity")
    text = plain_html(description)
    return Listing(str(native), str(title)[:200], company, str(location), public_url(url), text,
                   100 <= len(text) < 100000, timestamp(published), facts or {})


def ashby(board, company):
    data = request_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}", {"includeCompensation": "true"})
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise SourceError("Unexpected Ashby response.")
    jobs, skipped = [], 0
    for item in data["jobs"]:
        try:
            if item.get("isListed") is False: continue
            compensation = item.get("compensation") or {}
            components = [part for part in compensation.get("summaryComponents", []) if isinstance(part, dict) and part.get("compensationType") == "Salary"]
            pay = {}
            if len(components) == 1:
                part = components[0]
                pay = {"salary_min": part.get("minValue"), "salary_max": part.get("maxValue"), "salary_currency": part.get("currencyCode"),
                       "salary_period": {"1 YEAR": "annual", "1 MONTH": "monthly"}.get(part.get("interval"), "unknown")}
            jobs.append(_listing(item, item.get("id") or item.get("jobUrl"), item.get("title"), company,
                item.get("location", ""), item.get("applyUrl") or item.get("jobUrl"),
                item.get("descriptionPlain") or item.get("descriptionHtml", ""), item.get("publishedAt"),
                {"employment_type": item.get("employmentType", "unknown"), "work_mode": item.get("workplaceType", "unknown"),
                 "secondary_locations": item.get("secondaryLocations", []), **pay}))
        except (ValueError, TypeError, AttributeError): skipped += 1
    return Snapshot(jobs, not skipped, skipped=skipped)


def workable(board, company):
    data = request_json(f"https://www.workable.com/api/accounts/{board}", {"details": "true"})
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise SourceError("Unexpected Workable response.")
    jobs, skipped = [], 0
    for item in data["jobs"]:
        try:
            location = item.get("location") or {}
            text = "\n\n".join(str(item.get(key) or "") for key in ("description", "requirements", "benefits"))
            jobs.append(_listing(item, item.get("shortcode") or item.get("id"), item.get("title"), company,
                location.get("location_str") or ", ".join(str(location[k]) for k in ("city", "country") if location.get(k)),
                item.get("application_url") or item.get("shortlink") or item.get("url"), text,
                # created_at need not be the publication date.
                facts={"source_created_at": item.get("created_at"), "employment_type": item.get("employment_type", "unknown"),
                       "work_mode": location.get("workplace_type", "unknown")}))
        except (ValueError, TypeError, AttributeError): skipped += 1
    return Snapshot(jobs, not skipped, skipped=skipped)


def smartrecruiters(board, company, *, offset=0, max_pages=2, max_details=40):
    """Bound detail requests; continuation never closes unseen jobs."""
    jobs, seen, skipped, pages = [], set(), 0, 0
    base = f"https://api.smartrecruiters.com/v1/companies/{board}/postings"
    for _ in range(max_pages):
        data = request_json(base, {"limit": min(20, max_details - len(jobs)), "offset": offset})
        pages += 1
        if not isinstance(data, dict) or not isinstance(data.get("content"), list) or not isinstance(data.get("totalFound"), int):
            raise SourceError("Unexpected SmartRecruiters response.")
        content = data["content"]
        for item in content:
            native = item.get("id") if isinstance(item, dict) else None
            if not native or str(native) in seen:
                return Snapshot(jobs, False, pages=pages, skipped=skipped + 1,
                                truncation_reason="Malformed identity or repeated page; review required.")
            seen.add(str(native))
            # Rebuild from the validated board/native ID, never follow supplied ref.
            detail = request_json(base + "/" + quote(str(native), safe=""))
            try:
                sections = (detail.get("jobAd") or {}).get("sections") or {}
                description = "\n\n".join(str(block.get("text") or "") for block in sections.values() if isinstance(block, dict))
                location = detail.get("location") or {}
                jobs.append(_listing(detail, native, detail.get("name"), company,
                    ", ".join(str(location[k]) for k in ("city", "region", "country") if location.get(k)),
                    detail.get("applyUrl") or "https://jobs.smartrecruiters.com/" + board + "/" + quote(str(native), safe=""),
                    description, detail.get("releasedDate"),
                    {"employment_type": (detail.get("typeOfEmployment") or {}).get("label", "unknown"),
                     "work_mode": "remote" if location.get("remote") else "unknown"}))
            except (ValueError, TypeError, AttributeError): skipped += 1
            offset += 1
            if len(jobs) >= max_details: break
        if offset >= data["totalFound"]:
            return Snapshot(jobs, not skipped, pages=pages, skipped=skipped, traversal_valid=not skipped, traversal_end=True)
        if not content: return Snapshot(jobs, False, pages=pages, truncation_reason="Empty page before reported total.")
        if len(jobs) >= max_details: break
    return Snapshot(jobs, False, pages=pages, cursor=str(offset), skipped=skipped, truncation_reason="Execution detail/page budget; continue from offset.", traversal_valid=not skipped)


COMPANY_ADAPTERS = {"ashby": ashby, "smartrecruiters": smartrecruiters, "workable": workable}
