from __future__ import annotations

from typing import Any, Mapping

import anyio
import pytest

from trader_agents.llm_client import (
    LlmConfigurationError,
    LlmJsonRequest,
    LlmMessage,
    RuntimeConfiguredLlmClient,
    StaticJsonLlmClient,
    build_llm_client_from_env,
)


class FakeTransport:
    """Capture deterministic provider requests for client boundary tests."""

    def __init__(
        self,
        response: Mapping[str, Any],
        *,
        get_response: Mapping[str, Any] | None = None,
    ) -> None:
        """Store POST and optional GET responses."""
        self.response = dict(response)
        self.get_response = dict(get_response or {})
        self.calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []

    async def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """Capture a GET request and return the configured response."""
        self.get_calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.get_response

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "url": url,
                "payload": dict(payload),
                "headers": dict(headers),
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


def _request() -> LlmJsonRequest:
    return LlmJsonRequest(
        messages=(LlmMessage(role="user", content="Return JSON."),),
        response_schema={"type": "object"},
    )


def test_build_llm_client_from_env_requires_provider() -> None:
    with pytest.raises(LlmConfigurationError, match="TRADER_AGENTS_LLM_PROVIDER"):
        build_llm_client_from_env({})


def test_runtime_configured_llm_client_respects_empty_environment() -> None:
    client = RuntimeConfiguredLlmClient(env={})

    async def _run() -> None:
        with pytest.raises(LlmConfigurationError, match="TRADER_AGENTS_LLM_PROVIDER"):
            await client.complete_json(_request())

    anyio.run(_run)


def test_build_llm_client_from_env_rejects_unsupported_provider() -> None:
    with pytest.raises(LlmConfigurationError, match="Unsupported"):
        build_llm_client_from_env(
            {
                "TRADER_AGENTS_LLM_PROVIDER": "unknown",
                "TRADER_AGENTS_LLM_MODEL": "model",
            }
        )


def test_static_json_llm_client_returns_configured_json_and_records_requests() -> None:
    client = StaticJsonLlmClient([{"action": "finish", "reason": "done"}])

    async def _run() -> None:
        output = await client.complete_json(_request())

        assert output == {"action": "finish", "reason": "done"}
        assert len(client.requests) == 1

    anyio.run(_run)


def test_openrouter_style_client_uses_openai_compatible_endpoint() -> None:
    transport = FakeTransport(
        {
            "choices": [
                {
                    "message": {
                        "content": '{"action": "finish", "reason": "complete"}',
                    }
                }
            ]
        }
    )
    client = build_llm_client_from_env(
        {
            "TRADER_AGENTS_LLM_PROVIDER": "openrouter",
            "TRADER_AGENTS_LLM_MODEL": "openrouter/model",
            "TRADER_AGENTS_LLM_API_KEY": "secret",
            "TRADER_AGENTS_LLM_TIMEOUT_SECONDS": "12",
        },
        transport=transport,
    )

    async def _run() -> None:
        output = await client.complete_json(_request())

        assert output == {"action": "finish", "reason": "complete"}
        assert (
            transport.calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
        )
        assert transport.calls[0]["headers"]["Authorization"] == "Bearer secret"
        assert transport.calls[0]["payload"]["model"] == "openrouter/model"
        assert transport.calls[0]["payload"]["response_format"] == {
            "type": "json_object"
        }
        assert transport.calls[0]["timeout_seconds"] == 12.0

    anyio.run(_run)


def test_ollama_client_uses_local_chat_endpoint() -> None:
    transport = FakeTransport(
        {
            "message": {
                "content": '{"action": "finish", "reason": "complete"}',
            }
        }
    )
    client = build_llm_client_from_env(
        {
            "TRADER_AGENTS_LLM_PROVIDER": "ollama",
            "TRADER_AGENTS_LLM_MODEL": "llama3.1",
            "TRADER_AGENTS_LLM_BASE_URL": "http://localhost:11434",
        },
        transport=transport,
    )

    async def _run() -> None:
        output = await client.complete_json(_request())

        assert output == {"action": "finish", "reason": "complete"}
        assert transport.calls[0]["url"] == "http://localhost:11434/api/chat"
        assert transport.calls[0]["payload"]["model"] == "llama3.1"
        assert transport.calls[0]["payload"]["format"] == {"type": "object"}
        assert transport.calls[0]["payload"]["think"] is False
        assert transport.calls[0]["payload"]["stream"] is False
        assert transport.calls[0]["payload"]["options"]["num_ctx"] == 8_192
        assert transport.calls[0]["payload"]["options"]["num_predict"] == 800

    anyio.run(_run)


def test_ollama_client_verifies_admitted_model_digest_before_chat() -> None:
    digest = "a" * 64
    transport = FakeTransport(
        {
            "message": {
                "content": '{"action": "finish", "reason": "complete"}',
            }
        },
        get_response={
            "models": [
                {
                    "name": "qwen3.5:9b",
                    "model": "qwen3.5:9b",
                    "digest": digest,
                }
            ]
        },
    )
    client = build_llm_client_from_env(
        {
            "TRADER_AGENTS_LLM_PROVIDER": "ollama",
            "TRADER_AGENTS_LLM_MODEL": "qwen3.5:9b",
            "TRADER_AGENTS_LLM_MODEL_REVISION": digest,
            "TRADER_AGENTS_LLM_BASE_URL": "http://localhost:11434",
        },
        transport=transport,
    )

    async def _run() -> None:
        output = await client.complete_json(_request())

        assert output == {"action": "finish", "reason": "complete"}
        assert transport.get_calls[0]["url"] == "http://localhost:11434/api/tags"
        assert len(transport.calls) == 1

    anyio.run(_run)


def test_ollama_client_rejects_model_digest_drift_before_chat() -> None:
    transport = FakeTransport(
        {
            "message": {
                "content": '{"action": "finish", "reason": "complete"}',
            }
        },
        get_response={
            "models": [
                {
                    "name": "qwen3.5:9b",
                    "digest": "b" * 64,
                }
            ]
        },
    )
    client = build_llm_client_from_env(
        {
            "TRADER_AGENTS_LLM_PROVIDER": "ollama",
            "TRADER_AGENTS_LLM_MODEL": "qwen3.5:9b",
            "TRADER_AGENTS_LLM_MODEL_REVISION": "a" * 64,
        },
        transport=transport,
    )

    async def _run() -> None:
        with pytest.raises(LlmConfigurationError, match="digest mismatch"):
            await client.complete_json(_request())

        assert transport.calls == []

    anyio.run(_run)
"""Unit tests for provider configuration and exact model identity checks."""
