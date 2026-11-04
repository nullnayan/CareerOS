"""Versioned, query-bound cursors for source-specific continuation."""
from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Mapping

from .contracts import CollectorFailure, CollectorRequest, FailureReason

CURSOR_VERSION = 1


def encode_cursor(request: CollectorRequest, state: Mapping[str, Any]) -> str:
    value = {"v": CURSOR_VERSION, "tool": request.tool, "source_id": request.source_id,
             "query_fingerprint": request.query_fingerprint, "state": dict(state)}
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    if len(encoded) > 8192:
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Collector cursor exceeded its size limit.")
    return encoded


def decode_cursor(request: CollectorRequest) -> dict[str, Any]:
    if not request.cursor:
        return {}
    try:
        raw = base64.urlsafe_b64decode(request.cursor + "=" * (-len(request.cursor) % 4))
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict) or value.get("v") != CURSOR_VERSION:
            raise ValueError
        if value.get("tool") != request.tool or value.get("source_id") != request.source_id:
            raise ValueError
        if value.get("query_fingerprint") != request.query_fingerprint:
            raise ValueError
        state = value.get("state")
        if not isinstance(state, dict):
            raise ValueError
        return state
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Cursor is invalid or belongs to a different query or collector version.") from None
