"""Unit contracts for runtime-configured knowledge embedding adapters.

Subject: Embedding configuration, request shaping, batching, response normalization, and safe summaries.
Level: In-process adapter contract.
Collaborators: Real adapter logic with mocked HTTP calls and fixed responses; no network service.
Guarantees: Configuration fails explicitly, API variants normalize, order is preserved, and secrets stay hidden.
Non-goals: Embedding quality, provider availability, vector persistence, retrieval ranking, or model evaluation.
"""

from __future__ import annotations

from typing import Any, Mapping
from unittest.mock import patch
from urllib import request

import pytest

from trader_research.knowledge import embeddings
from trader_research.knowledge.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingRequestError,
    build_embedding_provider_from_env,
    embedding_runtime_summary,
)


def test_embedding_backend_timeout_is_normalized() -> None:
    """A low-level request timeout becomes the stable embedding request error contract."""
    with patch.object(request, "urlopen", side_effect=TimeoutError):
        with pytest.raises(EmbeddingRequestError, match="timed out after 12 seconds"):
            embeddings._post_json(
                "http://localhost:11434/v1/embeddings",
                {"model": "model", "input": "text"},
                headers={"Content-Type": "application/json"},
                timeout_seconds=12,
            )


def test_build_embedding_provider_from_env_requires_real_runtime_config() -> None:
    """Provider construction rejects missing provider, model, and compatible-endpoint configuration explicitly."""
    with pytest.raises(
        EmbeddingConfigurationError, match="TRADER_RESEARCH_EMBEDDINGS_PROVIDER"
    ):
        build_embedding_provider_from_env({})

    with pytest.raises(
        EmbeddingConfigurationError, match="TRADER_RESEARCH_EMBEDDINGS_MODEL"
    ):
        build_embedding_provider_from_env(
            {"TRADER_RESEARCH_EMBEDDINGS_PROVIDER": "openai"}
        )

    with pytest.raises(
        EmbeddingConfigurationError, match="TRADER_RESEARCH_EMBEDDINGS_BASE_URL"
    ):
        build_embedding_provider_from_env(
            {
                "TRADER_RESEARCH_EMBEDDINGS_PROVIDER": "openai_compatible",
                "TRADER_RESEARCH_EMBEDDINGS_MODEL": "embedding-model",
            }
        )


def test_openai_embedding_provider_uses_embeddings_endpoint() -> None:
    """The OpenAI adapter sends the configured model, input, credentials, and timeout to embeddings."""
    calls: list[dict[str, Any]] = []

    def _fake_post_json(
        url: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        calls.append(
            {
                "url": url,
                "payload": dict(payload),
                "headers": dict(headers),
                "timeout_seconds": timeout_seconds,
            }
        )
        return {"data": [{"embedding": [0.25, -0.5, 0.75]}]}

    provider = build_embedding_provider_from_env(
        {
            "TRADER_RESEARCH_EMBEDDINGS_PROVIDER": "openai",
            "TRADER_RESEARCH_EMBEDDINGS_MODEL": "text-embedding-3-small",
            "TRADER_RESEARCH_EMBEDDINGS_API_KEY": "secret",
            "TRADER_RESEARCH_EMBEDDINGS_TIMEOUT_SECONDS": "11",
        }
    )
    with patch("trader_research.knowledge.embeddings._post_json", _fake_post_json):
        vector = provider.embed("rank information coefficient")

    assert vector == (0.25, -0.5, 0.75)
    assert calls[0]["url"] == "https://api.openai.com/v1/embeddings"
    assert calls[0]["payload"] == {
        "model": "text-embedding-3-small",
        "input": "rank information coefficient",
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer secret"
    assert calls[0]["timeout_seconds"] == 11.0


def test_openai_embedding_provider_batches_and_restores_response_order() -> None:
    """Batched compatible responses are reordered by provider indices to match input order."""
    provider = build_embedding_provider_from_env(
        {
            "TRADER_RESEARCH_EMBEDDINGS_PROVIDER": "openai_compatible",
            "TRADER_RESEARCH_EMBEDDINGS_MODEL": "embedding-model",
            "TRADER_RESEARCH_EMBEDDINGS_BASE_URL": "http://localhost:9999/v1",
        }
    )
    response = {
        "data": [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ]
    }
    with patch(
        "trader_research.knowledge.embeddings._post_json", return_value=response
    ) as post:
        vectors = provider.embed_many(["first", "second"])

    assert vectors == ((1.0, 0.0), (0.0, 1.0))
    assert post.call_args.args[1] == {
        "model": "embedding-model",
        "input": ["first", "second"],
    }


def test_embedding_runtime_summary_omits_secrets() -> None:
    """Runtime summaries expose capability configuration without returning the configured API secret."""
    summary = embedding_runtime_summary(
        {
            "TRADER_RESEARCH_EMBEDDINGS_PROVIDER": "openai",
            "TRADER_RESEARCH_EMBEDDINGS_MODEL": "text-embedding-3-small",
            "TRADER_RESEARCH_EMBEDDINGS_API_KEY": "secret",
            "TRADER_RESEARCH_EMBEDDINGS_TIMEOUT_SECONDS": "30",
        }
    )

    assert summary == {
        "configured": True,
        "provider": "openai",
        "model": "text-embedding-3-small",
        "base_url": "https://api.openai.com/v1",
        "api_key_configured": True,
        "timeout_seconds": 30.0,
    }


def test_embedding_response_must_include_numeric_vector() -> None:
    """An empty or nonnumeric provider vector is rejected before entering retrieval state."""
    provider = build_embedding_provider_from_env(
        {
            "TRADER_RESEARCH_EMBEDDINGS_PROVIDER": "openai_compatible",
            "TRADER_RESEARCH_EMBEDDINGS_MODEL": "model",
            "TRADER_RESEARCH_EMBEDDINGS_BASE_URL": "http://localhost:9999/v1",
        }
    )
    with patch(
        "trader_research.knowledge.embeddings._post_json",
        return_value={"data": [{"embedding": []}]},
    ):
        with pytest.raises(EmbeddingRequestError, match="embedding vector"):
            provider.embed("text")
