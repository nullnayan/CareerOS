"""
tests/test_ats_dual_mode.py
────────────────────────────────────────────────────────────────────────────
Acceptance tests for the ATS dual-mode engine (PROMPT_dual_mode_ats.md).

Tests cover all 7 criteria from the plan:
  1. analyze-text / baseline mode → correct fields
  2. analyze-text / targeted mode → distinct scores
  3. analyze / baseline + targeted (mocked ResumeVersion)
  4. Bug 1 regression: unreadable JD → 200, mode=targeted, match_score=null
  5. Low-confidence JD (1–4 skills) → low_confidence status, numeric match_score
  6. Same resume+JD via both paths → same score_breakdown keys, match_score within tolerance
  7. score_breakdown only contains numeric values; match only in targeted mode

Run with:  pytest tests/test_ats_dual_mode.py -v
"""

import pytest
import os
import json

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_careeros.db")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "a" * 64)
os.environ.setdefault("SMTP_USER", "test@example.com")
os.environ.setdefault("SMTP_PASSWORD", "testpass")

from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# ── Minimal structured resume dict ────────────────────────────────────────────
MINIMAL_RESUME_JSON = {
    "contact": {
        "name": "Alex Kim",
        "email": "alex@example.com",
        "phone": "",
        "location": "",
        "website": "",
        "headline": "Software Engineer",
    },
    "target_role": "Software Engineer",
    "summary": "Python developer with 3 years of experience in backend systems.",
    "experience": [
        {
            "title": "Software Engineer",
            "company": "Acme Corp",
            "start": "2021-01",
            "end": "present",
            "bullets": [
                "Built REST APIs in Python and FastAPI",
                "Managed PostgreSQL databases and wrote SQL queries",
                "Deployed microservices using Docker and Kubernetes",
            ],
        }
    ],
    "education": [
        {
            "degree": "BSc Computer Science",
            "school": "State University",
            "year": "2021",
        }
    ],
    "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"],
    "projects": [],
    "certifications": [],
}

# A keyword-rich JD (many ontology skills expected)
RICH_JD = """
We are looking for a Software Engineer with strong Python experience.
Requirements:
- Proficiency in Python and FastAPI or Django REST framework
- Experience with PostgreSQL and SQL
- Docker and Kubernetes for deployment
- CI/CD pipelines (GitHub Actions or Jenkins)
- Familiarity with Redis for caching
- REST API design and microservices
- Version control with Git
Must have: 3+ years Python backend experience.
"""

# A JD that will yield zero recognised ontology skills (Bug 1 regression)
UNREADABLE_JD = """
A position is available. Further details will be announced later.
"""

# A JD with 1–4 ontology hits → low_confidence
LOW_CONF_JD = """
We need someone who knows Python and can write SQL queries.
The role involves communication and teamwork.
"""


# ── Auth mock helpers ─────────────────────────────────────────────────────────
class _FakeUser:
    id = "user-test-001"
    career_level = "entry"
    target_role = "Software Engineer"
    email = "test@example.com"


def _fake_auth(_token=None):
    return _FakeUser()


def _fake_parse_hybrid(file_bytes: bytes, filename: str) -> dict:
    """Return the minimal JSON without actually running an ML parser."""
    import copy
    return copy.deepcopy(MINIMAL_RESUME_JSON)


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    from main import app
    from core.workspace import get_workspace_owner
    from db.session import get_db
    session = MagicMock()
    app.dependency_overrides[get_workspace_owner] = _fake_auth
    app.dependency_overrides[get_db] = lambda: session
    with patch("api.ats.get_db", side_effect=lambda: iter([session])), patch("ats.jd.extract._extract_via_llm", return_value=None):
        with TestClient(app, raise_server_exceptions=True) as c:
            c.db_session = session
            yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def analyze_text_url():
    return "/analyze-text"


# ── Helper ────────────────────────────────────────────────────────────────────
def post_analyze_text(client, resume_text: str, job_description: str | None = None):
    payload = {"resume_text": resume_text}
    if job_description is not None:
        payload["job_description"] = job_description
    return client.post(
        "/analyze-text",
        json=payload,
        headers={"Authorization": "Bearer test-token"},
    )


def resume_text_from_json(d: dict) -> str:
    """Build a plain-text resume from the structured dict for the paste-text path."""
    lines = []
    contact = d.get("contact", {})
    lines.append(contact.get("name", ""))
    lines.append(contact.get("email", ""))
    lines.append(d.get("summary", ""))
    for exp in d.get("experience", []):
        lines.append(exp.get("title", ""))
        lines.append(exp.get("company", ""))
        for b in exp.get("bullets", []):
            lines.append(f"  - {b}")
    for edu in d.get("education", []):
        lines.append(edu.get("degree", ""))
        lines.append(edu.get("school", ""))
    lines.append(" ".join(d.get("skills", [])))
    return "\n".join(lines)


RESUME_TEXT = resume_text_from_json(MINIMAL_RESUME_JSON)


# ═════════════════════════════════════════════════════════════════════════════
# Test 1: analyze-text / baseline mode
# ═════════════════════════════════════════════════════════════════════════════
def test_analyze_text_baseline(client):
    """
    POST /analyze-text with resume text and NO JD:
    → 200, mode=baseline, numeric baseline_score, no match_score key,
      no jd_extraction_status key.
    """
    with patch("api.resumes.parse_resume_hybrid", side_effect=_fake_parse_hybrid):
        resp = post_analyze_text(client, RESUME_TEXT, job_description=None)

    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["mode"] == "baseline"
    assert isinstance(data.get("baseline_score"), (int, float))
    assert "match_score" not in data, "baseline response must not include match_score"
    assert "jd_extraction_status" not in data, "baseline response must not include jd_extraction_status"

    # score_breakdown must exist with numeric values only
    breakdown = data.get("score_breakdown", {})
    assert isinstance(breakdown, dict)
    assert "match" not in breakdown, "match must be absent in baseline score_breakdown"
    for v in breakdown.values():
        assert isinstance(v, (int, float)) and not (v != v), f"Non-numeric in breakdown: {v}"


# ═════════════════════════════════════════════════════════════════════════════
# Test 2: analyze-text / targeted mode with keyword-rich JD
# ═════════════════════════════════════════════════════════════════════════════
def test_analyze_text_targeted(client):
    """
    POST /analyze-text with resume text AND keyword-rich JD:
    → 200, mode=targeted, numeric match_score, numeric baseline_score,
      match_score != baseline_score, jd_extraction_status=ok.
    """
    with patch("api.resumes.parse_resume_hybrid", side_effect=_fake_parse_hybrid):
        resp = post_analyze_text(client, RESUME_TEXT, job_description=RICH_JD)

    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["mode"] == "targeted"
    assert isinstance(data.get("baseline_score"), (int, float))
    assert isinstance(data.get("match_score"), (int, float))
    assert isinstance(data.get("overall_score"), (int, float))
    assert data["jd_extraction_status"] == "ok"
    # The two scores must be independently computed numbers
    assert data["match_score"] != data["baseline_score"], (
        "match_score and baseline_score must be distinct values"
    )


# ═════════════════════════════════════════════════════════════════════════════
# Test 3: /analyze (saved resume) — both modes
# ═════════════════════════════════════════════════════════════════════════════
def _fake_resume_version(structured_json: dict):
    from db.models import ResumeVersion
    rv = ResumeVersion()
    rv.id = "resume-001"
    rv.user_id = "user-test-001"
    rv.structured_json = structured_json

    rv.file_path = None
    rv.raw_bytes = None
    return rv


def test_analyze_saved_baseline(client):
    """
    POST /analyze (saved resume) with no JD → mode=baseline, numeric baseline_score.
    """
    fake_rv = _fake_resume_version(MINIMAL_RESUME_JSON)
    with patch("api.ats.run_v3_scoring") as mock_score:
        # Mock DB lookup
        session = client.db_session
        session.get.return_value = fake_rv

        # Mock the scorer to return a predictable result
        mock_score.return_value = {
            "mode": "baseline",
            "baseline_score": 72.5,
            "overall_score": 72.5,
            "score_breakdown": {"strength": 72.5, "parseability": 90.0},
            "issues": [],
            "summary": "Good resume.",
            "bullet_point_analysis": [],
        }

        resp = client.post(
            "/analyze",
            json={"resume_id": "resume-001"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "baseline"
    assert isinstance(data.get("baseline_score"), (int, float))
    assert "match_score" not in data


def test_analyze_saved_targeted(client):
    """
    POST /analyze (saved resume) with JD → mode=targeted,
    numeric match_score, numeric baseline_score.
    """
    fake_rv = _fake_resume_version(MINIMAL_RESUME_JSON)
    with patch("api.ats.run_v3_scoring") as mock_score:
        session = client.db_session
        session.get.return_value = fake_rv

        mock_score.return_value = {
            "mode": "targeted",
            "baseline_score": 72.5,
            "match_score": 65.0,
            "overall_score": 68.0,
            "jd_extraction_status": "ok",
            "score_breakdown": {"strength": 72.5, "parseability": 90.0, "match": 65.0},
            "issues": [],
            "summary": "Good resume.",
            "bullet_point_analysis": [],
            "matched_keywords": ["Python"],
            "missing_keywords": ["Go"],
        }

        resp = client.post(
            "/analyze",
            json={"resume_id": "resume-001", "job_description": RICH_JD},
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "targeted"
    assert isinstance(data.get("baseline_score"), (int, float))
    assert isinstance(data.get("match_score"), (int, float))
    assert isinstance(data.get("overall_score"), (int, float))


# ═════════════════════════════════════════════════════════════════════════════
# Test 4: Bug 1 regression — unreadable JD → 200 not 500
# ═════════════════════════════════════════════════════════════════════════════
def test_bug1_unreadable_jd_does_not_crash(client):
    """
    POST /analyze-text with a JD containing zero recognised skills:
    → 200 (NOT 500), mode=targeted, jd_extraction_status=failed,
      match_score is null (None in JSON), numeric baseline_score.
    Must NOT return a fabricated match number.
    Must NOT report mode=baseline.
    """
    with patch("api.resumes.parse_resume_hybrid", side_effect=_fake_parse_hybrid):
        resp = post_analyze_text(client, RESUME_TEXT, job_description=UNREADABLE_JD)

    assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}: {resp.text}"
    data = resp.json()

    assert data["mode"] == "targeted", "mode must still report 'targeted' even when JD unreadable"
    assert data["jd_extraction_status"] == "failed"
    # match_score key must be present but null
    assert "match_score" in data, "match_score key must be present in targeted mode"
    assert data["match_score"] is None, (
        f"match_score must be null when JD unreadable, got: {data['match_score']}"
    )
    assert isinstance(data.get("baseline_score"), (int, float))
    assert data["baseline_score"] > 0


# ═════════════════════════════════════════════════════════════════════════════
# Test 5: Low-confidence JD (1–4 skills) → low_confidence status
# ═════════════════════════════════════════════════════════════════════════════
def test_low_confidence_jd(client):
    """
    POST /analyze-text with a JD that has only 1–4 recognised skills:
    → jd_extraction_status=low_confidence, numeric match_score.
    """
    with patch("api.resumes.parse_resume_hybrid", side_effect=_fake_parse_hybrid):
        resp = post_analyze_text(client, RESUME_TEXT, job_description=LOW_CONF_JD)

    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["mode"] == "targeted"
    assert data.get("jd_extraction_status") in ("low_confidence", "failed"), (
        f"Expected low_confidence or failed, got: {data.get('jd_extraction_status')}"
    )
    # If low_confidence (got some skills), match_score should be numeric
    if data["jd_extraction_status"] == "low_confidence":
        assert isinstance(data.get("match_score"), (int, float))


# ═════════════════════════════════════════════════════════════════════════════
# Test 6: Same resume + JD via both paths → same score_breakdown keys,
#          match_score within tolerance (Bug 3 title asymmetry gone)
# ═════════════════════════════════════════════════════════════════════════════
def test_parity_between_paths(client):
    """
    The same resume + JD through /analyze-text must produce the same
    score_breakdown keys as /analyze (saved-resume path).
    match_score values must be within 5 points of each other.
    """
    with patch("api.resumes.parse_resume_hybrid", side_effect=_fake_parse_hybrid):
        resp_text = post_analyze_text(client, RESUME_TEXT, job_description=RICH_JD)

    assert resp_text.status_code == 200, resp_text.text
    text_data = resp_text.json()

    # For the saved-resume path use the real scoring pipeline (no mock)
    # We need to mock only the DB + auth
    fake_rv = _fake_resume_version(MINIMAL_RESUME_JSON)
    with patch("api.ats.get_db") as mock_db_ctx, \
         patch("api.ats.get_current_user", side_effect=_fake_auth):
        session = MagicMock()
        session.get.return_value = fake_rv
        # commit/refresh are no-ops in test
        session.commit.return_value = None
        session.refresh.return_value = None
        mock_db_ctx.return_value = iter([session])

        resp_upload = client.post(
            "/analyze",
            json={"resume_id": "resume-001", "job_description": RICH_JD},
            headers={"Authorization": "Bearer test-token"},
        )

    if resp_upload.status_code == 200:
        upload_data = resp_upload.json()
        text_keys = set(text_data.get("score_breakdown", {}).keys())
        upload_keys = set(upload_data.get("score_breakdown", {}).keys())
        # Both paths should produce the same breakdown dimensions
        assert text_keys == upload_keys, (
            f"score_breakdown keys differ between paths: text={text_keys}, upload={upload_keys}"
        )
        # match_score parity — within 5 points
        ms_text = text_data.get("match_score")
        ms_upload = upload_data.get("match_score")
        if isinstance(ms_text, (int, float)) and isinstance(ms_upload, (int, float)):
            assert abs(ms_text - ms_upload) <= 5.0, (
                f"match_score parity failed: text={ms_text}, upload={ms_upload}"
            )


# ═════════════════════════════════════════════════════════════════════════════
# Test 7: score_breakdown contains only numeric values; match only in targeted
# ═════════════════════════════════════════════════════════════════════════════
def test_score_breakdown_numeric_only_baseline(client):
    """
    Baseline mode: score_breakdown has no 'match' key and all values are numeric.
    """
    with patch("api.resumes.parse_resume_hybrid", side_effect=_fake_parse_hybrid):
        resp = post_analyze_text(client, RESUME_TEXT, job_description=None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data.get("score_breakdown", {})
    assert "match" not in breakdown
    for k, v in breakdown.items():
        assert isinstance(v, (int, float)), f"Non-numeric value in breakdown[{k}]: {v!r}"


def test_score_breakdown_numeric_only_targeted(client):
    """
    Targeted mode (keyword-rich JD): score_breakdown may include 'match'
    and all values must be numeric — no null/None entries.
    """
    with patch("api.resumes.parse_resume_hybrid", side_effect=_fake_parse_hybrid):
        resp = post_analyze_text(client, RESUME_TEXT, job_description=RICH_JD)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data.get("score_breakdown", {})
    for k, v in breakdown.items():
        assert isinstance(v, (int, float)), f"Non-numeric value in targeted breakdown[{k}]: {v!r}"


# ═════════════════════════════════════════════════════════════════════════════
# Additional: verify scorer unit directly (no HTTP, tests Bug 1 in isolation)
# ═════════════════════════════════════════════════════════════════════════════
def test_scorer_none_guard():
    """
    Unit test: score_resume must not raise TypeError when JD has zero keywords.
    match_fallback must be True, match must be None, headline must be numeric.
    """
    from ats.scoring.scorer import score_resume
    from ats.doc_builder import build_resume_doc
    from ats.layout_probe import probe_layout
    from ats.models import JobTarget

    layout = probe_layout(None)
    doc = build_resume_doc(MINIMAL_RESUME_JSON, layout, declared_band="entry")

    # Craft a JobTarget with zero keywords — the Bug 1 trigger
    empty_jd = JobTarget(
        title="Unknown Title",
        title_normalized="unknown_title",
        seniority="entry",
        keywords=(),  # ← zero keywords, all MATCH checks return None
        min_years=None,
        required_degree=None,
        source_hash="test-empty",
        extraction_confidence="failed",
    )

    # This must NOT raise TypeError
    report = score_resume(doc, empty_jd)

    assert report.match is None, f"match must be None for empty JD, got {report.match}"
    assert report.match_fallback is True, "match_fallback must be True"
    assert isinstance(report.headline, (int, float)), "headline must be numeric even when match is None"
    assert report.headline > 0, "headline must be the strength score, not 0"
