from __future__ import annotations

import math

from jobs.oss.normalize import normalize_job, normalize_jobs, plain_text


def test_normalizer_handles_nan_html_dates_salary_and_application_links():
    job = normalize_job({
        "id": "external-17", "title": "<b>Software</b> Engineer", "company": {"name": "Example Co"},
        "locations": ["Bengaluru", "Remote"], "job_url": "https://board.example/jobs/17",
        "job_url_direct": "https://apply.example/17", "description": "<p>Salary INR 5 LPA</p>",
        "date_posted": "2026-10-30T10:15:00+05:30", "validThrough": "2026-12-31",
        "salary": {"min_amount": float("nan"), "max_amount": 900000, "currency": "INR", "period": "yearly"},
    }, source_id="example", tool="fixture")
    assert job is not None
    assert job.title == "Software Engineer"
    assert job.company == "Example Co"
    assert job.location == "Bengaluru, Remote"
    assert job.apply_url == "https://apply.example/17"
    assert job.published_at.isoformat() == "2026-10-30T04:45:00"
    assert job.facts["original_application_url"] == "https://apply.example/17"
    assert job.facts["salary_min"] is None
    assert job.facts["salary_max"] == 900000
    assert job.facts["salary_evidence"] == "source_fields"
    assert job.facts["application_deadline"] == "2026-12-31"


def test_normalizer_rejects_private_or_credential_bearing_urls_and_uses_stable_ids():
    base = {"title": "Engineer", "company": "Example", "location": "Remote"}
    for url in ("http://example.com/job", "https://127.0.0.1/job",
                "https://jobs.example.com/job?token=secret", "javascript:alert(1)"):
        assert normalize_job({**base, "url": url}, source_id="x", tool="fixture") is None
    first = normalize_job({**base, "url": "https://jobs.example.com/a"}, source_id="x", tool="fixture")
    second = normalize_job({**base, "url": "https://jobs.example.com/a"}, source_id="x", tool="fixture")
    assert first.native_id == second.native_id


def test_dedup_skips_bad_records_and_never_marks_description_complete_by_default():
    rows = [
        {"id": "one", "title": "Engineer", "company": "Example", "url": "https://jobs.example/1"},
        {"id": "one", "title": "Engineer", "company": "Example", "url": "https://jobs.example/1"},
        {"title": "", "company": "Example", "url": "https://jobs.example/2"},
        {"id": "two", "title": "Analyst", "company": "Example", "url": "https://jobs.example/2"},
    ]
    jobs, skipped = normalize_jobs(rows, source_id="x", tool="fixture", max_results=10)
    assert [job.native_id for job in jobs] == ["one", "two"]
    assert skipped == 2
    assert all(job.complete is False for job in jobs)


def test_estimated_salary_is_not_promoted_and_description_text_remains_evidence():
    estimated = normalize_job({
        "id": "e", "title": "Engineer", "company": "Example", "url": "https://jobs.example/e",
        "salary_min": 800000, "salary_currency": "INR", "salary_period": "annual",
        "salary_source": "estimated",
    }, source_id="x", tool="fixture")
    assert "salary_min" not in estimated.facts
    assert estimated.facts["original_salary_source"] == "estimated"
    text_pay = normalize_job({
        "id": "d", "title": "Engineer", "company": "Example", "url": "https://jobs.example/d",
        "description": "Compensation: INR 5 LPA", "salary_source": "description",
    }, source_id="x", tool="fixture")
    assert text_pay.facts["salary_evidence"] == "description"
    assert text_pay.facts["original_salary_source"] == "description"


def test_plain_text_removes_script_style_and_caps_body_size():
    assert plain_text("<script>private()</script><style>x</style><p>Job &amp; team</p>") == "Job & team"
    assert len(plain_text("x" * 100, limit=12)) == 12
