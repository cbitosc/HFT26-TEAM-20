"""LLMClient interface and the Featherless implementation (OpenAI-compatible chat completions).

Fixed by code, not configuration: temperature 0. Pinned by configuration: the model id. Recorded per
call: the model id the API returned, latency and token usage. Retries: timeouts, connection errors,
HTTP 429 and 5xx, with exponential backoff; other 4xx responses are not retried.

The API key is held as a SecretStr, sent only in the Authorization header, and never logged,
returned, stored or included in an exception message or repr. Prompts are not logged either.
"""
import logging
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import httpx2 as httpx
from pydantic import SecretStr

log = logging.getLogger("app.llm")

TEMPERATURE = 0
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class LLMResponse:
    text: str
    requested_model: str
    returned_model: str | None
    latency_seconds: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    attempts: int


class LLMError(Exception):
    code = "LLM_ERROR"

    def __init__(self, message: str, *, attempts: int = 1):
        super().__init__(message)
        self.message = message
        self.attempts = attempts


class LLMUnavailableError(LLMError):
    """Timeouts, connection failures or retryable HTTP statuses, after every retry."""

    code = "LLM_UNAVAILABLE"


class LLMRequestRejectedError(LLMError):
    """A non-retryable HTTP error such as 400 or 401."""

    code = "LLM_REQUEST_REJECTED"


class LLMBadResponseError(LLMError):
    """HTTP 200 with a body that is not a usable chat completion."""

    code = "LLM_BAD_RESPONSE"


class LLMClient(Protocol):
    def complete(self, *, model: str, system: str, user: str) -> LLMResponse:
        """One chat completion at temperature 0. Raises an LLMError subclass on failure."""
        ...


def _int_or_none(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class FeatherlessClient:
    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        timeout_seconds: float,
        max_retries: int,
        backoff_seconds: float,
        max_tokens: int,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if api_key is None or not api_key.get_secret_value().strip():
            raise ValueError("an API key is required")
        self._key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._backoff = backoff_seconds
        self._max_tokens = max_tokens
        self._transport = transport
        self._sleep = sleep

    def __repr__(self) -> str:  # never show the key
        return f"FeatherlessClient(url={self._url!r}, key=<hidden>)"

    def complete(self, *, model: str, system: str, user: str) -> LLMResponse:
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": TEMPERATURE,
            "max_tokens": self._max_tokens,
        }
        headers = {"Authorization": f"Bearer {self._key.get_secret_value()}", "Content-Type": "application/json"}
        attempts_allowed = self._max_retries + 1
        last_problem = "no attempt made"
        with httpx.Client(timeout=self._timeout, transport=self._transport) as http:
            for attempt in range(1, attempts_allowed + 1):
                started = time.perf_counter()
                try:
                    response = http.post(self._url, json=payload, headers=headers)
                except httpx.TimeoutException:
                    last_problem = "request timed out"
                except httpx.TransportError as exc:
                    last_problem = f"connection error ({type(exc).__name__})"
                else:
                    latency = time.perf_counter() - started
                    status = response.status_code
                    if status == 200:
                        return self._parse(response, model, latency, attempt)
                    if status not in RETRYABLE_STATUS:
                        raise LLMRequestRejectedError(f"the provider rejected the request (HTTP {status})",
                                                      attempts=attempt)
                    last_problem = f"HTTP {status}"
                if attempt < attempts_allowed:
                    delay = self._backoff * (2 ** (attempt - 1))
                    log.warning("LLM call failed (%s); retry %d of %d in %.1fs", last_problem, attempt,
                                self._max_retries, delay)
                    self._sleep(delay)
        raise LLMUnavailableError(f"the provider is unavailable after {attempts_allowed} attempt(s): {last_problem}",
                                  attempts=attempts_allowed)

    @staticmethod
    def _parse(response, model: str, latency: float, attempt: int) -> LLMResponse:
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMBadResponseError("the provider returned a malformed completion", attempts=attempt) from None
        if not isinstance(text, str):
            raise LLMBadResponseError("the provider returned a non-text completion", attempts=attempt)
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        returned = data.get("model") if isinstance(data.get("model"), str) else None
        return LLMResponse(
            text=text, requested_model=model, returned_model=returned, latency_seconds=latency,
            prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
            completion_tokens=_int_or_none(usage.get("completion_tokens")),
            total_tokens=_int_or_none(usage.get("total_tokens")), attempts=attempt,
        )


def make_featherless_client(settings) -> FeatherlessClient:
    return FeatherlessClient(
        api_key=settings.featherless_api_key,
        base_url=settings.featherless_base_url,
        timeout_seconds=settings.api_timeout_seconds,
        max_retries=settings.llm_max_retries,
        backoff_seconds=settings.llm_backoff_seconds,
        max_tokens=settings.llm_max_tokens,
    )
