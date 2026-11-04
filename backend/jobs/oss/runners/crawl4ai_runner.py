"""Bounded self-hosted Crawl4AI runner for reviewed public source profiles."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from _common import RunnerFailure, decode_cursor, serve


REPO_ROOT = Path(__file__).resolve().parents[4]
PROFILE_DIR = REPO_ROOT / "backend" / "jobs" / "oss" / "profiles"
RUNTIME_ROOT = REPO_ROOT / "oss-tools" / "runtime"
USER_AGENT = "CareerOS-OSS-Collector/1.0 (public careers page research)"
MAX_REQUESTS = 60
MAX_PAGES = 3
MAX_HTML_CHARS = 1_500_000
_SENSITIVE_URL_KEY = re.compile(r"(?:access[_-]?token|api[_-]?key|authorization|auth[_-]?token|client[_-]?secret|cookie|password|session(?:id)?|signature|^sig$|^token$|^key$)", re.I)


def _domain_allowed(url: str, domains: list[str] | tuple[str, ...]) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        if any(_SENSITIVE_URL_KEY.search(key) for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
            return False
        try:
            address = ipaddress.ip_address(host)
            return address.is_global and not domains
        except ValueError:
            return "." in host and any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)
    except ValueError:
        return False


def _public_dns(host: str) -> bool:
    """Resolve once and reject a host if any returned address is non-public."""
    try:
        infos = socket.getaddrinfo(host, 443, 0, socket.SOCK_STREAM)
        ips = {ipaddress.ip_address(item[4][0]) for item in infos}
        return bool(ips) and all(ip.is_global for ip in ips)
    except (OSError, ValueError, socket.gaierror):
        return False


def _search_url(profile: dict[str, Any], entry_url: str, role: str, location: str) -> str:
    params = dict(parse_qsl(urlsplit(entry_url).query, keep_blank_values=True))
    for key, value in (profile.get("query_parameters") or {}).items():
        if value == "role":
            params[str(key)] = role
        elif value == "location":
            params[str(key)] = location
    parsed = urlsplit(entry_url)
    path = parsed.path
    if profile.get("search_path_template"):
        role_value = (profile.get("role_aliases") or {}).get(role.lower().strip(), role)
        slug = re.sub(r"[^a-z0-9]+", "-", role_value.lower()).strip("-")
        path = str(profile["search_path_template"]).replace("{role_slug}", slug)
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(params), ""))


def _text(node: Any, limit: int = 50000) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()[:limit]


def _select_text(node: Any, selectors: list[str], limit: int = 50000) -> str:
    for selector in selectors:
        try:
            found = node.select_one(selector)
        except Exception:
            continue
        value = _text(found, limit)
        if value:
            return value
    return ""


def _load_extract_helpers():
    backend = str(REPO_ROOT / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from jobs.oss.crawl_extract import classify_page, structured_job_records, validate_ai_record
    return classify_page, structured_job_records, validate_ai_record


def _extract_page(html: str, page_url: str, profile: dict[str, Any], domains: list[str]) -> tuple[list[dict[str, Any]], str, list[str]]:
    from bs4 import BeautifulSoup

    classify_page, structured_job_records, validate_ai_record = _load_extract_helpers()
    soup = BeautifulSoup(html[:MAX_HTML_CHARS], "html.parser")
    records = [row for row in structured_job_records(html, page_url) if _domain_allowed(str(row.get("apply_url") or row.get("source_url") or ""), domains)]
    links: list[str] = []
    link_selectors = profile.get("job_link_selectors") or []
    for selector in link_selectors:
        try:
            anchors = soup.select(selector)
        except Exception:
            anchors = []
        for anchor in anchors:
            href = urljoin(page_url, str(anchor.get("href") or ""))
            if profile.get("job_url_pattern") and not re.search(profile["job_url_pattern"], urlsplit(href).path): continue
            if _domain_allowed(href, domains) and href not in links:
                links.append(href)

    title_selectors = profile.get("title_selectors") or []
    company_selectors = profile.get("company_selectors") or []
    location_selectors = profile.get("location_selectors") or []
    description_selectors = profile.get("description_selectors") or []
    for link in links:
        if any(str(row.get("source_url") or row.get("apply_url")) == link for row in records):
            continue
        anchor = None
        for selector in link_selectors:
            try:
                anchor = next((a for a in soup.select(selector) if urljoin(page_url, str(a.get("href") or "")) == link), None)
            except Exception:
                anchor = None
            if anchor is not None:
                break
        if anchor is None:
            continue
        node = anchor
        card = anchor
        for _ in range(9):
            if node is None:
                break
            if _select_text(node, title_selectors, 300) and (_select_text(node, company_selectors, 240) or profile.get("company_fallback")):
                card = node
                break
            node = getattr(node, "parent", None)
        title = (_text(anchor, 300) if profile.get("title_from_link") else _select_text(card, title_selectors, 300)) or _text(anchor, 300)
        if title.casefold().strip() in {"careers", "jobs", "search jobs", "apply", "apply now", "view jobs"}: continue
        company = _select_text(card, company_selectors, 240) or str(profile.get("company_fallback") or "")
        if not title or not company:
            continue
        records.append({
            "id": link, "title": title, "company": company,
            "location": _select_text(card, location_selectors, 300),
            "source_url": link, "apply_url": link,
            "description": _select_text(card, description_selectors),
            "description_complete": False,
        })

    if not records and links:
        local_model = os.environ.get("OSS_LOCAL_MODEL", "").strip()
        local_host = os.environ.get("OSS_OLLAMA_HOST", "http://127.0.0.1:11434").strip()
        if local_model and local_host in {"http://127.0.0.1:11434", "http://localhost:11434"}:
            from urllib.request import Request, urlopen
            text = _text(soup, 12000)
            prompt = ("Extract public job records from this loaded source page. Return JSON only: "
                      "{\"jobs\":[{\"id\":string,\"source_url\":string,\"title\":string,\"company\":string,"
                      "\"location\":string,\"description\":string,\"evidence\":{\"title\":string,\"company\":string,\"description\":string}}]}. "
                      "Use only these exact job links: " + json.dumps(links[:30]) + "\nPage text:\n" + text)
            payload = json.dumps({"model": local_model[:100], "prompt": prompt, "stream": False,
                                  "format": "json", "options": {"num_predict": 1200}}).encode("utf-8")
            try:
                request = Request(local_host.rstrip("/") + "/api/generate", data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=8) as response:
                    generated = json.loads(response.read(512 * 1024).decode("utf-8"))
                output = generated.get("response", "")
                parsed = json.loads(output) if isinstance(output, str) else output
                candidates = parsed.get("jobs", []) if isinstance(parsed, dict) else []
                if isinstance(candidates, list):
                    records.extend(validated for item in candidates[:20]
                                   if (validated := validate_ai_record(item, allowed_links=set(links), source_text=text)))
            except Exception:
                pass

    next_links: list[str] = []
    for selector in profile.get("next_selectors") or []:
        try:
            anchors = soup.select(selector)
        except Exception:
            anchors = []
        for anchor in anchors:
            href = urljoin(page_url, str(anchor.get("href") or ""))
            if href != page_url and _domain_allowed(href, domains) and href not in next_links:
                next_links.append(href)
    return records, _text(soup), next_links


async def _run(request: dict[str, Any]) -> dict[str, Any]:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    source_id = str(request.get("source_id", ""))
    profile_path = PROFILE_DIR / f"{source_id}.json"
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise RunnerFailure("unsupported", "The Crawl4AI source profile is missing or malformed.") from None
    domains = profile.get("approved_domains") or []
    if not isinstance(domains, list) or not domains:
        raise RunnerFailure("unsupported", "The Crawl4AI profile has no approved source domains.")
    access_state = str(profile.get("access_state", "")).casefold()
    if "permission_required" in access_state:
        raise RunnerFailure("blocked", "The source access review requires permission before automated collection.")
    if "login-required" in access_state:
        raise RunnerFailure("login_required", "The profile has no established public job-search route.")
    if not profile.get("query_parameters") and not profile.get("search_path_template"):
        raise RunnerFailure("login_required", "The source profile has no public search route and may require a session.")

    entry = request.get("entry_url") or profile.get("entry_url")
    if not isinstance(entry, str) or not _domain_allowed(entry, domains):
        raise RunnerFailure("blocked", "Entry URL is outside the approved HTTPS source domains.")
    state = decode_cursor(request)
    item_offset = int(state.get("item_offset", 0))
    if not 0 <= item_offset <= 5000:
        raise RunnerFailure("invalid_output", "Invalid within-page offset.")
    current = state.get("next_url") or _search_url(profile, entry, request["role"], request["location"])
    if not _domain_allowed(current, domains):
        raise RunnerFailure("invalid_output", "Continuation URL is outside the approved source domains.")

    try:
        from jobs.oss.crawl_extract import classify_page
    except ImportError:
        classify_page = _load_extract_helpers()[0]

    robots_parser = RobotFileParser()
    robots_url = urlunsplit(("https", urlsplit(entry).netloc, "/robots.txt", "", ""))
    request_budget = {"count": 0, "overflow": False, "outside": False, "dns_cache": {}}

    async def check_destination(url: str) -> bool:
        if not _domain_allowed(url, domains):
            return False
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
        if host not in request_budget["dns_cache"]:
            # Resolve synchronously so cancellation/timeout cleanup never
            # leaves a resolver worker holding the runner's stdout pipe.
            request_budget["dns_cache"][host] = _public_dns(host)
        return bool(request_budget["dns_cache"][host])

    async def on_page_context_created(page, context=None, config=None):
        async def guard(route):
            url = route.request.url
            if getattr(route.request, "resource_type", "") in {"image", "media", "font", "stylesheet"}:
                await route.abort("blockedbyclient")
                return
            scheme = urlsplit(url).scheme.lower()
            if scheme in {"data", "blob", "about"}:
                await route.continue_()
                return
            if not await check_destination(url):
                request_budget["outside"] = True
                await route.abort("blockedbyclient")
                return
            if request_budget["count"] >= MAX_REQUESTS:
                request_budget["overflow"] = True
                await route.abort("blockedbyclient")
                return
            request_budget["count"] += 1
            await route.continue_()
        await page.route("**/*", guard)

    load_more_js: list[str] | None = None
    load_more_selector = profile.get("load_more_selector")
    if isinstance(load_more_selector, str) and 0 < len(load_more_selector) <= 240:
        safe_selector = json.dumps(load_more_selector)
        click_count = max(1, min(2, int(profile.get("load_more_clicks", 1))))
        load_more_js = [
            "(async()=>{const e=document.querySelector(" + safe_selector + ");if(e){e.click();await new Promise(r=>setTimeout(r,500));}})()"
            for _ in range(click_count)
        ]
    scroll_steps = max(0, min(3, int(profile.get("scroll_steps", 0))))
    max_pages = max(1, min(MAX_PAGES, int(profile.get("max_pages", MAX_PAGES))))
    max_results = int(request.get("max_results", 20))
    max_details = min(8, max(0, int(request.get("max_details", 0))))
    operation_seconds = max(3, int(request.get("deadline_seconds", 60)) - 10)
    page_timeout_ms = max(2500, min(12000, int(operation_seconds * 1000 / (max_pages + max_details + 2))))
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until="domcontentloaded",
        page_timeout=page_timeout_ms,
        wait_for="css:" + str(profile.get("page_ready_selector") or "body"),
        wait_for_timeout=min(800, max(250, page_timeout_ms // 5)),
        check_robots_txt=False,
        user_agent=USER_AGENT,
        verbose=False,
        process_iframes=False,
        scan_full_page=scroll_steps > 0,
        max_scroll_steps=scroll_steps or None,
        scroll_delay=0.15,
        js_code=load_more_js,
        capture_network_requests=False,
        capture_console_messages=False,
    )
    browser_config = BrowserConfig(headless=True, verbose=False, enable_stealth=False,
                                   ignore_https_errors=False, proxy=None, storage_state=None,
                                   user_agent=USER_AGENT, java_script_enabled=True)
    seen_signatures = list(state.get("page_signatures", []))[-8:]
    all_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    page_urls: list[str] = []
    next_url: str | None = None
    explicit_empty = False
    changed_format = False
    blocked_reason: str | None = None

    async with AsyncWebCrawler(config=browser_config, base_directory=str(RUNTIME_ROOT / "crawl-data")) as crawler:
        crawler.crawler_strategy.set_hook("on_page_context_created", on_page_context_created)
        if profile.get("robots_required", True):
            if not await check_destination(robots_url):
                raise RunnerFailure("blocked", "Source robots.txt host did not resolve to an approved public address.")
            robots_result = await crawler.arun(robots_url, config=run_config)
            robots_status = getattr(robots_result, "status_code", None)
            robots_html = (getattr(robots_result, "html", "") or "")[:200000]
            if robots_status in {401, 403, 429}:
                reason = "rate_limited" if robots_status == 429 else "blocked"
                raise RunnerFailure(reason, "Source robots.txt request was denied.", robots_status)
            if not getattr(robots_result, "success", False) and robots_status not in {404, 410}:
                raise RunnerFailure("transport", "Source robots.txt could not be checked; collection stopped.", robots_status)
            robots_text = re.sub(r"<[^>]+>", " ", robots_html)
            robots_text = robots_text.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
            if robots_status in {404, 410}:
                robots_parser.parse([])
            else:
                robots_parser.set_url(robots_url)
                robots_parser.parse([line.strip() for line in robots_text.splitlines() if line.strip()])
                if "<html" in robots_html[:1000].casefold() and "user-agent:" not in robots_text.casefold():
                    raise RunnerFailure("blocked", "Source robots.txt did not return a readable policy document.", robots_status)
            if not robots_parser.can_fetch(USER_AGENT, current):
                raise RunnerFailure("blocked", "The source robots.txt disallows this public search path.")

        for _ in range(max_pages):
            if not await check_destination(current):
                raise RunnerFailure("blocked", "Page URL failed the approved public-host check.")
            page_urls.append(current)
            try:
                result = await crawler.arun(current, config=run_config)
            except Exception:
                if request_budget["overflow"]:
                    warnings.append("The hard browser request ceiling was reached.")
                    break
                raise RunnerFailure("transport", "Crawl4AI could not load the approved public page.") from None
            status = getattr(result, "status_code", None)
            html = (getattr(result, "html", "") or getattr(result, "cleaned_html", "") or "")[:MAX_HTML_CHARS]
            if status in {401, 403, 429}:
                reason = "rate_limited" if status == 429 else "blocked"
                raise RunnerFailure(reason, "The source denied the bounded public page request.", status)
            if not getattr(result, "success", False) and status not in {404, 410}:
                if request_budget["overflow"]:
                    warnings.append("The hard browser request ceiling was reached before page loading finished.")
                    break
                raise RunnerFailure("transport", "Crawl4AI returned no usable public page content.", status)
            final_url = getattr(result, "redirected_url", None) or getattr(result, "url", current)
            if not _domain_allowed(str(final_url), domains):
                raise RunnerFailure("blocked", "A page redirect left the approved source domain.")
            page_text = re.sub(r"<[^>]+>", " ", html)
            access = classify_page(status, page_text, profile)
            if access:
                reason = "rate_limited" if status == 429 else access
                raise RunnerFailure(reason, "The page requires login or returned an access challenge.", status)
            rows, visible_text, next_links = _extract_page(html, current, profile, domains)
            signature = hashlib.sha256((current + "\n" + "\n".join(str(row.get("id") or row.get("source_url")) for row in rows)).encode()).hexdigest()
            if signature in seen_signatures:
                warnings.append("The source repeated a previously collected page; traversal stopped.")
                break
            # A partly consumed window must be revisited before moving on.
            # Retain its signature only after all its rows have been emitted.
            for row in rows:
                if not any((prior.get("source_url") or prior.get("apply_url")) == (row.get("source_url") or row.get("apply_url")) for prior in all_rows):
                    all_rows.append(row)
            if not rows and any(marker.casefold() in visible_text.casefold() for marker in profile.get("empty_indicators", [])):
                explicit_empty = True
                break
            if not rows and len(visible_text) < 80:
                changed_format = True
                break
            next_url = next_links[0] if next_links else None
            if len(all_rows) > item_offset + max_results:
                break
            seen_signatures.append(signature)
            if not next_url:
                break
            if not robots_parser.can_fetch(USER_AGENT, next_url):
                warnings.append("Robots policy disallows the next page; traversal stopped there.")
                next_url = None
                break
            current = next_url
            if len(all_rows) >= max_results:
                break
            if request_budget["overflow"]:
                warnings.append("The hard browser request ceiling was reached.")
                break

        # Detail traversal is explicit and capped. Each destination is still
        # checked by robots, HTTPS/domain rules, DNS and the browser route.
        detailed = 0
        for row in all_rows[item_offset:item_offset + max_details]:
            detail_url = row.get("source_url") or row.get("apply_url")
            if not isinstance(detail_url, str) or detail_url in page_urls or not await check_destination(detail_url):
                continue
            if not robots_parser.can_fetch(USER_AGENT, detail_url):
                warnings.append("A job detail path is disallowed by robots.txt; its excerpt remains incomplete.")
                continue
            try:
                detail_result = await crawler.arun(detail_url, config=run_config)
            except Exception:
                warnings.append("A bounded detail-page request failed; its description remains incomplete.")
                continue
            detailed += 1
            detail_status = getattr(detail_result, "status_code", None)
            detail_html = (getattr(detail_result, "html", "") or getattr(detail_result, "cleaned_html", "") or "")[:MAX_HTML_CHARS]
            if classify_page(detail_status, re.sub(r"<[^>]+>", " ", detail_html), profile):
                warnings.append("A detail page requested login or returned a challenge; its description remains incomplete.")
                continue
            try:
                structured = _load_extract_helpers()[1](detail_html, detail_url)
                description = next((str(item.get("description") or "") for item in structured
                                    if str(item.get("description") or "").strip()), "")
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(detail_html, "html.parser")
                if not description:
                    for selector in profile.get("description_selectors") or []:
                        if selector.strip().casefold() == "main":
                            continue
                        description = _select_text(soup, [selector])
                        if description:
                            break
                if description and len(description) >= 40:
                    row["description"] = description
                    row["description_complete"] = True
            except Exception:
                pass
            if request_budget["overflow"]:
                warnings.append("The hard browser request ceiling was reached during detail traversal.")
                break

    if changed_format:
        raise RunnerFailure("changed_format", "The page loaded, but the profile found neither job records nor a recognized empty-results message.")
    if not all_rows and not explicit_empty:
        if request_budget["overflow"]:
            raise RunnerFailure("timeout", "The hard browser request ceiling was reached before a page could be evaluated.")
        raise RunnerFailure("changed_format", "The source page had no usable job records or explicit empty-results evidence.")
    if request_budget["outside"]:
        warnings.append("Out-of-domain or non-public browser requests were blocked by the runtime boundary.")
    if detailed < min(max_details, len(all_rows)):
        warnings.append("Details were loaded only for a bounded subset of listings.")

    selected = all_rows[item_offset:item_offset + max_results]
    remaining_offset = item_offset + len(selected) if len(all_rows) > item_offset + len(selected) else 0
    if remaining_offset:
        next_url = page_urls[-1]
    skipped = 0
    if explicit_empty and not selected:
        coverage = "exhausted"
        next_url = None
    elif next_url and len(page_urls) >= max_pages:
        coverage = "partial"
    elif next_url:
        coverage = "partial"
    else:
        coverage = "unknown"
    try:
        version = importlib.metadata.version("Crawl4AI")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return {"jobs": selected, "next_url": next_url, "coverage": coverage,
            "item_offset": remaining_offset,
            "page_signatures": seen_signatures[-8:], "page_count": len(page_urls),
            "request_count": request_budget["count"], "skipped": skipped,
            "warnings": warnings[:30], "tool_version": version,
            "description_pages": detailed}


def run(request: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(_run(request))


if __name__ == "__main__":
    serve(run)
