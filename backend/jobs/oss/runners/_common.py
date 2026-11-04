"""Runner-side JSON protocol. Upstream output is kept away from stdout."""
from __future__ import annotations

from contextlib import redirect_stdout
import json
import sys
import base64
import binascii
from typing import Any, Callable


class RunnerFailure(Exception):
    def __init__(self, reason: str, safe_message: str, status_code: int | None = None,
                 retry_after_seconds: int | None = None):
        self.reason = reason
        self.safe_message = safe_message[:240]
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(safe_message)


def decode_cursor(request: dict[str, Any]) -> dict[str, Any]:
    raw_cursor = request.get("cursor")
    if not raw_cursor:
        return {}
    try:
        raw = base64.urlsafe_b64decode(raw_cursor + "=" * (-len(raw_cursor) % 4))
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict) or value.get("v") != 1:
            raise ValueError
        if value.get("tool") != request.get("tool") or value.get("source_id") != request.get("source_id"):
            raise ValueError
        if value.get("query_fingerprint") != request.get("query_fingerprint"):
            raise ValueError
        state = value.get("state")
        if not isinstance(state, dict):
            raise ValueError
        return state
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        raise RunnerFailure("invalid_output", "Cursor is invalid or belongs to a different query or collector version.") from None


def read_request() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(128 * 1024 + 1)
    if len(raw) > 128 * 1024:
        raise RunnerFailure("invalid_output", "Collector input exceeded its size limit.")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise RunnerFailure("invalid_output", "Collector input must be a JSON object.")
    return value


def emit(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()


def serve(run: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    try:
        request = read_request()
        with redirect_stdout(sys.stderr):
            result = run(request)
        if not isinstance(result, dict):
            raise RunnerFailure("invalid_output", "Collector returned an invalid response.")
        emit(result)
    except RunnerFailure as exc:
        emit({"failure": {"reason": exc.reason, "safe_message": exc.safe_message,
                          "status_code": exc.status_code, "retry_after_seconds": exc.retry_after_seconds}})
    except Exception as exc:
        # Never surface arbitrary upstream exception text: it can contain a
        # signed URL, header, cookie, query token, or proxy credential.
        name = type(exc).__name__.lower()
        reason = "timeout" if "timeout" in name else "blocked" if "blocked" in name else "transport"
        emit({"failure": {"reason": reason, "safe_message": "Upstream collection failed; see isolated diagnostics.",
                          "status_code": None, "retry_after_seconds": None}})
