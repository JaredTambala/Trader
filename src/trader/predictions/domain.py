"""Dependency-neutral value objects for runtime model inference."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


DECISION_SCOPES = frozenset({"per_symbol", "universe_snapshot"})
PREDICTION_STATUSES = frozenset({"success", "stale", "timeout", "error", "skipped"})
FAILURE_ACTIONS = frozenset({"fail_closed", "skip_decision", "validated_fallback"})


@dataclass(frozen=True)
class FeatureColumn:
    """One ordered feature in a model input schema."""

    name: str
    dtype: str
    nullable: bool = False

    def __post_init__(self) -> None:
        """Reject incomplete schema entries."""
        if not self.name.strip() or not self.dtype.strip():
            raise ValueError("feature column name and dtype are required")

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON representation."""
        return {"name": self.name, "dtype": self.dtype, "nullable": self.nullable}


@dataclass(frozen=True)
class FeatureRow:
    """Point-in-time feature values for one optional instrument."""

    symbol: str | None
    as_of_ts: datetime
    availability_ts: datetime
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        """Normalize timestamps and require JSON-compatible values."""
        object.__setattr__(self, "symbol", _optional_symbol(self.symbol))
        object.__setattr__(self, "as_of_ts", _utc(self.as_of_ts))
        object.__setattr__(self, "availability_ts", _utc(self.availability_ts))
        _json_value(dict(self.values), "feature row values")

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON representation."""
        return {
            "symbol": self.symbol,
            "as_of_ts": self.as_of_ts.isoformat(),
            "availability_ts": self.availability_ts.isoformat(),
            "values": _jsonable(dict(self.values)),
        }


@dataclass(frozen=True)
class FeatureBatch:
    """Immutable, content-hashed input to one predictor invocation."""

    feature_set_id: str
    feature_set_digest: str
    decision_ts: datetime
    schema: tuple[FeatureColumn, ...]
    rows: tuple[FeatureRow, ...]
    input_hash: str
    missing_features: tuple[str, ...] = ()
    stale_features: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate schema, row shape, ordering, and the input digest."""
        if not self.feature_set_id.strip() or not self.feature_set_digest.strip():
            raise ValueError("feature set ID and digest are required")
        object.__setattr__(self, "decision_ts", _utc(self.decision_ts))
        if not self.schema:
            raise ValueError("feature batch schema cannot be empty")
        names = tuple(column.name for column in self.schema)
        if len(set(names)) != len(names):
            raise ValueError("feature batch schema names must be unique")
        for row in self.rows:
            if row.as_of_ts > self.decision_ts:
                raise ValueError("feature as_of_ts cannot be after decision_ts")
            if row.availability_ts > self.decision_ts:
                raise ValueError("feature availability_ts cannot be after decision_ts")
            unknown = set(row.values).difference(names)
            missing = set(names).difference(row.values)
            if unknown:
                raise ValueError(
                    f"feature row contains unknown columns: {sorted(unknown)}"
                )
            if missing:
                raise ValueError(f"feature row is missing columns: {sorted(missing)}")
            for column in self.schema:
                if row.values[column.name] is None and not column.nullable:
                    raise ValueError(f"feature {column.name} is not nullable")
        expected = _feature_batch_hash(self.identity_payload())
        if self.input_hash != expected:
            raise ValueError(
                "feature batch input_hash does not match canonical content"
            )

    @classmethod
    def build(
        cls,
        *,
        feature_set_id: str,
        feature_set_digest: str,
        decision_ts: datetime,
        schema: Sequence[FeatureColumn],
        rows: Sequence[FeatureRow],
        missing_features: Sequence[str] = (),
        stale_features: Sequence[str] = (),
    ) -> "FeatureBatch":
        """Build a validated batch and derive its deterministic input hash."""
        normalized_schema = tuple(schema)
        normalized_rows = tuple(rows)
        normalized_decision_ts = _utc(decision_ts)
        identity = {
            "feature_set_id": str(feature_set_id),
            "feature_set_digest": str(feature_set_digest),
            "decision_ts": normalized_decision_ts.isoformat(),
            "schema": [column.to_dict() for column in normalized_schema],
            "rows": [row.to_dict() for row in normalized_rows],
            "missing_features": sorted(set(str(item) for item in missing_features)),
            "stale_features": sorted(set(str(item) for item in stale_features)),
        }
        return cls(
            feature_set_id=str(feature_set_id),
            feature_set_digest=str(feature_set_digest),
            decision_ts=normalized_decision_ts,
            schema=normalized_schema,
            rows=normalized_rows,
            input_hash=_feature_batch_hash(identity),
            missing_features=tuple(identity["missing_features"]),
            stale_features=tuple(identity["stale_features"]),
        )

    @property
    def symbols(self) -> tuple[str, ...]:
        """Return symbols represented in row order."""
        return tuple(row.symbol for row in self.rows if row.symbol is not None)

    def identity_payload(self) -> dict[str, object]:
        """Return content covered by `input_hash`."""
        return {
            "feature_set_id": self.feature_set_id,
            "feature_set_digest": self.feature_set_digest,
            "decision_ts": self.decision_ts.isoformat(),
            "schema": [column.to_dict() for column in self.schema],
            "rows": [row.to_dict() for row in self.rows],
            "missing_features": list(self.missing_features),
            "stale_features": list(self.stale_features),
        }

    def to_dict(self, *, include_values: bool = True) -> dict[str, object]:
        """Return a stable payload, optionally omitting raw feature values."""
        payload = self.identity_payload()
        payload["input_hash"] = self.input_hash
        if not include_values:
            payload["rows"] = [
                {
                    "symbol": row.symbol,
                    "as_of_ts": row.as_of_ts.isoformat(),
                    "availability_ts": row.availability_ts.isoformat(),
                }
                for row in self.rows
            ]
        return payload


@dataclass(frozen=True)
class InferenceAdapterProfile:
    """Credential-free identity and runtime capabilities of an inference adapter.

    Attributes:
        profile_name: Stable configuration name used to select the adapter.
        provider: Provider or adapter family, such as ``mlflow``.
        adapter_version: Adapter and provider implementation identity.
        configuration_digest: Non-secret digest of material adapter configuration.
        capabilities: Declared bounded capabilities supported by the adapter.
        available: Whether required runtime dependencies are currently available.
        reason: Actionable explanation when the adapter is unavailable.
    """

    profile_name: str
    provider: str
    adapter_version: str
    configuration_digest: str
    capabilities: tuple[str, ...]
    available: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        """Require a complete immutable adapter identity."""
        for name in (
            "profile_name",
            "provider",
            "adapter_version",
            "configuration_digest",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"inference adapter {name} is required")

    def to_dict(self) -> dict[str, object]:
        """Return the stable non-secret adapter profile payload."""
        return {
            "profile_name": self.profile_name,
            "provider": self.provider,
            "adapter_version": self.adapter_version,
            "configuration_digest": self.configuration_digest,
            "capabilities": list(self.capabilities),
            "available": self.available,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ModelIdentity:
    """Immutable identity of the model used for one prediction."""

    registered_model_name: str
    model_version: str
    model_version_id: str
    model_digest: str
    signature_digest: str
    source_run_id: str
    adapter_profile: str
    adapter_version: str

    def __post_init__(self) -> None:
        """Require every immutable identity field."""
        for name, value in self.to_dict().items():
            if not str(value).strip():
                raise ValueError(f"model identity {name} is required")

    def to_dict(self) -> dict[str, str]:
        """Return the stable JSON representation."""
        return {
            "registered_model_name": self.registered_model_name,
            "model_version": self.model_version,
            "model_version_id": self.model_version_id,
            "model_digest": self.model_digest,
            "signature_digest": self.signature_digest,
            "source_run_id": self.source_run_id,
            "adapter_profile": self.adapter_profile,
            "adapter_version": self.adapter_version,
        }


@dataclass(frozen=True)
class PredictionRequest:
    """Closed request passed to a provider-neutral predictor."""

    run_id: str
    cycle_id: str
    feature_batch: FeatureBatch
    requested_outputs: tuple[str, ...]
    timeout_ms: int

    def __post_init__(self) -> None:
        """Reject incomplete or unbounded requests."""
        if not self.run_id.strip() or not self.cycle_id.strip():
            raise ValueError("prediction run_id and cycle_id are required")
        if not self.requested_outputs or any(
            not item.strip() for item in self.requested_outputs
        ):
            raise ValueError("at least one requested prediction output is required")
        if len(set(self.requested_outputs)) != len(self.requested_outputs):
            raise ValueError("requested prediction outputs must be unique")
        if isinstance(self.timeout_ms, bool) or not 1 <= self.timeout_ms <= 300_000:
            raise ValueError("prediction timeout_ms must be between 1 and 300000")


@dataclass(frozen=True)
class PredictionObservation:
    """One typed model output for an optional instrument."""

    output_name: str
    semantics: str
    value: object
    horizon: str
    symbol: str | None = None
    units: str | None = None
    uncertainty: object | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the output without imposing a closed methodology vocabulary."""
        if (
            not self.output_name.strip()
            or not self.semantics.strip()
            or not self.horizon.strip()
        ):
            raise ValueError(
                "prediction output_name, semantics, and horizon are required"
            )
        object.__setattr__(self, "symbol", _optional_symbol(self.symbol))
        _json_value(self.value, "prediction value")
        _json_value(self.uncertainty, "prediction uncertainty")
        _json_value(dict(self.metadata), "prediction metadata")

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON representation."""
        return {
            "symbol": self.symbol,
            "output_name": self.output_name,
            "semantics": self.semantics,
            "value": _jsonable(self.value),
            "horizon": self.horizon,
            "units": self.units,
            "uncertainty": _jsonable(self.uncertainty),
            "metadata": _jsonable(dict(self.metadata)),
        }


@dataclass(frozen=True)
class PredictionBatch:
    """Complete result of one predictor invocation."""

    model_identity: ModelIdentity
    feature_batch_hash: str
    decision_ts: datetime
    observations: tuple[PredictionObservation, ...]
    status: str
    latency_ms: float
    coverage: Mapping[str, object] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:
        """Validate status, timing, and output uniqueness."""
        if self.status not in PREDICTION_STATUSES:
            raise ValueError(f"unsupported prediction status: {self.status}")
        if not self.feature_batch_hash.strip():
            raise ValueError("prediction feature_batch_hash is required")
        object.__setattr__(self, "decision_ts", _utc(self.decision_ts))
        if not math.isfinite(float(self.latency_ms)) or self.latency_ms < 0:
            raise ValueError("prediction latency_ms must be finite and non-negative")
        keys = [(item.symbol, item.output_name) for item in self.observations]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "prediction observations must be unique by symbol and output"
            )
        if self.status == "success" and not self.observations:
            raise ValueError("successful prediction batches require observations")
        if self.status != "success" and self.observations:
            raise ValueError(
                "non-success prediction batches cannot contain observations"
            )
        _json_value(dict(self.coverage), "prediction coverage")

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON representation."""
        return {
            "model_identity": self.model_identity.to_dict(),
            "feature_batch_hash": self.feature_batch_hash,
            "decision_ts": self.decision_ts.isoformat(),
            "observations": [item.to_dict() for item in self.observations],
            "status": self.status,
            "latency_ms": float(self.latency_ms),
            "coverage": _jsonable(dict(self.coverage)),
            "warnings": list(self.warnings),
            "error": self.error,
        }


@dataclass(frozen=True)
class InferencePolicy:
    """Explicit timeout, freshness, and failure behavior for inference."""

    timeout_ms: int = 1_000
    failure_action: str = "fail_closed"
    max_feature_age_seconds: float | None = None
    require_complete_universe: bool = True
    fallback_ref: str | None = None

    def __post_init__(self) -> None:
        """Reject unsafe or incomplete policy combinations."""
        if isinstance(self.timeout_ms, bool) or not 1 <= self.timeout_ms <= 300_000:
            raise ValueError("inference timeout_ms must be between 1 and 300000")
        if self.failure_action not in FAILURE_ACTIONS:
            raise ValueError(
                f"unsupported inference failure_action: {self.failure_action}"
            )
        if self.max_feature_age_seconds is not None:
            if (
                not math.isfinite(float(self.max_feature_age_seconds))
                or self.max_feature_age_seconds < 0
            ):
                raise ValueError(
                    "max_feature_age_seconds must be finite and non-negative"
                )
        if (
            self.failure_action == "validated_fallback"
            and not str(self.fallback_ref or "").strip()
        ):
            raise ValueError("validated_fallback requires fallback_ref")
        if (
            self.failure_action != "validated_fallback"
            and self.fallback_ref is not None
        ):
            raise ValueError("fallback_ref is only valid for validated_fallback")

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON representation."""
        return {
            "timeout_ms": self.timeout_ms,
            "failure_action": self.failure_action,
            "max_feature_age_seconds": self.max_feature_age_seconds,
            "require_complete_universe": self.require_complete_universe,
            "fallback_ref": self.fallback_ref,
        }


@dataclass(frozen=True)
class StrategyPrediction:
    """Strategy-facing interpretation of one or more raw predictions."""

    name: str
    value: object
    symbol: str | None
    source_output_names: tuple[str, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate mapped decision input content."""
        if not self.name.strip() or not self.source_output_names:
            raise ValueError("strategy prediction name and source outputs are required")
        object.__setattr__(self, "symbol", _optional_symbol(self.symbol))
        _json_value(self.value, "strategy prediction value")
        _json_value(dict(self.metadata), "strategy prediction metadata")


def canonical_json_hash(value: object) -> str:
    """Return a deterministic SHA-256 digest for JSON-compatible content."""
    return hashlib.sha256(
        json.dumps(
            _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _feature_batch_hash(value: object) -> str:
    return f"sha256:{canonical_json_hash(value)}"


def _optional_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("timestamp values must be datetime instances")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_value(value: object, label: str) -> None:
    try:
        json.dumps(
            _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite JSON-compatible content") from exc


def _jsonable(value: object) -> Any:
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, MappingABC):
        return {str(key): _jsonable(inner) for key, inner in value.items()}
    if isinstance(value, SequenceABC) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numeric values are not JSON-compatible")
    return value
