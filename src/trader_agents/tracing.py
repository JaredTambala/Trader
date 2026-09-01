"""Redacted trace correlation for model, MCP, checkpoint, and evidence events."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
import json
from typing import Any, Protocol


_FORBIDDEN_ATTRIBUTE_PARTS = (
    "prompt",
    "reasoning",
    "scratchpad",
    "credential",
    "secret",
    "api_key",
    "raw_message",
    "raw_tool",
    "source_code",
    "content",
)
_MAX_TRACE_ATTRIBUTE_BYTES = 16_000


@dataclass(frozen=True)
class TraceCorrelation:
    """Stable identities attached to public agent trace spans."""

    session_id: str
    branch_id: str
    program_id: str
    model_profile_id: str
    tool_catalog_id: str
    delegation_id: str | None = None
    attempt_id: str | None = None

    def attributes(self) -> dict[str, str]:
        """Return redacted correlation attributes."""
        attributes = {
            "trader.session_id": self.session_id,
            "trader.branch_id": self.branch_id,
            "trader.program_id": self.program_id,
            "trader.model_profile_id": self.model_profile_id,
            "trader.tool_catalog_id": self.tool_catalog_id,
        }
        if self.delegation_id:
            attributes["trader.delegation_id"] = self.delegation_id
        if self.attempt_id:
            attributes["trader.attempt_id"] = self.attempt_id
        return attributes


class TraceSink(Protocol):
    """Minimal synchronous context boundary for optional trace backends."""

    def span(
        self,
        name: str,
        *,
        span_type: str,
        attributes: Mapping[str, Any],
    ) -> Any:
        """Return a context manager for one redacted public span."""


@dataclass(frozen=True)
class NoOpTraceSink:
    """Trace sink used when observability is deliberately disabled."""

    @contextmanager
    def span(
        self,
        name: str,
        *,
        span_type: str,
        attributes: Mapping[str, Any],
    ) -> Iterator[None]:
        """Validate then discard one trace span."""
        _validate_span(name, span_type, attributes)
        yield


@dataclass
class RecordingTraceSink:
    """In-memory redacted trace sink for deterministic tests."""

    spans: list[dict[str, Any]] = field(default_factory=list)

    @contextmanager
    def span(
        self,
        name: str,
        *,
        span_type: str,
        attributes: Mapping[str, Any],
    ) -> Iterator[None]:
        """Record span start/completion without raw model or tool content."""
        _validate_span(name, span_type, attributes)
        record = {
            "name": name,
            "span_type": span_type,
            "attributes": dict(attributes),
            "status": "running",
        }
        self.spans.append(record)
        try:
            yield
        except Exception:
            record["status"] = "error"
            raise
        else:
            record["status"] = "completed"


@dataclass(frozen=True)
class MlflowTraceSink:
    """Lazy MLflow trace sink for an explicitly configured environment.

    Attributes:
        tracking_uri: Approved MLflow tracking URI.
        experiment_name: Trace experiment receiving agent spans.
    """

    tracking_uri: str
    experiment_name: str

    def __post_init__(self) -> None:
        """Require explicit non-empty observability configuration."""
        if not self.tracking_uri.strip():
            raise ValueError("MLflow tracking_uri is required")
        if not self.experiment_name.strip():
            raise ValueError("MLflow experiment_name is required")

    @contextmanager
    def span(
        self,
        name: str,
        *,
        span_type: str,
        attributes: Mapping[str, Any],
    ) -> Iterator[None]:
        """Emit one redacted MLflow span through a lazy optional import."""
        _validate_span(name, span_type, attributes)
        try:
            import mlflow
        except ImportError as exc:
            raise RuntimeError(
                "MLflow tracing requires the project ml optional dependency"
            ) from exc
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(self.experiment_name)
        with mlflow.start_span(
            name=name,
            span_type=span_type,
            attributes=dict(attributes),
        ):
            yield


def correlated_attributes(
    correlation: TraceCorrelation,
    **event_attributes: Any,
) -> dict[str, Any]:
    """Combine required identities with bounded public event metadata."""
    attributes: dict[str, Any] = correlation.attributes()
    attributes.update(event_attributes)
    _validate_attributes(attributes)
    return attributes


def _validate_span(
    name: str,
    span_type: str,
    attributes: Mapping[str, Any],
) -> None:
    """Reject invalid names and unsafe trace attributes."""
    if not name.strip() or len(name) > 200:
        raise ValueError("trace span name must contain 1 to 200 characters")
    if not span_type.strip() or len(span_type) > 100:
        raise ValueError("trace span_type must contain 1 to 100 characters")
    _validate_attributes(attributes)


def _validate_attributes(attributes: Mapping[str, Any]) -> None:
    """Reject secret/raw-content keys and unbounded or non-JSON values."""
    for key in attributes:
        normalized = str(key).lower()
        if any(part in normalized for part in _FORBIDDEN_ATTRIBUTE_PARTS):
            raise ValueError(f"trace attribute key is not allowed: {key}")
    try:
        encoded = json.dumps(
            dict(attributes),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("trace attributes must be JSON-native") from exc
    if len(encoded) > _MAX_TRACE_ATTRIBUTE_BYTES:
        raise ValueError("trace attributes exceed the 16000-byte limit")
