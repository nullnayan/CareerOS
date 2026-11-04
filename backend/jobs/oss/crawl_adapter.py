"""Crawl4AI source-profile adapter with fixed domains and resumable page URLs."""
from __future__ import annotations

import json
from pathlib import Path
import time

from .catalog import REPO_ROOT, TOOL_VERSIONS
from .contracts import CollectorBatch, CollectorFailure, CollectorRequest, FailureReason, validate_public_url
from .cursors import decode_cursor, encode_cursor
from .normalize import normalize_jobs
from .runtime import invoke


PROFILE_DIR = Path(__file__).resolve().parent / "profiles"


def load_profile(source_id: str) -> dict:
    path = PROFILE_DIR / f"{source_id}.json"
    if not path.is_file():
        raise CollectorFailure(FailureReason.UNSUPPORTED, "No tested Crawl4AI source profile is registered.")
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Crawl4AI source profile is malformed.") from None
    if not isinstance(profile, dict) or profile.get("source_id") != source_id:
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Crawl4AI source profile identity does not match.")
    return profile


def collect(request: CollectorRequest) -> CollectorBatch:
    if request.tool != "crawl4ai":
        raise CollectorFailure(FailureReason.UNSUPPORTED, "Crawl4AI requires a dedicated profile request.")
    profile = load_profile(request.source_id)
    access_state = str(profile.get("access_state", ""))
    if "permission_required" in access_state.casefold():
        raise CollectorFailure(FailureReason.BLOCKED, "The source's reviewed terms require a permitted export or agreement before unattended collection.")
    if "login-required" in access_state.casefold():
        raise CollectorFailure(FailureReason.LOGIN_REQUIRED, "This source does not expose a public job-search route.")
    domains = tuple(profile.get("approved_domains") or ())
    if not domains:
        raise CollectorFailure(FailureReason.UNSUPPORTED, "This profile has no approved public source domains.")
    entry_url = request.entry_url or profile.get("entry_url")
    if not entry_url:
        raise CollectorFailure(FailureReason.UNSUPPORTED, "This source profile needs an approved entry URL.")
    try:
        validate_public_url(entry_url, domains)
    except ValueError:
        raise CollectorFailure(FailureReason.BLOCKED, "Entry URL is outside the profile's approved public source domains.") from None
    started = time.monotonic()
    state = decode_cursor(request)
    response = invoke("crawl4ai", request)
    raw = response.get("jobs")
    if not isinstance(raw, list):
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Crawl4AI runner returned no jobs array.")
    next_url = response.get("next_url")
    next_cursor = None
    coverage = response.get("coverage", "unknown")
    warnings = list(response.get("warnings") or [])
    if next_url:
        try:
            validate_public_url(next_url, domains)
        except ValueError:
            raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Crawl4AI continuation escaped the approved source domain.") from None
        next_cursor = encode_cursor(request, {"next_url": next_url,
                                              "item_offset": int(response.get("item_offset", 0)),
                                              "page_signatures": list(response.get("page_signatures") or state.get("page_signatures", []))[-8:]})
        coverage = "partial"
    jobs, skipped = normalize_jobs(raw, source_id=request.source_id, tool="crawl4ai",
                                   company_fallback=request.connection_key, max_results=request.max_results)
    return CollectorBatch(jobs, next_cursor, coverage, warnings,
                          skipped + int(response.get("skipped", 0)),
                          response.get("request_count"), time.monotonic() - started,
                          response.get("tool_version") or TOOL_VERSIONS["crawl4ai"])
