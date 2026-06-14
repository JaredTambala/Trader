"""Embedding providers for local knowledge indexing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
import os
import re
from typing import Any, Protocol
from urllib import error, request


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


class EmbeddingConfigurationError(RuntimeError):
    """Raised when no usable embedding runtime configuration is available."""


class EmbeddingRequestError(RuntimeError):
    """Raised when an embedding backend request fails or returns unusable data."""


class EmbeddingProvider(Protocol):
    """Minimal embedding provider protocol used by knowledge indexing."""

    provider: str
    model: str
    version: str

    def embed(self, text: str) -> tuple[float, ...]:
        """Return one embedding vector for text."""


class DeterministicEmbeddingProvider:
    """Hash-vector embedding provider for deterministic tests only."""

    provider = "local"
    model = "deterministic-hash-vector"
    version = "1"
    dimension = 32

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimension
        for token in TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:2], "big") % self.dimension
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return tuple(vector)
        return tuple(value / norm for value in vector)


@dataclass(frozen=True)
class EmbeddingConfiguration:
    """Runtime embedding backend configuration."""

    provider: str
    model: str
    base_url: str
    api_key: str = ""
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class OpenAICompatibleEmbeddingProvider:
    """Embedding provider for OpenAI-compatible `/embeddings` APIs."""

    config: EmbeddingConfiguration
    version: str = "runtime"

    @property
    def provider(self) -> str:
        return self.config.provider

    @property
    def model(self) -> str:
        return self.config.model

    def embed(self, text: str) -> tuple[float, ...]:
        payload = {"model": self.config.model, "input": text}
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        response = _post_json(
            _join_url(self.config.base_url, "embeddings"),
            payload,
            headers=headers,
            timeout_seconds=self.config.timeout_seconds,
        )
        return _embedding_from_openai_compatible_response(response)


@dataclass(frozen=True)
class RuntimeConfiguredEmbeddingProvider:
    """Embedding provider that resolves backend configuration at call time."""

    env: Mapping[str, str] | None = None

    @property
    def provider(self) -> str:
        source = self.env if self.env is not None else os.environ
        return _normalized_provider(source.get("TRADER_RESEARCH_EMBEDDINGS_PROVIDER", "")) or "runtime"

    @property
    def model(self) -> str:
        source = self.env if self.env is not None else os.environ
        return source.get("TRADER_RESEARCH_EMBEDDINGS_MODEL", "").strip() or "runtime"

    @property
    def version(self) -> str:
        return "runtime"

    def embed(self, text: str) -> tuple[float, ...]:
        provider = build_embedding_provider_from_env(self.env if self.env is not None else os.environ)
        return provider.embed(text)


def build_embedding_provider_from_env(env: Mapping[str, str] | None = None) -> EmbeddingProvider:
    """Build an embedding provider from `TRADER_RESEARCH_EMBEDDINGS_*` values."""
    source = env if env is not None else os.environ
    provider = _normalized_provider(source.get("TRADER_RESEARCH_EMBEDDINGS_PROVIDER", ""))
    if not provider:
        raise EmbeddingConfigurationError("TRADER_RESEARCH_EMBEDDINGS_PROVIDER is required")
    model = source.get("TRADER_RESEARCH_EMBEDDINGS_MODEL", "").strip()
    if not model:
        raise EmbeddingConfigurationError("TRADER_RESEARCH_EMBEDDINGS_MODEL is required")
    timeout = _parse_timeout(source.get("TRADER_RESEARCH_EMBEDDINGS_TIMEOUT_SECONDS", "30"))
    if provider == "openai":
        api_key = source.get("TRADER_RESEARCH_EMBEDDINGS_API_KEY", "").strip()
        if not api_key:
            raise EmbeddingConfigurationError("TRADER_RESEARCH_EMBEDDINGS_API_KEY is required for openai")
        return OpenAICompatibleEmbeddingProvider(
            EmbeddingConfiguration(
                provider=provider,
                model=model,
                base_url=source.get("TRADER_RESEARCH_EMBEDDINGS_BASE_URL", "https://api.openai.com/v1").strip()
                or "https://api.openai.com/v1",
                api_key=api_key,
                timeout_seconds=timeout,
            )
        )
    if provider == "openai_compatible":
        base_url = source.get("TRADER_RESEARCH_EMBEDDINGS_BASE_URL", "").strip()
        if not base_url:
            raise EmbeddingConfigurationError(
                "TRADER_RESEARCH_EMBEDDINGS_BASE_URL is required for openai_compatible"
            )
        return OpenAICompatibleEmbeddingProvider(
            EmbeddingConfiguration(
                provider=provider,
                model=model,
                base_url=base_url,
                api_key=source.get("TRADER_RESEARCH_EMBEDDINGS_API_KEY", "").strip(),
                timeout_seconds=timeout,
            )
        )
    raise EmbeddingConfigurationError(f"Unsupported TRADER_RESEARCH_EMBEDDINGS_PROVIDER: {provider}")


def embedding_runtime_summary(env: Mapping[str, str]) -> dict[str, Any]:
    """Return non-secret embedding runtime config metadata."""
    provider = _normalized_provider(env.get("TRADER_RESEARCH_EMBEDDINGS_PROVIDER", ""))
    model = env.get("TRADER_RESEARCH_EMBEDDINGS_MODEL", "").strip()
    base_url = env.get("TRADER_RESEARCH_EMBEDDINGS_BASE_URL", "").strip()
    return {
        "configured": bool(provider and model),
        "provider": provider or None,
        "model": model or None,
        "base_url": base_url or ("https://api.openai.com/v1" if provider == "openai" else None),
        "api_key_configured": bool(env.get("TRADER_RESEARCH_EMBEDDINGS_API_KEY", "").strip()),
        "timeout_seconds": _parse_timeout(env.get("TRADER_RESEARCH_EMBEDDINGS_TIMEOUT_SECONDS", "30")),
    }


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(sum(a * b for a, b in zip(left, right, strict=True)))


def _post_json(
    url: str,
    payload: Mapping[str, Any],
    *,
    headers: Mapping[str, str],
    timeout_seconds: float,
) -> Mapping[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(url=url, data=body, headers=dict(headers), method="POST")
    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise EmbeddingRequestError(f"Embedding backend returned HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise EmbeddingRequestError(f"Embedding backend request failed: {exc.reason}") from exc
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EmbeddingRequestError("Embedding backend did not return valid JSON") from exc
    if not isinstance(decoded, Mapping):
        raise EmbeddingRequestError("Embedding backend returned a non-object JSON payload")
    return decoded


def _embedding_from_openai_compatible_response(response: Mapping[str, Any]) -> tuple[float, ...]:
    data = response.get("data")
    if not isinstance(data, list) or not data:
        raise EmbeddingRequestError("Embedding response did not include data")
    first = data[0]
    if not isinstance(first, Mapping):
        raise EmbeddingRequestError("Embedding response data item was not an object")
    embedding = first.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise EmbeddingRequestError("Embedding response did not include an embedding vector")
    try:
        return tuple(float(value) for value in embedding)
    except (TypeError, ValueError) as exc:
        raise EmbeddingRequestError("Embedding vector contained non-numeric values") from exc


def _join_url(base_url: str, suffix: str) -> str:
    return f"{base_url.rstrip('/')}/{suffix.lstrip('/')}"


def _normalized_provider(value: str) -> str:
    provider = value.strip().lower().replace("-", "_")
    if provider in {"openai", "openai_compatible", "openai_compat", "compatible"}:
        return "openai" if provider == "openai" else "openai_compatible"
    return provider


def _parse_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as exc:
        raise EmbeddingConfigurationError("TRADER_RESEARCH_EMBEDDINGS_TIMEOUT_SECONDS must be numeric") from exc
    if timeout <= 0:
        raise EmbeddingConfigurationError("TRADER_RESEARCH_EMBEDDINGS_TIMEOUT_SECONDS must be positive")
    return timeout
