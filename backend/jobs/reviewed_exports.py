"""Offline JobSpy-compatible exports; never imports or executes a scraper.

Users supply records they may import, preview them, then select rows explicitly.
The community package's site support is not a permission or live health claim.
"""
import csv
import hashlib
import io
import json
from urllib.parse import urlsplit
from jobs.connectors import Listing, SourceError, canonical_url, plain_html, public_url, timestamp

SITES = {
    "linkedin": ("linkedin.com", "global; listing restrictions apply"),
    "indeed": ("indeed.com", "country-specific; listing restrictions apply"),
    "glassdoor": ("glassdoor.com", "country-specific; listing restrictions apply"),
    "zip_recruiter": ("ziprecruiter.com", "US and Canada"),
    "bayt": ("bayt.com", "source-dependent Middle East and other countries"),
    "naukri": ("naukri.com", "India"),
    "bdjobs": ("bdjobs.com", "Bangladesh"),
    "hellowork": ("hellowork.com", "France"),
}


def preview(content, format):
    if len(content.encode()) > 2_000_000: raise ValueError("Export exceeds the 2 MB review limit.")
    try:
        if format == "csv":
            reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
            records = []
            for row in reader:
                records.append(row)
                if len(records) > 200: raise ValueError("Review at most 200 records at a time; split this export.")
        else:
            records = json.loads(content)
            if not isinstance(records, list) or len(records) > 200:
                raise ValueError("Supply an array of at most 200 export records.")
    except (json.JSONDecodeError, csv.Error, RecursionError): raise ValueError("Invalid export format or excessive nesting.") from None
    result, errors, seen = [], [], set()
    for index, row in enumerate(records):
        try:
            job = normalized(row)
            identity = (row["site"], canonical_url(job.apply_url))
            if identity in seen:
                errors.append({"row": index, "message": "Duplicate source URL in this export."}); continue
            seen.add(identity)
            result.append({"row": index, "site": row["site"], "title": job.title, "company": job.company,
                           "location": job.location, "url": job.apply_url, "description": job.description,
                           "description_complete": False, "geography": SITES[row["site"]][1]})
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            errors.append({"row": index, "message": str(exc) if isinstance(exc, ValueError) else "Malformed export record."})
    return {"items": result, "errors": errors, "total_rows": len(records),
            "note": "Offline reviewed import only. JobSpy is not installed or run. Descriptions remain excerpts unless explicitly confirmed complete."}


def normalized(row, full=False):
    if not isinstance(row, dict) or row.get("site") not in SITES: raise ValueError("Unsupported or missing export site.")
    site = row["site"]
    # Use the board URL, not a redirect supplied by an untrusted exporter.
    url = public_url(str(row.get("job_url") or ""))
    host = urlsplit(url).hostname
    domain = SITES[site][0]
    allowed = {domain}
    if site == "glassdoor": allowed.update({"glassdoor.co.in", "glassdoor.co.uk", "glassdoor.ca", "glassdoor.fr", "glassdoor.de", "glassdoor.com.au"})
    if not any(host == d or host.endswith("." + d) for d in allowed): raise ValueError("Job URL does not belong to the stated source.")
    title, company = row.get("title"), row.get("company")
    if not isinstance(title, str) or not title.strip() or not isinstance(company, str) or not company.strip():
        raise ValueError("Title and company are required.")
    description = plain_html(row.get("description") or "")
    if len(description) < 50: raise ValueError("Supply at least 50 characters of reviewed job description.")
    facts = {"source_family": site, "source_url": url, "attribution": site, "access_route": "reviewed_export",
             "community_tool": "JobSpy-compatible export; collection not performed by CareerOS",
             "salary_note": "Imported source statement; not independently verified.", "employment_type": row.get("job_type") or "unknown",
             "work_mode": "remote" if str(row.get("is_remote", "")).lower() == "true" else "unknown"}
    # Retain explicit intervals without estimates, currency conversion or pay inference.
    interval = {"yearly": "annual", "monthly": "monthly", "annual": "annual"}.get(row.get("interval"), "unknown")
    facts["original_salary_source"] = str(row.get("salary_source") or "").strip().lower()
    if str(row.get("salary_source") or "").lower() == "direct_data":
        for source, dest in (("min_amount", "salary_min"), ("max_amount", "salary_max")):
            value = row.get(source)
            if value not in (None, ""):
                try:
                    number = float(value)
                    if not 0 <= number <= 1e10: raise ValueError()
                except (ValueError, TypeError): raise ValueError("Invalid advertised salary amount.") from None
                facts[dest] = number
        facts.update(salary_currency=row.get("currency"), salary_period=interval)
    native = hashlib.sha256(canonical_url(url).encode()).hexdigest()
    return Listing(native, title.strip()[:200], company.strip()[:150], str(row.get("location") or "")[:250],
                   url, description, bool(full) and len(description) < 100000, timestamp(row.get("date_posted")), facts)


def selected(content, format, rows, full=False):
    reviewed = preview(content, format)
    valid = {item["row"] for item in reviewed["items"]}
    if not rows or len(rows) > 100 or len(set(rows)) != len(rows) or any(i not in valid for i in rows):
        raise ValueError("Select 1–100 unique valid rows from the preview.")
    records = list(csv.DictReader(io.StringIO(content.lstrip("\ufeff")))) if format == "csv" else json.loads(content)
    return [(records[index]["site"], normalized(records[index], full)) for index in rows]
