"""Small JSON boundary shared by isolated collectors and CareerOS."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit
import ipaddress


class FailureReason(str, Enum):
    CANCELLED = "cancelled"
    UNSUPPORTED = "unsupported"
    RUNTIME_MISSING = "runtime_missing"
    LOGIN_REQUIRED = "login_required"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"
    CHANGED_FORMAT = "changed_format"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    INVALID_OUTPUT = "invalid_output"


class CollectorFailure(Exception):
    """A safe, typed source failure. Raw third-party exception strings stay private."""

    def __init__(self, reason: FailureReason | str, safe_message: str,
                 status_code: int | None = None, retry_after_seconds: int | None = None):
        self.reason = FailureReason(reason)
        self.safe_message = str(safe_message)[:240]
        self.status_code = status_code if isinstance(status_code, int) and 100 <= status_code <= 599 else None
        self.retry_after_seconds = retry_after_seconds if isinstance(retry_after_seconds, int) and 0 <= retry_after_seconds <= 86400 else None
        super().__init__(self.safe_message)

    def to_dict(self) -> dict[str, Any]:
        return {"reason": self.reason.value, "safe_message": self.safe_message,
                "status_code": self.status_code, "retry_after_seconds": self.retry_after_seconds}


_IDENT = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,79}$", re.I)
_FINGERPRINT = re.compile(r"^[a-f0-9]{64}$")
_TOOLS = {"jobspy", "ats_scrapers", "instahyre", "internshala", "shine", "crawl4ai"}
_SENSITIVE_QUERY_KEY = re.compile(r"(?:access[_-]?token|api[_-]?key|authorization|auth[_-]?token|client[_-]?secret|cookie|password|session(?:id)?|signature|^sig$|^token$|^key$)", re.I)
_REQUEST_FIELDS = {"source_id", "tool", "connection_key", "generation", "query_fingerprint",
                   "role", "location", "country_code", "max_age_days", "entry_url", "cursor",
                   "max_results", "max_details", "deadline_seconds"}


def query_fingerprint(source_id: str, tool: str, role: str, location: str,
                      country_code: str, max_age_days: int | None = None) -> str:
    payload = {"source_id": source_id.strip().lower(), "tool": tool.strip().lower(),
               "role": " ".join(role.split()).casefold(), "location": " ".join(location.split()).casefold(),
               "country_code": country_code.strip().upper(), "max_age_days": max_age_days}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_public_url(value: str, approved_domains: tuple[str, ...] | list[str] = ()) -> str:
    """Accept HTTPS public destinations only; never fetch application links here."""
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("URL is missing or exceeds the 2048-character limit.")
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        raise ValueError("URL is malformed.") from None
    if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password or port not in (None, 443):
        raise ValueError("Use a public HTTPS URL without credentials or a custom port.")
    if any(_SENSITIVE_QUERY_KEY.search(key) for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        raise ValueError("Credential-like query parameters are not accepted in collector URLs.")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid")) or "." not in host:
        raise ValueError("Local or non-public URL hosts are not supported.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Private or reserved URL addresses are not supported.")
    if approved_domains and not any(host == d.lower() or host.endswith("." + d.lower()) for d in approved_domains):
        raise ValueError("URL host is outside the approved source domains.")
    return value.strip()


@dataclass(frozen=True)
class CollectorRequest:
    source_id: str
    tool: str
    connection_key: str
    generation: int
    query_fingerprint: str
    role: str
    location: str
    country_code: str
    max_age_days: int | None = None
    entry_url: str | None = None
    cursor: str | None = None
    max_results: int = 20
    max_details: int = 0
    deadline_seconds: int = 60

    def __post_init__(self) -> None:
        for name, value in (("source_id", self.source_id), ("tool", self.tool), ("connection_key", self.connection_key)):
            if not isinstance(value, str) or not _IDENT.fullmatch(value):
                raise ValueError(f"{name} must be a short identifier.")
        if self.tool not in _TOOLS:
            raise ValueError("tool is not one of the isolated OSS runtimes.")
        if not isinstance(self.generation, int) or isinstance(self.generation, bool) or self.generation < 0:
            raise ValueError("generation must be a non-negative integer.")
        if not isinstance(self.query_fingerprint, str) or not _FINGERPRINT.fullmatch(self.query_fingerprint):
            raise ValueError("query_fingerprint must be a SHA-256 hex digest.")
        for name, value, limit in (("role", self.role, 200), ("location", self.location, 180)):
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError(f"{name} must contain 1 to {limit} characters.")
        if not isinstance(self.country_code, str) or not re.fullmatch(r"[A-Za-z]{2}", self.country_code):
            raise ValueError("country_code must be an ISO 3166-1 alpha-2 code.")
        if self.max_age_days is not None and (not isinstance(self.max_age_days, int) or not 1 <= self.max_age_days <= 90):
            raise ValueError("max_age_days must be between 1 and 90.")
        if self.entry_url is not None:
            validate_public_url(self.entry_url)
        if self.cursor is not None and (not isinstance(self.cursor, str) or len(self.cursor) > 8192):
            raise ValueError("cursor exceeds the 8192-character limit.")
        if not isinstance(self.max_results, int) or not 1 <= self.max_results <= 20:
            raise ValueError("max_results must be between 1 and 20.")
        if not isinstance(self.max_details, int) or not 0 <= self.max_details <= 20:
            raise ValueError("max_details must be between 0 and 20.")
        if not isinstance(self.deadline_seconds, int) or not 1 <= self.deadline_seconds <= 120:
            raise ValueError("deadline_seconds must be between 1 and 120.")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CollectorRequest":
        unknown = set(value) - _REQUEST_FIELDS
        if unknown:
            raise ValueError("Collector request contains unsupported fields.")
        return cls(**dict(value))

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NormalizedJob:
    native_id: str
    title: str
    company: str
    location: str
    apply_url: str
    description: str
    complete: bool
    published_at: datetime | None = None
    facts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.published_at:
            result["published_at"] = self.published_at.isoformat()
        return result


@dataclass
class CollectorBatch:
    jobs: list[NormalizedJob]
    next_cursor: str | None
    coverage: str
    warnings: list[str] = field(default_factory=list)
    skipped: int = 0
    request_count: int | None = None
    elapsed_seconds: float = 0.0
    tool_version: str = "unknown"

    def __post_init__(self) -> None:
        if self.coverage not in {"partial", "exhausted", "unknown"}:
            raise ValueError("coverage must be partial, exhausted, or unknown.")
        if self.request_count is not None and self.request_count < 0:
            raise ValueError("request_count cannot be negative.")
        self.elapsed_seconds = max(0.0, min(float(self.elapsed_seconds), 3600.0))
        self.warnings = [str(w)[:240] for w in self.warnings[:40]]

    def to_dict(self) -> dict[str, Any]:
        return {"jobs": [job.to_dict() for job in self.jobs], "next_cursor": self.next_cursor,
                "coverage": self.coverage, "warnings": self.warnings, "skipped": self.skipped,
                "request_count": self.request_count, "elapsed_seconds": self.elapsed_seconds,
                "tool_version": self.tool_version}

    def to_snapshot(self):
        """Convert to CareerOS ingestion shape, always non-exhaustive at catalogue scope."""
        from jobs.connectors import Listing, Snapshot
        from jobs.salary import salary_facts

        listings = []
        for job in self.jobs:
            facts = salary_facts(job.description, dict(job.facts))
            listings.append(Listing(job.native_id, job.title, job.company, job.location,
                                    job.apply_url, job.description, job.complete,
                                    job.published_at, facts))
        return Snapshot(listings, complete=False, scope="rolling_feed", pages=1,
                        cursor=self.next_cursor, skipped=self.skipped,
                        warnings=list(self.warnings),
                        truncation_reason=None if self.coverage == "exhausted" else self.coverage,
                        traversal_valid=False, traversal_end=False,
                        board_version=self.tool_version)
