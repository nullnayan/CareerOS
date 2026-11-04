"""Independent-organization quota fallback; synthetic credentials only."""
import json
from unittest.mock import MagicMock, patch
import pytest
from agents import llm_client
from core.groq_keys import KEY_GROUPS, TASK_GROUPS, key_candidates_for_task, routing_status


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setenv("GROQ_KEYS_INDEPENDENT_ORGANIZATIONS", "true")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    for group in KEY_GROUPS: monkeypatch.setenv("GROQ_API_KEY_" + group.upper(), "synthetic-" + group)
    llm_client._cooldowns.clear()
    monkeypatch.setattr(llm_client.time, "monotonic", lambda: 100.0)
    yield
    llm_client._cooldowns.clear()


def response(status=200, retry="10"):
    result = MagicMock(status_code=status, headers={"retry-after": retry})
    result.json.return_value = {"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]}
    return result


@pytest.mark.parametrize("task", list(TASK_GROUPS))
def test_every_task_has_its_primary_and_four_independent_backups(task):
    candidates = key_candidates_for_task(task)
    assert len(candidates) == 5
    assert candidates[0][1] == "GROQ_API_KEY_" + TASK_GROUPS[task].upper()
    assert len({scope for _, _, scope in candidates}) == 5


def test_rate_limited_primary_falls_back_and_is_skipped_until_reset():
    with patch("agents.llm_client.httpx.post", side_effect=[response(429), response(), response()]) as post:
        client = llm_client.LLMClient("latex_repair")
        assert json.loads(client.generate("system", "source", True))["ok"]
        assert json.loads(client.generate("system", "source", True))["ok"]
    calls = post.call_args_list
    assert [c.kwargs["headers"]["Authorization"] for c in calls] == ["Bearer synthetic-tailoring", "Bearer synthetic-ats", "Bearer synthetic-ats"]
    assert calls[0].kwargs["json"] == calls[1].kwargs["json"]


def test_all_keys_limited_returns_earliest_retry_without_repeating_keys():
    with patch("agents.llm_client.httpx.post", side_effect=[response(429, str(delay)) for delay in [45, 10, 30, 20, 40]]) as post:
        with pytest.raises(llm_client.GroqRateLimitError) as error:
            llm_client.LLMClient("latex_repair").generate("system", "source", True)
        assert error.value.retry_after == 11 and post.call_count == 5
        assert "independent" in str(error.value)
        with pytest.raises(llm_client.GroqRateLimitError):
            llm_client.LLMClient("latex_repair").generate("system", "source", True)
        assert post.call_count == 5


def test_shared_organization_policy_never_rotates_keys(monkeypatch):
    monkeypatch.setenv("GROQ_KEYS_INDEPENDENT_ORGANIZATIONS", "false")
    with patch("agents.llm_client.httpx.post", return_value=response(429)) as post:
        with pytest.raises(llm_client.GroqRateLimitError): llm_client.LLMClient("latex_repair").generate("system", "source")
        with pytest.raises(llm_client.GroqRateLimitError): llm_client.LLMClient("image_analysis").generate("system", "resume")
    assert post.call_count == 1


def test_duplicate_credentials_are_not_treated_as_extra_quota(monkeypatch):
    for group in KEY_GROUPS: monkeypatch.setenv("GROQ_API_KEY_" + group.upper(), "same-synthetic-key")
    assert len(key_candidates_for_task("latex_repair")) == 1
    assert all(not group["backup_variables"] for group in routing_status())


def test_missing_primary_can_use_configured_backup(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY_TAILORING")
    candidates = key_candidates_for_task("latex_repair")
    assert len(candidates) == 4 and candidates[0][1] == "GROQ_API_KEY_ATS"


def test_auth_failure_is_reported_without_retrying_other_organizations():
    with patch("agents.llm_client.httpx.post", return_value=response(401)) as post:
        with pytest.raises(RuntimeError, match="GROQ_API_KEY_TAILORING"):
            llm_client.LLMClient("latex_repair").generate("system", "source")
    assert post.call_count == 1


def test_routing_status_exposes_only_variable_names_and_configuration():
    status = routing_status()
    assert all(group["independent_organization_backups"] and len(group["backup_variables"]) == 4 for group in status)
    assert "synthetic-" not in json.dumps(status)


def test_invalid_routing_policy_defaults_to_shared_quota(monkeypatch, tmp_path):
    import core.groq_keys as keys
    monkeypatch.delenv("GROQ_KEYS_INDEPENDENT_ORGANIZATIONS")
    policy = tmp_path / "policy.json"; policy.write_text("[]")
    monkeypatch.setattr(keys, "ROUTING_POLICY_FILE", policy)
    assert len(key_candidates_for_task("latex_repair")) == 1
