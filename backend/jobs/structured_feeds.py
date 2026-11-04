"""Normalize explicit RSS/Atom/XML/JSON/JobPosting feeds without crawling links."""
import hashlib
import json
import re
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from xml.etree import ElementTree as ET
from jobs.connectors import Listing, Snapshot, SourceError, plain_html, public_url, timestamp
from jobs.feed_transport import fetch_public_feed


class StructuredScripts(HTMLParser):
    def __init__(self): super().__init__(); self.active = False; self.parts = []; self.scripts = []
    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json": self.active = True; self.parts = []
    def handle_data(self, data):
        if self.active: self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.scripts.append("".join(self.parts)); self.active = False


def json_records(data, depth=0):
    if depth > 12: raise ValueError("Structured data nesting exceeds the supported depth")
    if isinstance(data, list):
        return [record for item in data for record in json_records(item, depth + 1)]
    if not isinstance(data, dict): return []
    kind = data.get("@type", [])
    if "JobPosting" in ([kind] if isinstance(kind, str) else kind): return [data]
    if "@graph" in data: return json_records(data["@graph"], depth + 1)
    if isinstance(data.get("jobs"), list): return data["jobs"]
    if "title" in data and ("apply_url" in data or "url" in data): return [data]
    return []


def xml_records(body):
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", body, re.I): raise ValueError("XML entities and doctypes are unsupported")
    root = ET.fromstring(body)
    local = lambda tag: tag.rsplit("}", 1)[-1].lower()
    if local(root.tag) not in {"rss", "feed", "jobs", "jobfeed", "job", "source"}:
        raise ValueError("Unrecognized job-feed root")
    records = []
    for node in root.iter():
        if local(node.tag) not in {"item", "entry", "job"}: continue
        values = {local(child.tag): "".join(child.itertext()).strip() for child in node}
        link = next((child.get("href") for child in node if local(child.tag) == "link" and child.get("rel", "alternate") == "alternate" and child.get("href")), None)
        records.append({"id": values.get("guid") or values.get("id") or values.get("jobid"),
            "title": values.get("title") or values.get("jobtitle"), "company": values.get("company") or values.get("companyname"),
            "location": values.get("location") or ", ".join(filter(None, [values.get("city"), values.get("country")])),
            "url": link or values.get("url") or values.get("link") or values.get("applyurl"),
            "description": values.get("description") or values.get("encoded") or values.get("content") or values.get("summary"),
            "datePosted": values.get("pubdate") or values.get("published") or values.get("dateposted"),
            "validThrough": values.get("expirationdate") or values.get("validthrough"),
            "employmentType": values.get("jobtype") or values.get("employmenttype") or "unknown"})
    return records


def normalized(item, company, full_descriptions):
    if not isinstance(item, dict): raise ValueError("Expected a job object")
    title = item.get("title")
    url = public_url(item.get("apply_url") or item.get("url") or "")
    if not isinstance(title, str) or not title.strip(): raise ValueError("Missing title")
    employer = item.get("hiringOrganization") or item.get("company") or company
    if isinstance(employer, dict): employer = employer.get("name") or company
    location = item.get("jobLocation") or item.get("location") or ""
    locations = location if isinstance(location, list) else [location]
    labels = []
    for place in locations:
        if isinstance(place, dict):
            address = place.get("address") or place
            if isinstance(address, dict):
                country = address.get("addressCountry") or ""
                if isinstance(country, dict): country = country.get("name", "")
                place = ", ".join(str(v) for v in [address.get("addressLocality"), address.get("addressRegion"), country] if v)
            else: place = str(address)
        if isinstance(place, str) and place: labels.append(place)
    description = plain_html(item.get("description") or "")
    if len(description) < 50: raise ValueError("Description too short")
    published = timestamp(item.get("datePosted") or item.get("published_at"))
    if not published and item.get("datePosted"):
        try: published = timestamp(parsedate_to_datetime(item["datePosted"]).isoformat())
        except (ValueError, TypeError, OverflowError): pass
    identifier = item.get("identifier") or item.get("id") or url
    if isinstance(identifier, dict): identifier = identifier.get("value") or url
    native = str(identifier)
    if len(native) > 250: native = hashlib.sha256(native.encode()).hexdigest()
    expiry = timestamp(item.get("validThrough"))
    facts = {"employment_type": item.get("employmentType", "unknown"), "source_url": url,
             "attribution": str(employer), "secondary_locations": labels[1:],
             "work_mode": "remote" if item.get("jobLocationType") == "TELECOMMUTE" else "unknown"}
    restrictions = item.get("applicantLocationRequirements")
    if restrictions:
        if not isinstance(restrictions, list): restrictions = [restrictions]
        countries = [str(value.get("name", "")) if isinstance(value, dict) else str(value) for value in restrictions]
        if not labels: labels = [", ".join(countries)]
        facts["applicant_location_requirements"] = countries
    if expiry: facts["source_expiry_at"] = expiry.isoformat()
    salary = item.get("baseSalary")
    if isinstance(salary, dict) and isinstance(salary.get("value"), dict):
        value = salary["value"]
        facts.update(salary_currency=salary.get("currency"),
            salary_min=value.get("minValue", value.get("value")), salary_max=value.get("maxValue", value.get("value")),
            salary_period={"YEAR": "annual", "MONTH": "monthly"}.get(str(value.get("unitText", "")).upper(), "unknown"))
    elif item.get("salary_currency"):
        facts.update({key: item.get(key) for key in ("salary_currency", "salary_min", "salary_max", "salary_period")})
    if item.get("work_mode") in {"remote", "hybrid", "onsite"}: facts["work_mode"] = item["work_mode"]
    return Listing(native, title.strip()[:200], str(employer), labels[0] if labels else "", url, description,
                   full_descriptions and len(description) < 100000, published, facts)


def parse_feed(body, company, configuration, cursor=None, budget=500):
    try:
        text = body.decode("utf-8-sig")
        kind = configuration.get("format", "auto")
        if kind == "json" or text.lstrip().startswith(("{", "[")):
            data = json.loads(text)
            records = json_records(data)
            if not records and not (isinstance(data, dict) and data.get("jobs") == []): raise ValueError("No job records")
        elif kind == "jsonld" or re.search(r"<html\b|<!doctype\s+html", text[:1000], re.I):
            parser = StructuredScripts(); parser.feed(text)
            records = [record for script in parser.scripts for record in json_records(json.loads(script))]
            if not records: raise ValueError("No JobPosting structured data")
        else: records = xml_records(body)
    except (ValueError, TypeError, UnicodeError, ET.ParseError, RecursionError):
        raise SourceError("Unexpected structured-feed format; existing jobs preserved.") from None
    version = hashlib.sha256(body).hexdigest()
    offset, warnings = 0, []
    if cursor:
        try:
            checkpoint = json.loads(cursor)
            if checkpoint["version"] == version: offset = max(0, int(checkpoint["offset"]))
            else: warnings.append("Feed changed during traversal; restarted from its first page.")
        except (ValueError, KeyError, TypeError): raise SourceError("Invalid feed checkpoint.") from None
    jobs, skipped = [], 0
    for item in records[offset:offset + budget]:
        try: jobs.append(normalized(item, company, configuration.get("full_descriptions", False)))
        except (ValueError, TypeError, AttributeError): skipped += 1
    end = offset + budget
    next_cursor = json.dumps({"version": version, "offset": end}) if end < len(records) else None
    return Snapshot(jobs, False, scope="rolling_feed", cursor=next_cursor, skipped=skipped, warnings=warnings,
                    truncation_reason="More feed records available." if next_cursor else None)


def fetch_feed(configuration, company, cursor=None):
    if not configuration.get("feed_url"): raise SourceError("This source requires a public feed URL.")
    return parse_feed(fetch_public_feed(configuration["feed_url"]), company, configuration, cursor)
