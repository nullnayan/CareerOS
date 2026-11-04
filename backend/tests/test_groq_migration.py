"""No live AI calls: verify credential selection, bounded failures, and repairs."""
import json
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from agents import llm_client
from core.agent_models import AGENT_MODELS
from core.groq_keys import TASK_GROUPS, key_for_task, routing_status
from services.latex_compiler import compilation_failure
from services.local_embeddings import get_embeddings_batch
from tailoring.latex import category_regions, patch as patch_source
from tailoring.selection import select


@pytest.fixture(autouse=True)
def reset_cooldowns(monkeypatch):
    monkeypatch.setenv("GROQ_KEYS_INDEPENDENT_ORGANIZATIONS", "false")
    llm_client._cooldowns.clear()
    yield
    llm_client._cooldowns.clear()


def successful_response(content='{"ok": true}'):
    response = MagicMock(status_code=200)
    response.json.return_value = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
    return response


def test_all_tasks_use_groq_and_have_explicit_key_groups():
    assert set(AGENT_MODELS) == set(TASK_GROUPS)
    assert all(provider == "groq" for provider, _ in AGENT_MODELS.values())


@pytest.mark.parametrize("task,group", [("resume_parser", "PARSING"), ("chat_rag", "CHAT"),
    ("jd_skill_extractor", "TAILORING"), ("latex_repair", "TAILORING"), ("bullet_rewriter", "ATS"), ("intent_classifier", "CLASSIFICATION")])
def test_tasks_use_their_own_credentials(monkeypatch, task, group):
    monkeypatch.setenv("GROQ_API_KEY_" + group, "test-secret-for-" + group)
    with patch("agents.llm_client.httpx.post", return_value=successful_response()) as post:
        assert json.loads(llm_client.LLMClient(task).generate("JSON only", "Check", True))["ok"]
    headers = post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-secret-for-" + group
    assert post.call_args.args[0] == "https://api.groq.com/openai/v1/chat/completions"


def test_rate_limit_does_not_rotate_credentials(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY_PARSING", "key-parsing")
    monkeypatch.setenv("GROQ_API_KEY_CHAT", "key-chat")
    response = MagicMock(status_code=429, headers={"retry-after": "10"})
    with patch("agents.llm_client.httpx.post", return_value=response) as post:
        with pytest.raises(llm_client.GroqRateLimitError):
            llm_client.LLMClient("resume_parser").generate("system", "user")
        with pytest.raises(llm_client.GroqRateLimitError):
            llm_client.LLMClient("chat_rag").generate("system", "user")
        assert post.call_count == 1


def test_auth_error_does_not_leak_key_or_response(monkeypatch):
    secret = "private-synthetic-value"
    monkeypatch.setenv("GROQ_API_KEY_CHAT", secret)
    response = MagicMock(status_code=401, text=secret)
    with patch("agents.llm_client.httpx.post", return_value=response):
        with pytest.raises(RuntimeError) as caught:
            llm_client.LLMClient("chat_rag").generate("system", "user")
    assert secret not in str(caught.value)
    assert "GROQ_API_KEY_CHAT" in str(caught.value)
    assert secret not in json.dumps(routing_status())


def test_vision_uses_actual_multimodal_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY_PARSING", "synthetic-key")
    with patch("agents.llm_client.httpx.post", return_value=successful_response("Test image")) as post:
        assert llm_client.LLMClient("image_analysis").generate_vision("system", "user", b"image", "image/png") == "Test image"
    payload = post.call_args.kwargs["json"]
    assert payload["model"] == "qwen/qwen3.8-27b"
    assert payload["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_embeddings_have_no_provider_dependency():
    model = MagicMock()
    model.embed.return_value = iter([np.array([.1] * 384), np.array([.2] * 384)])
    with patch("services.local_embeddings._model", return_value=model):
        result = get_embeddings_batch(["first", "second"])
    assert len(result) == 2 and len(result[0]) == 384


def test_compile_error_is_short_but_retains_diagnostics():
    log = "package loading\n./main.tex:188: LaTeX Error: Something's wrong--perhaps a missing \\item.\nfull diagnostics"
    error = compilation_failure(log)
    assert "line 188" in str(error) and "nested list" in str(error)
    assert "package loading" not in str(error)
    assert error.diagnostics == log


def test_escaped_category_names_remain_patchable():
    source = r"\begin{document}\section{Skills}\textbf{Databases \& Data}{: SQLite}\section{Projects}Example\end{document}"
    assert "Databases & Data" in category_regions(source)
    candidates, _ = select("Requirements:\nMongoDB is essential for this graduate role.", "SQLite", ["Databases & Data"], {})
    assert candidates[0]["category"] == "Databases & Data"
    result, _ = patch_source(source, [{"name": "MongoDB", "category": "Databases & Data"}])
    assert result == source.replace("{: SQLite}", "{: SQLite, MongoDB}")
