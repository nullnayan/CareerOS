"""Direct company-careers adapter around local ats-scrapers resolution."""
from __future__ import annotations

import time

from .catalog import TOOL_VERSIONS
from .contracts import CollectorBatch, CollectorFailure, CollectorRequest, FailureReason
from .normalize import normalize_jobs
from .runtime import invoke
from .cursors import decode_cursor, encode_cursor


def collect(request: CollectorRequest) -> CollectorBatch:
    if request.tool != "ats_scrapers":
        raise CollectorFailure(FailureReason.UNSUPPORTED, "ats-scrapers requires its dedicated tool request.")
    if not request.entry_url:
        raise CollectorFailure(FailureReason.UNSUPPORTED, "Provide the employer's exact public careers URL.")
    started = time.monotonic()
    decode_cursor(request)
    response = invoke("ats_scrapers", request)
    raw = response.get("jobs")
    if not isinstance(raw, list):
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "ats-scrapers runner returned no jobs array.")
    jobs, skipped = normalize_jobs(raw, source_id=request.source_id, tool="ats_scrapers",
                                   company_fallback=request.connection_key, max_results=request.max_results)
    next_cursor = encode_cursor(request, response["next_state"]) if response.get("next_state") else None
    return CollectorBatch(jobs, next_cursor, response.get("coverage", "unknown"),
                          list(response.get("warnings") or []), skipped + int(response.get("skipped", 0)),
                          response.get("request_count"), time.monotonic() - started,
                          response.get("tool_version") or TOOL_VERSIONS["ats_scrapers"])
