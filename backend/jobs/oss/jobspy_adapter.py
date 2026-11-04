"""JobSpy 1.4.1 one-board adapter. No implicit all-sites execution."""
from __future__ import annotations

import hashlib
import time

from .catalog import JOBSPY_SITES, TOOL_VERSIONS
from .contracts import CollectorBatch, CollectorFailure, CollectorRequest, FailureReason
from .cursors import decode_cursor, encode_cursor
from .normalize import normalize_jobs
from .runtime import invoke


def collect(request: CollectorRequest) -> CollectorBatch:
    if request.tool != "jobspy" or request.source_id not in JOBSPY_SITES:
        raise CollectorFailure(FailureReason.UNSUPPORTED, "JobSpy requires one explicitly supported board per request.")
    started = time.monotonic()
    state = decode_cursor(request)
    response = invoke("jobspy", request)
    raw = response.get("jobs")
    if not isinstance(raw, list):
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "JobSpy runner returned no jobs array.")
    warnings = list(response.get("warnings") or [])
    upstream_errors = response.get("upstream_errors") or {}
    if upstream_errors:
        warnings.extend(f"{site}: upstream source reported a partial error ({message})." for site, message in list(upstream_errors.items())[:8])
    raw_ids = [str(item.get("id") or item.get("job_url") or "") for item in raw if isinstance(item, dict)]
    signature = hashlib.sha256("\n".join(raw_ids).encode()).hexdigest()
    signatures = list(state.get("page_signatures", []))
    previous_ids = list(dict.fromkeys(str(x) for x in state.get("seen_ids", [])))
    previous_set = set(previous_ids)
    repeated = bool(raw_ids) and signature in signatures
    fresh = [record for record in raw if str(record.get("id") or record.get("job_url") or "") not in previous_set]
    jobs, skipped = normalize_jobs(fresh, source_id=request.source_id, tool="jobspy",
                                   company_fallback="", max_results=request.max_results)
    warnings = [str(w)[:240] for w in warnings[:30]]
    if repeated or (raw_ids and not fresh):
        warnings.append("The upstream board repeated a page at a later offset; continuation was stopped.")
        return CollectorBatch(jobs, None, "unknown", warnings, skipped + max(0, len(raw) - len(fresh)),
                              response.get("request_count"), time.monotonic() - started, response.get("tool_version") or TOOL_VERSIONS["jobspy"])
    if raw_ids and any(identity in previous_set for identity in raw_ids):
        warnings.append("Overlapping results were deduplicated; continuation retained while the source makes progress.")
    offset = int(state.get("offset", 0))
    if len(raw) >= request.max_results and not upstream_errors:
        signatures = (signatures + [signature])[-8:]
        seen_ids = list(dict.fromkeys(previous_ids + raw_ids))[-160:]
        next_cursor = encode_cursor(request, {"offset": offset + len(raw), "page_signatures": signatures,
                                              "seen_ids": seen_ids})
        coverage = "partial"
    elif upstream_errors:
        next_cursor = None
        coverage = "partial" if jobs else "unknown"
    elif not raw:
        next_cursor = None
        coverage = "unknown"
    else:
        next_cursor = None
        coverage = "exhausted"
    return CollectorBatch(jobs, next_cursor, coverage, warnings, skipped,
                          response.get("request_count"), time.monotonic() - started, response.get("tool_version") or TOOL_VERSIONS["jobspy"])
