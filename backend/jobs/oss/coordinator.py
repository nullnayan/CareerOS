"""One OSS source plan; no legacy fallback or database access from collectors."""
import hashlib
import json
from pathlib import Path
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from urllib.parse import urlsplit
from jobs.connectors import SourceError
from .contracts import CollectorRequest, CollectorFailure, query_fingerprint
from .catalog import REPO_ROOT, JOBSPY_SITES, OMKAR_SITES

_browser = threading.BoundedSemaphore(1)
_domains = {}
_domain_guard = threading.Lock()


@contextmanager
def _acquire(lock, deadline=None):
    from .cancellation import check
    while not lock.acquire(timeout=0.1):
        check()
        if deadline and time.monotonic() >= deadline: raise CollectorFailure("timeout", "Collection wait exceeded its shared budget.")
    try:
        check()
        yield
    finally: lock.release()


def catalog():
    from jobs.directory import company_directory
    rows = []
    for key, item in {**JOBSPY_SITES, **OMKAR_SITES}.items():
        blocked = key in {"internshala_jobs", "internshala_internships"}
        rows.append(dict(key=key, name=key.replace("_", " ").title(), tool=item.tool,
                         url=item.official_url, scope=item.country_scope,
                         limitation=item.limitation, connectable=not blocked, verification="not_live_verified"))
    for path in sorted((Path(__file__).parent / "profiles").glob("*.json")):
        if "template" in path.name: continue
        profile = json.loads(path.read_text(encoding="utf-8"))
        key = profile["source_id"]
        access = profile.get("access_state", "")
        blocked = "permission_required" in access or "login-required" in access or not (profile.get("query_parameters") or profile.get("search_path_template"))
        rows.append(dict(key=key, name=key.title(), tool="crawl4ai", url=profile["entry_url"],
                         scope="Profile-defined public search; partial coverage", limitation=access,
                         connectable=not blocked, verification="partial_or_unverified"))
        if profile.get("primary_ats_url"):
            rows[-1].update(tool="ats_scrapers", url=profile["primary_ats_url"],
                            fallback_profile=key, fallback_url=profile["entry_url"])
    for item in company_directory():
        rows.append(dict(key="ats-" + item["provider"] + "-" + item["board"].lower(), name=item["company"],
                         tool="ats_scrapers", url=item["url"], scope="This employer board only",
                         limitation="Local adapter required; no universal catalogue guarantee.", connectable=True,
                         verification="partial" if item["board"] == "stripe" else "not_live_verified"))
    for row in rows:
        path = REPO_ROOT / "oss-tools" / "runtime" / "probes" / ("completion-" + row["key"] + ".json")
        if path.is_file():
            try:
                evidence = json.loads(path.read_text(encoding="utf-8"))
                row["last_probe"] = {field: evidence.get(field) for field in ("checked_at", "outcome", "jobs", "complete_descriptions", "message")}
                if evidence.get("jobs", 0) > 0: row["verification"] = "live_checked_partial"
            except (OSError, ValueError, TypeError): pass
    return rows


def specification(key, configuration=None):
    result = next((row for row in catalog() if row["key"] == key), None)
    if result is None and key.startswith("ats-user-") and configuration:
        from .contracts import validate_public_url
        from .catalog import ATS_API_DOMAINS
        url = validate_public_url(configuration.get("url"), tuple(domain for domains in ATS_API_DOMAINS.values() for domain in domains))
        result = dict(key=key, name=str(configuration.get("company") or "Employer")[:150], tool="ats_scrapers",
                      url=url, connectable=True, limitation="Exact user-supplied employer board; local resolution required.")
    if not result: raise ValueError("Choose a registered open-source connection.")
    return result


def fetch(key, preferences):
    row = specification(key, preferences.get("_configuration"))
    if not row["connectable"]: raise SourceError(row["limitation"] or "Source needs access setup.", status_code=403)
    from . import jobspy_adapter, ats_adapter, omkar_adapter, crawl_adapter
    tools = {"jobspy": jobspy_adapter.collect, "ats_scrapers": ats_adapter.collect,
             "shine": omkar_adapter.collect, "instahyre": omkar_adapter.collect,
             "internshala": omkar_adapter.collect, "crawl4ai": crawl_adapter.collect}
    roles = preferences.get("target_roles") or ["Software Engineer"]
    locations = preferences.get("locations") or ["India"]
    queries = [(role, location) for role in roles for location in locations]
    # Query age up to 365 is supported by the app; do not truncate it to the
    # smaller upstream parameter. Leave source filtering off and filter locally.
    age = preferences.get("max_posting_age_days")
    upstream_age = age if age and age <= 90 else None
    signature = hashlib.sha256(json.dumps([key, queries, preferences.get("country_code"), age], sort_keys=True).encode()).hexdigest()
    state = {}
    try:
        state = json.loads(preferences.get("_cursor") or "{}")
        if state.get("query") != signature or state.get("v") != 1: state = {}
        index = int(state.get("index", 0))
        if not 0 <= index < len(queries): raise ValueError()
    except (ValueError, TypeError, AttributeError): raise SourceError("Invalid OSS search checkpoint.") from None
    role, location = queries[index]
    source_id = key if row["tool"] != "ats_scrapers" else key[:80]
    route = state.get("route", "primary")
    if route not in {"primary", "fallback"} or (route == "fallback" and not row.get("fallback_profile")):
        raise SourceError("Invalid OSS fallback checkpoint.")
    started = time.monotonic()
    def attempt(which):
        tool = "crawl4ai" if which == "fallback" else row["tool"]
        sid = row["fallback_profile"] if which == "fallback" else source_id
        url = row["fallback_url"] if which == "fallback" else row["url"]
        remaining = int(110 - (time.monotonic() - started))
        if remaining < 5: raise CollectorFailure("timeout", "The shared collection/fallback budget was exhausted.")
        fingerprint = query_fingerprint(sid, tool, role, location, preferences.get("country_code", "in"), upstream_age)
        request = CollectorRequest(source_id=sid, tool=tool, connection_key=key, generation=0,
            query_fingerprint=fingerprint, role=role, location=location, country_code=preferences.get("country_code", "in"),
            max_age_days=upstream_age, entry_url=url, cursor=state.get("cursor") if which == route else None,
            max_results=20 if tool == "jobspy" else 8, max_details=20 if tool == "jobspy" else 8,
            deadline_seconds=min(remaining, 90 if tool in {"crawl4ai", "jobspy"} else 60))
        with _domain_guard:
            domain_lock = _domains.setdefault(urlsplit(url).hostname, threading.Lock())
        with _acquire(domain_lock, started + 110):
            if tool == "crawl4ai":
                with _acquire(_browser, started + 110):
                    remaining = int(110 - (time.monotonic() - started))
                    if remaining < 1: raise CollectorFailure("timeout", "Collection wait exceeded its shared budget.")
                    return tools[tool](replace(request, deadline_seconds=min(request.deadline_seconds, remaining))), tool
            remaining = int(110 - (time.monotonic() - started))
            if remaining < 1: raise CollectorFailure("timeout", "Collection wait exceeded its shared budget.")
            return tools[tool](replace(request, deadline_seconds=min(request.deadline_seconds, remaining))), tool
    try:
        from .cancellation import scope, check
        with scope(preferences.get("_cancel_tokens", [])):
            try: batch, used_tool = attempt(route)
            except CollectorFailure as exc:
                # Only a registered profile may replace a format/adapter failure.
                # Access denials, rate limits and legitimate empty results do not
                # trigger another access path.
                if route != "primary" or not row.get("fallback_profile") or exc.reason.value not in {"unsupported", "changed_format", "invalid_output"}: raise
                batch, used_tool = attempt("fallback")
                route = "fallback"
                batch.warnings.append(f"Registered Crawl4AI fallback used after {exc.reason.value}.")
            check()
    except CollectorFailure as exc:
        error = SourceError(exc.safe_message, exc.retry_after_seconds, exc.status_code)
        error.reason = exc.reason.value
        raise error from None
    snapshot = batch.to_snapshot()
    next_index = index if batch.next_cursor else index + 1
    snapshot.cursor = json.dumps({"v": 1, "query": signature, "index": next_index,
                                 "route": route if batch.next_cursor else "primary", "cursor": batch.next_cursor}) if next_index < len(queries) else None
    for job in snapshot.jobs:
        job.facts.update(collector_version=batch.tool_version, source_family=key, access_route="oss_" + used_tool)
    snapshot.warnings.append(f"{used_tool}: {batch.coverage} coverage; {batch.elapsed_seconds:.1f}s; requests={batch.request_count}.")
    return snapshot


def ledger():
    path = REPO_ROOT / "OSS_DISCOVERY_COVERAGE_PART2.json"
    return json.loads((path if path.exists() else REPO_ROOT / "OSS_SOURCE_COVERAGE.json").read_text(encoding="utf-8"))
