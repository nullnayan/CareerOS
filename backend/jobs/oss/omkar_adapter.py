"""Local-only OmkarCloud collectors with versioned source pagination."""
from __future__ import annotations

import hashlib
import time

from .catalog import OMKAR_SITES, TOOL_VERSIONS
from .contracts import CollectorBatch, CollectorFailure, CollectorRequest, FailureReason
from .cursors import decode_cursor, encode_cursor
from .normalize import normalize_jobs
from .runtime import invoke


def collect(request: CollectorRequest) -> CollectorBatch:
    capability = OMKAR_SITES.get(request.source_id)
    expected_tool = capability.tool if capability else None
    if expected_tool != request.tool or request.tool not in {"instahyre", "internshala", "shine"}:
        raise CollectorFailure(FailureReason.UNSUPPORTED, "Select one supported local OmkarCloud source and board.")
    started = time.monotonic()
    state = decode_cursor(request)
    response = invoke(request.tool, request)
    raw = response.get("jobs")
    if not isinstance(raw, list):
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "OmkarCloud runner returned no jobs array.")
    page = int(state.get("page", 1))
    item_offset = int(state.get("item_offset", 0))
    if page < 1 or page > 500 or item_offset < 0 or item_offset > 1000:
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Source cursor exceeds the supported page window.")
    ids = [str(item.get("id") or item.get("link") or item.get("url") or "") for item in raw if isinstance(item, dict)]
    signature = hashlib.sha256("\n".join(ids).encode()).hexdigest()
    signatures = list(state.get("page_signatures", []))
    repeated = bool(ids) and item_offset == 0 and signature in signatures
    if repeated:
        return CollectorBatch([], None, "unknown", ["Upstream repeated a page; continuation was stopped."],
                              len(raw), None, time.monotonic() - started,
                              response.get("tool_version") or TOOL_VERSIONS[request.tool])
    selected = raw[item_offset:item_offset + request.max_results]
    next_page = response.get("next_page")
    has_more = response.get("has_more")
    if len(raw) > item_offset + request.max_results:
        next_state = {"page": page, "item_offset": item_offset + request.max_results,
                      "page_signatures": signatures[-8:]}
        next_cursor = encode_cursor(request, next_state)
        coverage = "partial"
    elif has_more is True and isinstance(next_page, int) and next_page == page + 1:
        next_cursor = encode_cursor(request, {"page": next_page, "item_offset": 0,
                                              "page_signatures": (signatures + [signature])[-8:]})
        coverage = "partial"
    else:
        next_cursor = None
        coverage = "exhausted" if has_more is False else "unknown"
    jobs, skipped = normalize_jobs(selected, source_id=request.source_id, tool=request.tool,
                                   company_fallback=request.connection_key, max_results=request.max_results)
    warnings = list(response.get("warnings") or [])
    return CollectorBatch(jobs, next_cursor, coverage, warnings, skipped,
                          response.get("request_count"), time.monotonic() - started,
                          response.get("tool_version") or TOOL_VERSIONS[request.tool])
