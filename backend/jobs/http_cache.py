"""Bounded process-local HTTP validators for public JSON only.

Every call revalidates with the provider. Never serve stale data after errors,
cache credentials, or alter the scheduler's polling/backoff deadlines.
"""
from collections import OrderedDict
from threading import Lock

_entries = OrderedDict()
_lock = Lock()
MAX_BYTES = 32_000_000


def get(key):
    with _lock:
        entry = _entries.get(key)
        if entry: _entries.move_to_end(key)
        return entry


def put(key, body, headers):
    values = {}
    for name in ("ETag", "Last-Modified", "Cache-Control", "Vary"):
        value = headers.get(name) if headers else None
        values[name] = value if isinstance(value, str) else ""
    forbidden = values["Cache-Control"].lower()
    if "no-store" in forbidden or "private" in forbidden or values["Vary"]:
        with _lock: _entries.pop(key, None)
        return
    if not values["ETag"] and not values["Last-Modified"]: return
    validators = {k: v for k, v in (("If-None-Match", values["ETag"]), ("If-Modified-Since", values["Last-Modified"])) if v}
    with _lock:
        _entries[key] = (body, validators)
        _entries.move_to_end(key)
        while len(_entries) > 64 or sum(len(item[0]) for item in _entries.values()) > MAX_BYTES:
            _entries.popitem(last=False)


def clear():
    with _lock: _entries.clear()
