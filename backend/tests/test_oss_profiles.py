from __future__ import annotations

import json
from pathlib import Path

from jobs.oss.crawl_adapter import PROFILE_DIR, load_profile
from jobs.oss.contracts import validate_public_url


def test_source_profiles_are_parseable_and_use_approved_https_domains():
    profiles = [json.loads(path.read_text(encoding="utf-8"))
                for path in PROFILE_DIR.glob("*.json") if path.name != "company_portal.template.json"]
    assert len(profiles) >= 12
    assert len({profile["source_id"] for profile in profiles}) == len(profiles)
    for profile in profiles:
        assert profile["preferred_tool"] == "crawl4ai"
        assert profile["approved_domains"]
        assert profile["max_pages"] <= 3
        assert profile["max_details"] <= 8
        validate_public_url(profile["official_url"], profile["approved_domains"])
        validate_public_url(profile["entry_url"], profile["approved_domains"])
        assert profile["robots_required"] is True
        assert profile["challenge_indicators"]


def test_company_profile_carries_official_identity_but_not_a_guessed_ats_slug():
    for source, company, domain in (("cognizant", "Cognizant", "cognizant.com"),
                                    ("tcs", "TCS", "tcs.com"),
                                    ("infosys", "Infosys", "infosys.com"),
                                    ("wipro", "Wipro", "wipro.com"),
                                    ("accenture", "Accenture", "accenture.com"),
                                    ("deloitte", "Deloitte", "deloitte.com")):
        profile = load_profile(source)
        assert profile["company_fallback"] == company
        assert profile["approved_domains"] == [domain]
        assert "unverified" in profile["access_state"]
        assert "slug" not in profile


def test_permission_and_login_states_are_explicit():
    assert "permission_required" in load_profile("wellfound")["access_state"]
    assert "login-required" in load_profile("superset")["access_state"]
    assert "cookie" in load_profile("unstop")["access_state"]
