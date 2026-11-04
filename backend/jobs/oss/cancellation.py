"""Cross-process cancellation markers; tokens never become filesystem paths."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
from .catalog import RUNTIME_ROOT
from .contracts import CollectorFailure

_tokens = ContextVar("oss_cancellation", default=())


def token(owner, kind, identifier):
    return hashlib.sha256(f"{owner}:{kind}:{identifier}".encode()).hexdigest()


def marker(value):
    # Rehash even internal tokens; callers cannot inject relative paths.
    return RUNTIME_ROOT / "cancel" / (hashlib.sha256(value.encode()).hexdigest() + ".cancel")


def cancel(value):
    path = marker(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def reset(value):
    marker(value).unlink(missing_ok=True)


def cancelled():
    return any(marker(value).exists() for value in _tokens.get())


def check():
    if cancelled(): raise CollectorFailure("cancelled", "Collection was cancelled; its owned process tree was stopped.")


@contextmanager
def scope(values):
    handle = _tokens.set(tuple(values))
    try:
        check()
        yield
    finally: _tokens.reset(handle)
