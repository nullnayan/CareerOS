"""Compact text routing and task-specific output budgets; no real provider calls."""
from unittest.mock import MagicMock, patch
import pytest
from agents import llm_client
from core.agent_models import AGENT_MODELS, AGENT_MAX_TOKENS, FAST_MODEL, REPAIR_MODEL, VISION_MODEL
from core.groq_keys import TASK_GROUPS


@pytest.fixture(autouse=True)
def clear_cooldowns(monkeypatch):
    llm_client._cooldowns.clear()
    monkeypatch.setattr(llm_client, "key_candidates_for_task", lambda task: [("synthetic", "GROQ_API_KEY_TEST", "test")])
    yield
    llm_client._cooldowns.clear()


def success():
    response = MagicMock(status_code=200)
    response.json.return_value = {"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]}
    return response


def test_every_task_has_explicit_model_key_group_and_output_budget():
    assert set(AGENT_MODELS) == set(AGENT_MAX_TOKENS) == set(TASK_GROUPS)
    for task, (provider, model) in AGENT_MODELS.items():
        assert provider == "groq"
        if task in {"resume_vision_parser", "image_analysis"}:
            assert model == VISION_MODEL
        elif task == "latex_repair":
            assert model == REPAIR_MODEL
        else:
            assert model == FAST_MODEL
    assert AGENT_MAX_TOKENS["chat_rag"] == 1024
    assert AGENT_MAX_TOKENS["latex_repair"] == 8192
    assert all(256 <= AGENT_MAX_TOKENS[task] <= 512 for task in ("intent_classifier", "push_intent", "skill_classifier", "sanity_checker", "chat_rerank"))


@pytest.mark.parametrize("task", list(AGENT_MODELS))
def test_request_uses_task_budget_and_low_or_disabled_reasoning(task):
    with patch("agents.llm_client.httpx.post", return_value=success()) as post:
        llm_client.LLMClient(task).generate("JSON only", "Check", True)
    payload = post.call_args.kwargs["json"]
    assert payload["model"] == AGENT_MODELS[task][1]
    assert payload["max_completion_tokens"] == AGENT_MAX_TOKENS[task]
    assert payload["reasoning_effort"] == ("none" if task in {"latex_repair", "resume_vision_parser", "image_analysis"} else "low")
    assert payload["response_format"] == {"type": "json_object"}


def test_shared_org_cooldowns_are_per_model_not_global():
    limited = MagicMock(status_code=429, headers={"retry-after": "10"})
    with patch("agents.llm_client.httpx.post", side_effect=[limited, success()]) as post:
        with pytest.raises(llm_client.GroqRateLimitError):
            llm_client.LLMClient("latex_repair").generate("system", "source")
        assert llm_client.LLMClient("chat_rag").generate("system", "question")
    assert post.call_count == 2
