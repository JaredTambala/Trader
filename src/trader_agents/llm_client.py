"""Provider-neutral LLM client boundary for LangGraph policy nodes."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import os
from typing import Any, Protocol
from urllib import error, request


class LlmConfigurationError(RuntimeError):
    """Raised when no usable LLM runtime configuration is available."""


class LlmRequestError(RuntimeError):
    """Raised when an LLM backend request fails or returns unusable data."""


@dataclass(frozen=True)
class LlmMessage:
    """One provider-neutral chat message."""

    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-native chat message."""
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class LlmJsonRequest:
    """A provider-neutral JSON-response LLM request.

    Attributes:
        messages: Ordered system and public-context messages.
        response_schema: JSON Schema the returned object must satisfy.
        model: Optional request-specific model override.
        temperature: Provider-neutral sampling temperature.
        max_tokens: Maximum generated output tokens.
        thinking: Whether a provider may emit an internal thinking phase. The
            default is false for bounded structured control decisions.
    """

    messages: tuple[LlmMessage, ...]
    response_schema: Mapping[str, Any]
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int = 800
    thinking: bool = False

    def messages_payload(self) -> list[dict[str, str]]:
        """Return provider-neutral message payloads."""
        return [message.to_dict() for message in self.messages]


class LlmClient(Protocol):
    """Minimal async client protocol for structured LLM policy decisions."""

    async def complete_json(self, llm_request: LlmJsonRequest) -> Mapping[str, Any]:
        """Return a JSON-native object emitted by an LLM backend."""


class JsonHttpTransport(Protocol):
    """Small async JSON POST transport used by runtime LLM clients."""

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """POST a JSON payload and return the decoded JSON response."""


@dataclass
class StaticJsonLlmClient:
    """Deterministic fake LLM client for graph and policy tests."""

    responses: Sequence[Mapping[str, Any]]

    def __post_init__(self) -> None:
        """Copy responses and initialize captured requests."""
        self._responses = [dict(response) for response in self.responses]
        self.requests: list[LlmJsonRequest] = []

    async def complete_json(self, llm_request: LlmJsonRequest) -> Mapping[str, Any]:
        """Return the next configured response."""
        self.requests.append(llm_request)
        if not self._responses:
            raise LlmRequestError("StaticJsonLlmClient has no remaining responses")
        return self._responses.pop(0)


@dataclass(frozen=True)
class LlmConfiguration:
    """Runtime LLM backend configuration."""

    provider: str
    model: str
    base_url: str
    api_key: str = ""
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class UrllibJsonTransport:
    """Stdlib JSON HTTP transport to avoid adding runtime dependencies."""

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """POST JSON using urllib in a worker thread."""

        def _post() -> Mapping[str, Any]:
            body = json.dumps(payload).encode("utf-8")
            http_request = request.Request(
                url=url,
                data=body,
                headers={**dict(headers), "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with request.urlopen(http_request, timeout=timeout_seconds) as response:
                    text = response.read().decode("utf-8")
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise LlmRequestError(f"LLM backend returned HTTP {exc.code}: {detail}") from exc
            except error.URLError as exc:
                raise LlmRequestError(f"LLM backend request failed: {exc.reason}") from exc
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError as exc:
                raise LlmRequestError("LLM backend did not return valid JSON") from exc
            if not isinstance(decoded, Mapping):
                raise LlmRequestError("LLM backend returned a non-object JSON payload")
            return decoded

        return await asyncio.to_thread(_post)


@dataclass(frozen=True)
class OpenAICompatibleJsonLlmClient:
    """JSON client for OpenAI-compatible chat completion APIs."""

    config: LlmConfiguration
    transport: JsonHttpTransport = UrllibJsonTransport()

    async def complete_json(self, llm_request: LlmJsonRequest) -> Mapping[str, Any]:
        """Call an OpenAI-compatible chat endpoint and parse JSON content."""
        payload = {
            "model": llm_request.model or self.config.model,
            "messages": llm_request.messages_payload(),
            "temperature": llm_request.temperature,
            "max_tokens": llm_request.max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        response = await self.transport.post_json(
            _join_url(self.config.base_url, "chat/completions"),
            payload,
            headers=headers,
            timeout_seconds=self.config.timeout_seconds,
        )
        choices = response.get("choices")
        if not isinstance(choices, Sequence) or not choices:
            raise LlmRequestError("OpenAI-compatible response did not include choices")
        choice = choices[0]
        if not isinstance(choice, Mapping):
            raise LlmRequestError("OpenAI-compatible choice was not an object")
        message = choice.get("message")
        if not isinstance(message, Mapping):
            raise LlmRequestError("OpenAI-compatible choice did not include a message")
        content = message.get("content")
        return _decode_json_content(content)


@dataclass(frozen=True)
class OllamaJsonLlmClient:
    """JSON client for Ollama chat API backends."""

    config: LlmConfiguration
    transport: JsonHttpTransport = UrllibJsonTransport()

    async def complete_json(self, llm_request: LlmJsonRequest) -> Mapping[str, Any]:
        """Call an Ollama chat endpoint and parse JSON content."""
        payload = {
            "model": llm_request.model or self.config.model,
            "messages": llm_request.messages_payload(),
            "stream": False,
            "format": "json",
            "think": llm_request.thinking,
            "options": {"temperature": llm_request.temperature},
        }
        response = await self.transport.post_json(
            _join_url(self.config.base_url, "api/chat"),
            payload,
            headers={},
            timeout_seconds=self.config.timeout_seconds,
        )
        message = response.get("message")
        if not isinstance(message, Mapping):
            raise LlmRequestError("Ollama response did not include a message")
        return _decode_json_content(message.get("content"))


@dataclass(frozen=True)
class RuntimeConfiguredLlmClient:
    """LLM client that resolves the concrete backend from environment at call time."""

    env: Mapping[str, str] | None = None
    transport: JsonHttpTransport = UrllibJsonTransport()

    async def complete_json(self, llm_request: LlmJsonRequest) -> Mapping[str, Any]:
        """Resolve and call the configured backend."""
        client = build_llm_client_from_env(
            self.env if self.env is not None else os.environ,
            transport=self.transport,
        )
        return await client.complete_json(llm_request)


def build_llm_client_from_env(
    env: Mapping[str, str] | None = None,
    *,
    transport: JsonHttpTransport | None = None,
) -> LlmClient:
    """Build an LLM client from `TRADER_AGENTS_LLM_*` environment variables."""
    source = env if env is not None else os.environ
    provider = _normalized_provider(source.get("TRADER_AGENTS_LLM_PROVIDER", ""))
    if not provider:
        raise LlmConfigurationError("TRADER_AGENTS_LLM_PROVIDER is required")
    model = source.get("TRADER_AGENTS_LLM_MODEL", "").strip()
    if not model:
        raise LlmConfigurationError("TRADER_AGENTS_LLM_MODEL is required")
    timeout = _parse_timeout(source.get("TRADER_AGENTS_LLM_TIMEOUT_SECONDS", "30"))
    selected_transport = transport or UrllibJsonTransport()

    if provider == "ollama":
        config = LlmConfiguration(
            provider=provider,
            model=model,
            base_url=source.get("TRADER_AGENTS_LLM_BASE_URL", "http://localhost:11434").strip(),
            timeout_seconds=timeout,
        )
        return OllamaJsonLlmClient(config=config, transport=selected_transport)

    if provider == "openrouter":
        api_key = source.get("TRADER_AGENTS_LLM_API_KEY", "").strip()
        if not api_key:
            raise LlmConfigurationError("TRADER_AGENTS_LLM_API_KEY is required for openrouter")
        config = LlmConfiguration(
            provider=provider,
            model=model,
            base_url=source.get("TRADER_AGENTS_LLM_BASE_URL", "https://openrouter.ai/api/v1").strip(),
            api_key=api_key,
            timeout_seconds=timeout,
        )
        return OpenAICompatibleJsonLlmClient(config=config, transport=selected_transport)

    if provider == "openai_compatible":
        base_url = source.get("TRADER_AGENTS_LLM_BASE_URL", "").strip()
        if not base_url:
            raise LlmConfigurationError("TRADER_AGENTS_LLM_BASE_URL is required for openai_compatible")
        config = LlmConfiguration(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=source.get("TRADER_AGENTS_LLM_API_KEY", "").strip(),
            timeout_seconds=timeout,
        )
        return OpenAICompatibleJsonLlmClient(config=config, transport=selected_transport)

    raise LlmConfigurationError(f"Unsupported TRADER_AGENTS_LLM_PROVIDER: {provider}")


def _normalized_provider(value: str) -> str:
    """Normalize provider aliases used in local environment files."""
    provider = value.strip().lower().replace("-", "_")
    if provider in {"openai", "openai_compatible", "openai_compat", "compatible"}:
        return "openai_compatible"
    return provider


def _parse_timeout(value: str) -> float:
    """Parse a positive timeout value."""
    try:
        timeout = float(value)
    except ValueError as exc:
        raise LlmConfigurationError("TRADER_AGENTS_LLM_TIMEOUT_SECONDS must be numeric") from exc
    if timeout <= 0:
        raise LlmConfigurationError("TRADER_AGENTS_LLM_TIMEOUT_SECONDS must be positive")
    return timeout


def _join_url(base_url: str, path: str) -> str:
    """Join a base URL and relative path without double slashes."""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _decode_json_content(content: object) -> Mapping[str, Any]:
    """Decode provider message content into a JSON object."""
    if isinstance(content, Mapping):
        return dict(content)
    if not isinstance(content, str):
        raise LlmRequestError("LLM message content was not text or an object")
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LlmRequestError("LLM message content was not valid JSON") from exc
    if not isinstance(decoded, Mapping):
        raise LlmRequestError("LLM message content JSON was not an object")
    return decoded
