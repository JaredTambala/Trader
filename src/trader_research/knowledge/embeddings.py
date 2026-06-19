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
    """Raised when environment-backed embedding settings cannot build a usable provider instance."""


class EmbeddingRequestError(RuntimeError):
    """Raised when an embedding backend request fails or returns unusable response data."""


class EmbeddingProvider(Protocol):
    """Small interface required by indexing and retrieval code for embeddings.

    Providers expose stable metadata used in embedding manifests and implement a
    single-text `embed` call that returns a numeric vector. Keeping the protocol
    narrow lets tests inject deterministic providers while production code can
    resolve OpenAI-compatible backends from runtime configuration.
    """

    provider: str
    model: str
    version: str

    def embed(self, text: str) -> tuple[float, ...]:
        """Return one numeric embedding vector for the supplied text payload and backend."""


class DeterministicEmbeddingProvider:
    """Local hash-vector provider used when tests need stable embeddings.

    The provider tokenizes text, hashes tokens into signed buckets, and normalizes
    the vector so lexical overlap produces repeatable similarity scores without
    network access or credentials. It is intentionally low fidelity and should be
    treated as a deterministic fake rather than a production semantic embedding.
    """

    provider = "local"
    model = "deterministic-hash-vector"
    version = "1"
    dimension = 32

    def embed(self, text: str) -> tuple[float, ...]:
        """Embed text with deterministic token hashing and L2 normalization.

        Tokens are lowercased, hashed into signed vector buckets, and normalized so
        repeated inputs produce identical vectors without network access.
        """
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
    """Secret-bearing runtime settings for one OpenAI-compatible embedding backend.

    The config keeps provider/model/base URL together with an optional bearer token
    and request timeout. It is passed directly to the HTTP provider and should not
    be serialized into manifests or logs because `api_key` may contain credentials.
    """

    provider: str
    model: str
    base_url: str
    api_key: str = ""
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class OpenAICompatibleEmbeddingProvider:
    """HTTP embedding provider for OpenAI-compatible `/embeddings` endpoints.

    Calls serialize the configured model and input text, attach a bearer token only
    when one is configured, validate that the response is an object, and extract
    the first numeric embedding vector. Backend transport, JSON, and shape
    failures are translated into `EmbeddingRequestError` for callers to surface.
    """

    config: EmbeddingConfiguration
    version: str = "runtime"

    @property
    def provider(self) -> str:
        """Return the configured provider name recorded in embedding manifests and search queries."""
        return self.config.provider

    @property
    def model(self) -> str:
        """Return the configured model name recorded in embedding manifests and search queries."""
        return self.config.model

    def embed(self, text: str) -> tuple[float, ...]:
        """Call the configured OpenAI-compatible endpoint and parse the first vector.

        The request includes bearer authorization only when an API key is present,
        and response transport, JSON, or shape failures are translated into
        `EmbeddingRequestError`.
        """
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
    """Lazy provider that reads embedding backend settings for each embed call.

    This wrapper lets long-lived services expose provider/model metadata from an
    injected environment mapping while deferring validation until an embedding is
    actually requested. It is useful for MCP tools that should start without
    credentials but fail clearly when indexing or retrieval needs runtime vectors.
    """

    env: Mapping[str, str] | None = None

    @property
    def provider(self) -> str:
        """Resolve the provider name from the injected environment or process environment mapping."""
        source = self.env if self.env is not None else os.environ
        return _normalized_provider(source.get("TRADER_RESEARCH_EMBEDDINGS_PROVIDER", "")) or "runtime"

    @property
    def model(self) -> str:
        """Resolve the model name from the injected environment or process environment mapping."""
        source = self.env if self.env is not None else os.environ
        return source.get("TRADER_RESEARCH_EMBEDDINGS_MODEL", "").strip() or "runtime"

    @property
    def version(self) -> str:
        """Return the runtime version marker used before concrete provider resolution occurs."""
        return "runtime"

    def embed(self, text: str) -> tuple[float, ...]:
        """Build the currently configured provider and delegate the embed request immediately."""
        provider = build_embedding_provider_from_env(self.env if self.env is not None else os.environ)
        return provider.embed(text)


def build_embedding_provider_from_env(env: Mapping[str, str] | None = None) -> EmbeddingProvider:
    """Build and validate the runtime embedding provider from environment values.

    The builder requires provider and model values, normalizes provider aliases,
    parses the request timeout, and enforces provider-specific requirements such
    as API keys for OpenAI or base URLs for compatible backends. Configuration
    problems are reported as `EmbeddingConfigurationError` before any network call
    is attempted.
    """
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
    """Return log- and envelope-safe metadata about embedding runtime settings.

    The summary reports whether provider/model/base URL are configured, which
    backend would be used, whether an API key is present, and the parsed timeout.
    It deliberately reports only the presence of the key, never the key value, so
    health checks can be observable without leaking credentials.
    """
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
    """Compute dot-product similarity for normalized vectors of equal length.

    Embedding providers are expected to return already normalized vectors when
    cosine semantics are required, so this helper only guards empty or
    mismatched-dimension inputs and otherwise returns the strict-pairwise dot
    product. Dimension mismatches return zero instead of raising because retrieval
    can continue with lexical evidence when vector evidence is unusable.
    """
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
