"""Read-only documented job-board APIs. No arbitrary URL fetching or scraping."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import hashlib
import ipaddress
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler


class SourceError(RuntimeError):
    def __init__(self, message, retry_after_seconds=None, status_code=None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.status_code = status_code


def retry_after_seconds(value):
    if not value:
        return None
    try:
        seconds = int(value)
    except (ValueError, TypeError):
        try:
            seconds = int((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None
    return max(30, seconds)


@dataclass
class Listing:
    native_id: str
    title: str
    company: str
    location: str
    apply_url: str
    description: str
    complete: bool
    published_at: datetime | None = None
    facts: dict = field(default_factory=dict)


@dataclass
class Snapshot:
    jobs: list[Listing]
    complete: bool = True
    scope: str = "company_board"
    pages: int = 1
    cursor: str | None = None
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    truncation_reason: str | None = None
    traversal_valid: bool = False
    traversal_end: bool = False
    board_version: str | None = None

    def metadata(self):
        return {"scope": self.scope, "pages": self.pages, "cursor": self.cursor,
                "skipped": self.skipped, "warnings": self.warnings,
                "truncation_reason": self.truncation_reason,
                "can_close_missing": self.complete and self.scope == "company_board"}


class _PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}: self.hidden += 1
        if tag in {"p", "li", "br", "div", "h1", "h2", "h3", "h4"}: self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}: self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "li", "div", "h1", "h2", "h3", "h4"}: self.parts.append("\n")

    def handle_data(self, text):
        if not self.hidden: self.parts.append(text)


def plain_html(value: str) -> str:
    parser = _PlainHTML()
    parser.feed(unescape(unescape(str(value or ""))))
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()[:100000]


def public_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"https", "http"} or not host or parsed.username or parsed.password:
        raise ValueError("Use a public HTTP or HTTPS application URL.")
    if host == "localhost" or "." not in host or host.endswith((".local", ".internal")):
        raise ValueError("Local application URLs are not supported.")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("Private application URLs are not supported.")
    except ValueError as exc:
        if "not supported" in str(exc): raise
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def canonical_url(value: str) -> str:
    parsed = urlsplit(public_url(value))
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() != "gh_src"]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), urlencode(sorted(query)), ""))


def fingerprint(job: Listing) -> str:
    parts = [job.company, job.title, job.location, job.description]
    text = "|".join(re.sub(r"\s+", " ", part).strip().lower() for part in parts)
    return hashlib.sha256(text.encode()).hexdigest()


def timestamp(value) -> datetime | None:
    try:
        if isinstance(value, (float, int)):
            return datetime.fromtimestamp(value / 1000, timezone.utc).replace(tzinfo=None)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError):
        return None


def board_slug(provider: str, value: str) -> str:
    value = value.strip()
    if "://" in value:
        parsed = urlsplit(value)
        allowed = {"greenhouse": {"boards.greenhouse.io", "job-boards.greenhouse.io"},
                   "lever": {"jobs.lever.co", "jobs.eu.lever.co"},
                   "ashby": {"jobs.ashbyhq.com"},
                   "smartrecruiters": {"careers.smartrecruiters.com", "jobs.smartrecruiters.com"},
                   "workable": {"apply.workable.com"}}
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in {None, 443}:
            raise ValueError("Use a public HTTPS company board URL without credentials or a custom port.")
        if parsed.hostname not in allowed.get(provider, set()):
            raise ValueError("Use that provider's company board URL or board identifier.")
        # Lever's EU boards need an explicit EU prefix for the fixed API host.
        value = parsed.path.strip("/").split("/")[0]
        if provider == "lever" and parsed.hostname == "jobs.eu.lever.co": value = "eu:" + value
    pattern = r"(?:eu:)?[A-Za-z0-9_-]{1,80}" if provider == "lever" else r"[A-Za-z0-9_-]{1,80}"
    if not re.fullmatch(pattern, value):
        raise ValueError("Board identifiers may contain letters, numbers, hyphens, and underscores.")
    return value


def detect_board(value):
    host = urlsplit(value.strip()).hostname
    providers = {"boards.greenhouse.io": "greenhouse", "job-boards.greenhouse.io": "greenhouse",
        "jobs.lever.co": "lever", "jobs.eu.lever.co": "lever", "jobs.ashbyhq.com": "ashby",
        "careers.smartrecruiters.com": "smartrecruiters", "jobs.smartrecruiters.com": "smartrecruiters",
        "apply.workable.com": "workable"}
    provider = providers.get(host)
    if not provider: raise ValueError("Provider could not be detected. Choose a supported provider and board identifier.")
    return provider, board_slug(provider, value)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urlsplit(req.full_url)
        new = urlsplit(newurl)
        # Workable's documented public endpoint currently redirects to its
        # official widget endpoint. Permit only this exact fixed-host mapping.
        if (old.hostname == "www.workable.com" and re.fullmatch(r"/api/accounts/[A-Za-z0-9_-]{1,80}", old.path)
                and new.scheme == "https" and new.netloc == "apply.workable.com"
                and new.path == "/api/v1/widget/accounts/" + old.path.rsplit("/", 1)[1]
                and new.query == old.query):
            return super().redirect_request(req, fp, code, msg, headers, newurl)
        raise SourceError("Source redirect requires review; existing listings preserved.")


urlopen = build_opener(_NoRedirect()).open


# Only fixed documented provider hosts are fetched. Board URLs are parsed into
# validated identifiers; listing/apply URLs are stored, never requested.
_API_HOSTS = {"boards-api.greenhouse.io", "api.lever.co", "api.eu.lever.co", "api.adzuna.com",
              "api.ashbyhq.com", "api.smartrecruiters.com", "www.workable.com", "remotive.com", "jobicy.com", "himalayas.app"}


def request_json(url: str, params: dict | None = None):
    # urllib intentionally avoids httpx's INFO request logging: Adzuna credentials
    # are query parameters and must never appear in server logs or exceptions.
    full_url = url + ("?" + urlencode(params) if params else "")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in _API_HOSTS or parsed.port not in {None, 443} or parsed.username or parsed.password:
        raise SourceError("Unsupported API destination.")
    from jobs import http_cache
    cacheable = parsed.hostname != "api.adzuna.com"
    cached = http_cache.get(full_url) if cacheable else None
    request = Request(full_url, headers={"Accept": "application/json", "User-Agent": "CareerOS-personal/0.2",
                      **(cached[1] if cached else {})})
    try:
        deadline = time.monotonic() + 20
        with urlopen(request, timeout=20) as response:
            chunks, size = [], 0
            reader = getattr(response, "read1", response.read)
            while True:
                if time.monotonic() >= deadline: raise SourceError("Source response exceeded the execution time budget.")
                chunk = reader(min(65536, 8000001 - size))
                if not chunk: break
                chunks.append(chunk); size += len(chunk)
                if size > 8000000: raise SourceError("Job board response exceeded the 8 MB limit.")
            data = b"".join(chunks)
            headers = response.headers
        result = json.loads(data)
        if cacheable: http_cache.put(full_url, data, headers)
        return result
    except HTTPError as exc:
        if exc.code == 304 and cached:
            return json.loads(cached[0])
        messages = {401: "Credential rejected", 403: "Access denied", 404: "Board not found", 429: "Source rate limit reached; retry later"}
        delay = retry_after_seconds(exc.headers.get("Retry-After")) if exc.headers else None
        raise SourceError(f"{messages.get(exc.code, 'Source request failed')} (HTTP {exc.code}).", delay, exc.code) from None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise SourceError("Source could not be reached or returned invalid JSON. Retry later.") from None


def greenhouse(board: str, company: str) -> Snapshot:
    data = request_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", {"content": "true"})
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise SourceError("Unexpected Greenhouse response.")
    result = []
    for item in data["jobs"]:
        if not isinstance(item, dict): continue
        if not item.get("id") or not item.get("title") or not item.get("absolute_url"): continue
        try: url = public_url(item["absolute_url"])
        except ValueError: continue
        description = plain_html(item.get("content", ""))
        result.append(Listing(str(item["id"]), item["title"][:200], company, (item.get("location") or {}).get("name", ""),
                              url, description, 100 <= len(description) < 100000,
                              facts={"requisition_id": item.get("requisition_id"), "source_updated_at": item.get("updated_at"), "employment_type": "unknown"}))
    return Snapshot(result, len(result) == len(data["jobs"]), skipped=len(data["jobs"]) - len(result))


def lever(board: str, company: str, offset=0) -> Snapshot:
    eu = board.startswith("eu:")
    board = board.removeprefix("eu:")
    host = "api.eu.lever.co" if eu else "api.lever.co"
    jobs = []
    valid_snapshot = True
    seen_ids = set()
    for page in range(10):
        data = request_json(f"https://{host}/v0/postings/{board}", {"mode": "json", "limit": 100, "skip": offset + page * 100})
        if not isinstance(data, list): raise SourceError("Unexpected Lever response.")
        before = len(jobs)
        for item in data:
            if not isinstance(item, dict): continue
            if item.get("id") in seen_ids:
                return Snapshot(jobs, False, pages=page + 1, truncation_reason="Repeated native ID/page; review required.")
            seen_ids.add(item.get("id"))
            if not item.get("id") or not item.get("text") or not item.get("hostedUrl"): continue
            try: url = public_url(item.get("applyUrl") or item["hostedUrl"])
            except ValueError: continue
            categories = item.get("categories") or {}
            parts = [plain_html(item.get("descriptionPlain") or item.get("description", ""))]
            parts.extend(str(block.get("text", "")) + "\n" + plain_html(block.get("content", "")) for block in item.get("lists", []))
            parts.append(plain_html(item.get("additionalPlain") or item.get("additional", "")))
            description = "\n\n".join(parts).strip()[:100000]
            jobs.append(Listing(item["id"], item["text"][:200], company, categories.get("location", ""), url, description,
                                100 <= len(description) < 100000, None,
                                {"employment_type": categories.get("commitment", "unknown"), "work_mode": item.get("workplaceType", "unknown"),
                                 "source_created_at": item.get("createdAt"), "publication_date_unknown": True}))
        valid_snapshot = valid_snapshot and len(jobs) - before == len(data)
        if len(data) < 100: return Snapshot(jobs, valid_snapshot and offset == 0, scope="continuation" if offset else "company_board", pages=page + 1,
                                          skipped=0 if valid_snapshot else 1, traversal_valid=valid_snapshot, traversal_end=True)
    return Snapshot(jobs, False, pages=10, cursor=str(offset + 1000), truncation_reason="Execution page budget; resume from offset.", traversal_valid=valid_snapshot)


def adzuna(country: str, preferences: dict) -> Snapshot:
    from core.config import settings
    if not settings.ADZUNA_APP_ID or not settings.ADZUNA_APP_KEY:
        raise SourceError("Adzuna credentials are not configured on the backend.")
    params = {"app_id": settings.ADZUNA_APP_ID, "app_key": settings.ADZUNA_APP_KEY,
              "results_per_page": 50, "what_or": " ".join(preferences["target_roles"][:3]), "sort_by": "date"}
    if preferences.get("locations"): params["where"] = preferences["locations"][0]
    data = request_json(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1", params)
    if not isinstance(data, dict) or not isinstance(data.get("results"), list): raise SourceError("Unexpected Adzuna response.")
    jobs = []
    for item in data["results"]:
        try: url = public_url(item["redirect_url"])
        except (KeyError, ValueError): continue
        jobs.append(Listing(str(item["id"]), item.get("title", "Untitled")[:200], (item.get("company") or {}).get("display_name", "Unknown company"),
                            (item.get("location") or {}).get("display_name", ""), url, plain_html(item.get("description", "")), False,
                            timestamp(item.get("created")), {"salary_min": item.get("salary_min"), "salary_max": item.get("salary_max"),
                            "salary_currency": "INR" if country == "in" else None, "salary_period": "annual",
                            "employment_type": item.get("contract_time", "unknown"), "description_note": "Search excerpt; supply a full JD before tailoring."}))
    # Search results are a window, never an exhaustive closure snapshot.
    return Snapshot(jobs, False)


def _bounded_board(snapshot, cursor=None, budget=1500):
    offset = max(0, int(cursor or 0))
    total = len(snapshot.jobs)
    snapshot.traversal_valid = snapshot.complete and not snapshot.skipped
    snapshot.board_version = hashlib.sha256(json.dumps(sorted(str(job.native_id) for job in snapshot.jobs)).encode()).hexdigest()
    snapshot.traversal_end = offset + budget >= total
    if offset or total > budget:
        snapshot.jobs = snapshot.jobs[offset:offset + budget]
        snapshot.complete = False
        snapshot.scope = "continuation" if offset else "company_board"
        snapshot.cursor = str(offset + budget) if offset + budget < total else None
        snapshot.truncation_reason = "Ingestion execution budget; resumable board offset."
    return snapshot


def fetch_source(provider: str, board: str, company: str, preferences: dict) -> Snapshot:
    from jobs.engine import mode
    if mode() == "oss":
        if provider != "oss": raise SourceError("Legacy collectors are inactive in open-source mode.")
        from jobs.oss.coordinator import fetch
        return fetch(board, preferences)
    if provider == "oss": raise SourceError("Open-source collection is inactive in legacy mode.")
    if provider == "adzuna": return adzuna(board, preferences)
    from jobs.adapters import dispatch
    return dispatch(provider, board, company, preferences)
