from __future__ import annotations

import base64
import json

import pytest

from jobs.oss.contracts import (CollectorBatch, CollectorFailure, CollectorRequest,
                                FailureReason, NormalizedJob, query_fingerprint,
                                validate_public_url)
from jobs.oss.cursors import decode_cursor, encode_cursor


def make_request(**overrides):
    values = dict(source_id="cutshort", tool="crawl4ai", connection_key="cutshort",
                  generation=4, query_fingerprint=query_fingerprint(
                      "cutshort", "crawl4ai", "software engineer", "Bengaluru", "IN"),
                  role="software engineer", location="Bengaluru", country_code="IN",
                  max_results=2, max_details=1, deadline_seconds=30)
    values.update(overrides)
    return CollectorRequest(**values)


def test_request_bounds_and_sensitive_urls_are_enforced():
    request = make_request(entry_url="https://cutshort.io/jobs")
    assert request.max_results == 2
    for url in ("http://cutshort.io/jobs", "https://127.0.0.1/jobs",
                "https://cutshort.io/jobs?access_token=secret",
                "https://cutshort.io:8443/jobs", "https://user:pass@cutshort.io/jobs"):
        with pytest.raises(ValueError):
            validate_public_url(url, ("cutshort.io",))
    with pytest.raises(ValueError):
        make_request(max_results=21)
    with pytest.raises(ValueError):
        make_request(deadline_seconds=121)


def test_cursor_is_versioned_bound_to_source_and_query_and_rejects_corruption():
    request = make_request()
    cursor = encode_cursor(request, {"next_url": "https://cutshort.io/jobs?page=2"})
    assert decode_cursor(make_request(cursor=cursor)) == {"next_url": "https://cutshort.io/jobs?page=2"}
    other_query = make_request(query_fingerprint="0" * 64, cursor=cursor)
    with pytest.raises(CollectorFailure) as error:
        decode_cursor(other_query)
    assert error.value.reason is FailureReason.INVALID_OUTPUT
    with pytest.raises(CollectorFailure):
        decode_cursor(make_request(cursor="%%%"))
    raw = json.dumps({"v": 99, "tool": "crawl4ai", "source_id": "cutshort",
                      "query_fingerprint": request.query_fingerprint, "state": {}}).encode()
    wrong_version = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    with pytest.raises(CollectorFailure):
        decode_cursor(make_request(cursor=wrong_version))


def test_batch_snapshot_never_grants_catalogue_closure_and_keeps_salary_evidence():
    job = NormalizedJob(
        native_id="42", title="Engineer", company="Example", location="India",
        apply_url="https://jobs.example.com/42", description="Compensation: INR 50,000 monthly",
        complete=False, facts={"salary_min": 50000, "salary_currency": "INR",
                               "salary_period": "monthly", "salary_evidence": "description",
                               "original_salary_source": "description"})
    batch = CollectorBatch([job], None, "exhausted", tool_version="fixture")
    snapshot = batch.to_snapshot()
    assert snapshot.complete is False
    assert snapshot.scope == "rolling_feed"
    assert snapshot.traversal_valid is False
    assert snapshot.traversal_end is False
    assert snapshot.jobs[0].facts["annual_salary_min_inr"] == 600000
    assert snapshot.jobs[0].facts["salary_evidence"] == "description"


def test_estimated_pay_stays_unverified_after_snapshot_conversion():
    job = NormalizedJob(
        native_id="43", title="Engineer", company="Example", location="India",
        apply_url="https://jobs.example.com/43", description="Estimated salary INR 900000 annually",
        complete=False, facts={"salary_min": 900000, "salary_currency": "INR",
                               "salary_period": "annual", "salary_evidence": "source_fields",
                               "original_salary_source": "estimated"})
    snapshot = CollectorBatch([job], None, "partial").to_snapshot()
    assert "salary_min" not in snapshot.jobs[0].facts
    assert "annual_salary_min_inr" not in snapshot.jobs[0].facts
    assert snapshot.jobs[0].facts["original_salary_source"] == "estimated"
