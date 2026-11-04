"""Retained legacy regression suites explicitly opt into archived execution.

OSS tests exercise the production-default OSS mode, with separate integration
assertions proving that the old paths cannot execute there.
"""
import pytest


@pytest.fixture(autouse=True)
def discovery_test_mode(request, monkeypatch):
    if not request.node.path.name.startswith("test_oss"):
        from core.config import settings
        monkeypatch.setattr(settings, "JOB_DISCOVERY_ENGINE", "legacy")
        monkeypatch.setattr(settings, "JOB_LEGACY_ENABLED", True)
