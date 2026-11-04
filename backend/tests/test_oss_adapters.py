from __future__ import annotations

import json

import pytest

from jobs.oss import ats_adapter, crawl_adapter, jobspy_adapter, omkar_adapter
from jobs.oss.contracts import (CollectorFailure, CollectorRequest, FailureReason,
                                query_fingerprint)
from jobs.oss.cursors import decode_cursor


def request(tool, source, *, cursor=None, entry_url=None, max_results=1, country="IN"):
    role, location = "software engineer", "Bengaluru"
    return CollectorRequest(source_id=source, tool=tool, connection_key=source,
                            generation=2, query_fingerprint=query_fingerprint(source, tool, role, location, country),
                            role=role, location=location, country_code=country,
                            cursor=cursor, entry_url=entry_url, max_results=max_results,
                            max_details=1, deadline_seconds=30)


def job(job_id, url=None):
    url = url or f"https://jobs.example.com/{job_id}"
    return {"id": job_id, "title": "Software Engineer", "company": "Example",
            "location": "Bengaluru", "job_url": url, "job_url_direct": url,
            "description": "Excerpt", "description_complete": False}


def test_jobspy_adapter_uses_offset_cursor_and_continues_when_overlap_has_new_jobs(monkeypatch):
    req = request("jobspy", "indeed")
    monkeypatch.setattr(jobspy_adapter, "invoke", lambda *_: {
        "jobs": [job("one")], "warnings": [], "upstream_errors": {},
        "request_count": 4, "tool_version": "python-jobspy 1.4.1",
    })
    first = jobspy_adapter.collect(req)
    assert first.coverage == "partial"
    assert first.jobs[0].facts["collector_tool"] == "jobspy"
    assert first.request_count == 4
    assert decode_cursor(request("jobspy", "indeed", cursor=first.next_cursor))["offset"] == 1

    next_request = request("jobspy", "indeed", cursor=first.next_cursor)
    monkeypatch.setattr(jobspy_adapter, "invoke", lambda *_: {
        "jobs": [job("one"), job("two")], "warnings": [], "upstream_errors": {},
        "request_count": 2, "tool_version": "python-jobspy 1.4.1",
    })
    second = jobspy_adapter.collect(next_request)
    assert [record.native_id for record in second.jobs] == ["two"]
    assert second.next_cursor is not None
    assert second.coverage == "partial"
    assert decode_cursor(request("jobspy", "indeed", cursor=second.next_cursor))["offset"] == 3
    assert any("Overlapping" in warning for warning in second.warnings)


def test_jobspy_repeated_page_and_source_errors_are_not_reported_as_empty_success(monkeypatch):
    req = request("jobspy", "indeed")
    state = {"offset": 20, "seen_ids": ["one"], "page_signatures": []}
    from jobs.oss.cursors import encode_cursor
    req = request("jobspy", "indeed", cursor=encode_cursor(req, state))
    monkeypatch.setattr(jobspy_adapter, "invoke", lambda *_: {
        "jobs": [job("one")], "warnings": [], "upstream_errors": {"indeed": "429 rate limit"},
        "request_count": 1,
    })
    batch = jobspy_adapter.collect(req)
    assert batch.coverage == "unknown"
    assert batch.next_cursor is None
    assert any("partial error" in warning for warning in batch.warnings)


def test_ats_adapter_normalizes_local_fetch_details_and_request_count(monkeypatch):
    req = request("ats_scrapers", "stripe", entry_url="https://job-boards.greenhouse.io/stripe")
    monkeypatch.setattr(ats_adapter, "invoke", lambda *_: {
        "jobs": [{"ats_id": "gh-1", "title": "Software Engineer", "company": "Stripe",
                  "location": "Remote", "url": "https://job-boards.greenhouse.io/stripe/jobs/1",
                  "apply_url": "https://job-boards.greenhouse.io/stripe/jobs/1",
                  "description": "Long description", "description_complete": True}],
        "coverage": "exhausted", "warnings": [], "request_count": 3,
        "tool_version": "ats-scrapers 0.3.0",
    })
    batch = ats_adapter.collect(req)
    assert batch.coverage == "exhausted"
    assert batch.request_count == 3
    assert batch.jobs[0].complete is True
    assert batch.jobs[0].facts["source_id"] == "stripe"


def test_omkar_adapter_pages_source_native_items_and_retains_stipend_period(monkeypatch):
    req = request("shine", "shine")
    monkeypatch.setattr(omkar_adapter, "invoke", lambda *_: {
        "jobs": [{"id": 17, "title": "Software Engineer", "company": "Example",
                  "location": "Bengaluru", "link": "https://www.shine.com/job-search/17",
                  "salary": {"min_amount": 50000, "currency": "INR", "period": "monthly"},
                  "experience": "2-4 years"}],
        "has_more": True, "next_page": 2, "request_count": 2,
        "warnings": [], "tool_version": "shine-scraper/ec9c0978",
    })
    batch = omkar_adapter.collect(req)
    assert batch.coverage == "partial"
    assert batch.request_count == 2
    assert batch.jobs[0].facts["salary_period"] == "monthly"
    assert batch.jobs[0].facts["experience"] == "2-4 years"
    state = decode_cursor(request("shine", "shine", cursor=batch.next_cursor))
    assert state["page"] == 2


def test_omkar_adapter_stops_repeated_pages(monkeypatch):
    req = request("shine", "shine")
    from jobs.oss.cursors import encode_cursor
    state = {"page": 2, "page_signatures": ["bad"]}
    req = request("shine", "shine", cursor=encode_cursor(req, state))
    row = {"id": 17, "title": "Software Engineer", "company": "Example",
           "location": "Bengaluru", "link": "https://www.shine.com/jobs/17"}
    import hashlib
    signature = hashlib.sha256("17".encode()).hexdigest()
    req = request("shine", "shine", cursor=encode_cursor(req, {"page": 2, "page_signatures": [signature]}))
    monkeypatch.setattr(omkar_adapter, "invoke", lambda *_: {"jobs": [row], "has_more": True, "next_page": 3})
    batch = omkar_adapter.collect(req)
    assert batch.jobs == []
    assert batch.next_cursor is None
    assert batch.coverage == "unknown"


def test_crawl_adapter_uses_profile_and_runner_signatures_in_cursor(monkeypatch):
    req = request("crawl4ai", "cutshort", entry_url="https://cutshort.io/jobs")
    assert crawl_adapter.load_profile("cutshort")["approved_domains"] == ["cutshort.io"]
    monkeypatch.setattr(crawl_adapter, "invoke", lambda *_: {
        "jobs": [job("cutshort-17", "https://cutshort.io/jobs/17")],
        "next_url": "https://cutshort.io/jobs?page=2", "coverage": "partial",
        "page_signatures": ["page-one-signature"], "request_count": 7,
        "tool_version": "Crawl4AI 0.9.5",
    })
    batch = crawl_adapter.collect(req)
    assert batch.coverage == "partial"
    assert batch.request_count == 7
    state = decode_cursor(request("crawl4ai", "cutshort", cursor=batch.next_cursor))
    assert state["next_url"] == "https://cutshort.io/jobs?page=2"
    assert state["page_signatures"] == ["page-one-signature"]


@pytest.mark.parametrize("source_id,expected", [
    ("wellfound", FailureReason.BLOCKED),
    ("superset", FailureReason.LOGIN_REQUIRED),
])
def test_crawl_adapter_enforces_recorded_access_gates_without_invoking_runner(monkeypatch, source_id, expected):
    def unexpected(*_):
        raise AssertionError("a gated source must not invoke the external runner")
    monkeypatch.setattr(crawl_adapter, "invoke", unexpected)
    url = "https://wellfound.com/jobs" if source_id == "wellfound" else "https://app.joinsuperset.com/"
    req = request("crawl4ai", source_id, entry_url=url)
    with pytest.raises(CollectorFailure) as error:
        crawl_adapter.collect(req)
    assert error.value.reason is expected


def test_crawl_adapter_rejects_continuation_escape(monkeypatch):
    req = request("crawl4ai", "cutshort", entry_url="https://cutshort.io/jobs")
    monkeypatch.setattr(crawl_adapter, "invoke", lambda *_: {"jobs": [], "next_url": "https://127.0.0.1/admin"})
    with pytest.raises(CollectorFailure) as error:
        crawl_adapter.collect(req)
    assert error.value.reason is FailureReason.INVALID_OUTPUT
