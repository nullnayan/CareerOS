"""Groq-only text/vision client with task-scoped credentials and bounded retries.

Embedding compatibility exports run locally and never call a hosted AI service.
"""
import base64
import json
import logging
import math
import re
import time
from threading import Lock
import httpx
from dotenv import load_dotenv
from core.agent_models import AGENT_MODELS, AGENT_MAX_TOKENS
from core.groq_keys import key_candidates_for_task, independent_organizations
from services.local_embeddings import get_embedding, get_embeddings_batch

load_dotenv()
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_cooldowns: dict[tuple[str, str], float] = {}
_cooldown_lock = Lock()
logger = logging.getLogger(__name__)


class GroqRateLimitError(RuntimeError):
    def __init__(self, retry_after: int, independent: bool = False):
        self.retry_after = retry_after
        message = "All configured independent Groq organizations are currently limited for this model." if independent else "Task keys share organization limits; no key switching was attempted."
        super().__init__(f"Groq is rate-limited. Retry in {retry_after} seconds. {message}")


class LLMClient:
    def __init__(self, agent_name: str):
        if agent_name not in AGENT_MODELS:
            raise ValueError(f"Unknown AI task: {agent_name}")
        self.agent_name = agent_name
        self.provider, self.model = AGENT_MODELS[agent_name]
        if self.provider != "groq":
            raise ValueError("CareerOS supports only Groq for hosted AI.")

    def _request(self, messages: list, json_mode: bool) -> str:
        waits = []
        candidates = key_candidates_for_task(self.agent_name)
        for key, variable, scope in candidates:
            try:
                return self._request_with_key(messages, json_mode, key, variable, scope)
            except GroqRateLimitError as error:
                waits.append(error.retry_after)
        with _cooldown_lock:
            deadlines = [_cooldowns[(scope, self.model)] for _, _, scope in candidates if (scope, self.model) in _cooldowns]
        retry = max(1, math.ceil(min(deadlines) - time.monotonic())) if deadlines else min(waits) if waits else 60
        raise GroqRateLimitError(retry, independent=independent_organizations())

    def _request_with_key(self, messages: list, json_mode: bool, key: str, variable: str, scope: str) -> str:
        quota = (scope, self.model)
        with _cooldown_lock:
            remaining = _cooldowns.get(quota, 0) - time.monotonic()
        if remaining > 0:
            raise GroqRateLimitError(max(1, int(remaining) + 1))
        payload = {"model": self.model, "messages": messages, "temperature": 0 if self.agent_name == "latex_repair" else 0.2,
                   "max_completion_tokens": AGENT_MAX_TOKENS[self.agent_name],
                   "reasoning_effort": "none" if self.model.startswith("qwen/") else "low"}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        response = None
        network_attempts = 1 if self.agent_name == "latex_repair" else 3
        for attempt in range(network_attempts):
            try:
                response = httpx.post(GROQ_BASE_URL + "/chat/completions", headers=headers, json=payload, timeout=30 if self.agent_name == "latex_repair" else 45)
            except (httpx.TimeoutException, httpx.ConnectError):
                if attempt == network_attempts - 1:
                    raise RuntimeError("Groq repair request timed out. Try again later." if network_attempts == 1 else "Groq connection timed out after three attempts. Try again later.") from None
                time.sleep(2 ** attempt)
                continue
            status = response.status_code
            logger.info("Groq task=%s model=%s credential=%s status=%s", self.agent_name, self.model, variable, status)
            if status == 429:
                try:
                    retry = max(1, min(86400, int(float(response.headers.get("retry-after", "60")) + 1)))
                except ValueError:
                    retry = 60
                with _cooldown_lock:
                    _cooldowns[quota] = time.monotonic() + retry
                try:
                    detail = str(response.json().get("error", {}).get("message", "")).lower()
                except (ValueError, TypeError, AttributeError):
                    detail = ""
                metric = next((name for name in ("tokens per minute", "tokens per day", "requests per minute", "requests per day") if name in detail), "provider quota")
                logger.warning("Groq %s limited for %s (%s); retry after %ss; trying an available backup.", metric, self.agent_name, variable, retry)
                raise GroqRateLimitError(retry)
            if status in {500, 502, 503, 504} and attempt < network_attempts - 1:
                time.sleep(2 ** attempt)
                continue
            if status == 401:
                raise RuntimeError(f"Groq rejected the {variable} credential (401). Update that task's key and restart the backend.")
            if status == 403:
                raise RuntimeError(f"Groq denied access to model {self.model}. Check the project's model permissions.")
            if status == 404:
                raise RuntimeError(f"Groq model {self.model} is unavailable. Check the configured model ID.")
            if status >= 400:
                # Do not forward raw upstream responses: they can contain request data.
                raise RuntimeError(f"Groq returned HTTP {status} for task {self.agent_name}. Check model availability and request limits.")
            break
        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") == "length":
                raise RuntimeError("Groq output reached its limit. Try a shorter input.")
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError("Groq returned no usable content.")
            if json_mode:
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
                json.loads(content)
            return content
        except (KeyError, IndexError, json.JSONDecodeError, TypeError):
            raise RuntimeError("Groq returned an invalid response. No output was applied.") from None

    def generate(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
        if json_mode:
            system_prompt += "\nReturn only valid JSON; no Markdown or commentary."
        return self._request([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], json_mode)

    def generate_vision(self, system_prompt: str, user_prompt: str, image_bytes: bytes,
                        mime_type: str, json_mode: bool = False) -> str:
        if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("Vision requires a PNG, JPEG, or WebP image. Render PDF pages first.")
        if len(image_bytes) > 8_000_000:
            raise ValueError("Image exceeds the 8 MB upload limit. Resize it first.")
        if json_mode:
            system_prompt += "\nReturn only valid JSON."
        content = [{"type": "text", "text": user_prompt}, {"type": "image_url", "image_url": {
            "url": f"data:{mime_type};base64," + base64.b64encode(image_bytes).decode("ascii")}}]
        return self._request([{"role": "system", "content": system_prompt}, {"role": "user", "content": content}], json_mode)
