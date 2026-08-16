"""Define manifests and closed vocabularies for generated method code.

Manifests pin method-card provenance, source identity, entrypoints, dependencies,
fixtures, and validation status. Parsing fails on unknown or incomplete shapes so
generated code cannot expand its declared execution surface implicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


MATH_REGISTER_METHOD_IMPLEMENTATION = "math_register_method_implementation"
MATH_RUN_INDICATOR_FIXTURES = "math_run_indicator_fixtures"
MATH_RUN_SIGNAL_FIXTURES = "math_run_signal_fixtures"
MATH_GENERATE_PYTHON_METHOD = "math_generate_python_method"

SCHEMA_VERSION = "1"
INDICATOR_RUNTIME_CONTRACT = "trader.indicators.Indicator"
SIGNAL_RUNTIME_CONTRACT = "trader.signals.Signal"
DEFAULT_ALLOWED_IMPORTS = (
    "__future__",
    "dataclasses",
    "datetime",
    "math",
    "statistics",
    "trader.indicators",
    "trader.signals",
    "trader_standard.indicators",
    "typing",
)
FORBIDDEN_CALLS = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
DEFAULT_ENTRYPOINTS = {
    "sma": "trader_standard.indicators:SmaIndicator",
    "ema": "trader_standard.indicators:EmaIndicator",
    "rsi": "trader_standard.indicators:RsiIndicator",
    "rolling_volatility": "trader_standard.indicators:RollingVolatilityIndicator",
    "z_score": "trader_standard.indicators:ZScoreIndicator",
    "bollinger_wma_band_rule": "trader_standard.indicators:BollingerBandsIndicator",
    "bollinger_bwma_action_signal": "trader_standard.signals:BollingerBwmaActionSignal",
}


@dataclass(frozen=True)
class MethodImplementationManifest:
    """Persisted registration record for a validated Python method implementation.

    The manifest links a registry method, approved method-card evidence, source
    path/hash, class entrypoint, constructor kwargs, runtime contract, dependency
    allowlist, and static safety profile. Fixture runners and reviewers use it to
    reload the exact implementation that was checked and to verify that generated
    code remains quarantined and evidence-backed.
    """

    implementation_id: str
    method_id: str
    language: str
    implementation_kind: str
    entrypoint: str
    class_name: str
    source_path: str
    source_hash: str
    source_provenance: Mapping[str, Any]
    constructor_kwargs: Mapping[str, Any]
    method_card_ids: tuple[str, ...]
    method_contract: Mapping[str, Any]
    runtime_contract: str = INDICATOR_RUNTIME_CONTRACT
    dependency_allowlist: tuple[str, ...] = DEFAULT_ALLOWED_IMPORTS
    safety_profile: Mapping[str, Any] = field(default_factory=lambda: {
        "no_network": True,
        "no_filesystem_mutation": True,
        "no_sql": True,
        "no_broker_access": True,
        "no_process_execution": True,
    })
    status: str = "registered"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize implementation provenance, evidence, runtime, and safety metadata.

        Tuple and mapping fields are copied into JSON-compatible containers so
        registration, fixture validation, and review tooling all consume the same
        normalized manifest payload.
        """
        return {
            "artifact_type": "method_implementation_manifest",
            "schema_version": self.schema_version,
            "implementation_id": self.implementation_id,
            "method_id": self.method_id,
            "language": self.language,
            "implementation_kind": self.implementation_kind,
            "entrypoint": self.entrypoint,
            "class_name": self.class_name,
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "source_provenance": dict(self.source_provenance),
            "constructor_kwargs": dict(self.constructor_kwargs),
            "method_card_ids": list(self.method_card_ids),
            "method_contract": dict(self.method_contract),
            "runtime_contract": self.runtime_contract,
            "dependency_allowlist": list(self.dependency_allowlist),
            "safety_profile": dict(self.safety_profile),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodImplementationManifest":
        """Parse a manifest payload while defaulting legacy runtime and allowlist fields.

        The parser normalizes mappings, sequences, timestamps, status, schema
        version, and dependency allowlists before returning the typed manifest used
        by registration and fixture runners.
        """
        return cls(
            implementation_id=str(payload.get("implementation_id") or ""),
            method_id=str(payload.get("method_id") or ""),
            language=str(payload.get("language") or "python"),
            implementation_kind=str(payload.get("implementation_kind") or "maintained"),
            entrypoint=str(payload.get("entrypoint") or ""),
            class_name=str(payload.get("class_name") or ""),
            source_path=str(payload.get("source_path") or ""),
            source_hash=str(payload.get("source_hash") or ""),
            source_provenance=mapping(payload.get("source_provenance")),
            constructor_kwargs=mapping(payload.get("constructor_kwargs")),
            method_card_ids=tuple(str(item) for item in sequence(payload.get("method_card_ids"))),
            method_contract=mapping(payload.get("method_contract")),
            runtime_contract=str(payload.get("runtime_contract") or INDICATOR_RUNTIME_CONTRACT),
            dependency_allowlist=tuple(str(item) for item in sequence(payload.get("dependency_allowlist")))
            or DEFAULT_ALLOWED_IMPORTS,
            safety_profile=mapping(payload.get("safety_profile")),
            status=str(payload.get("status") or "registered"),
            created_at=parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
        )


def mapping(value: Any) -> Mapping[str, Any]:
    """Return a mapping value or an empty mapping for malformed JSON fields.

    Manifest parsing accepts artifacts produced by external tools, so optional
    mapping fields are normalized defensively instead of letting `dict()` coerce
    surprising values. Required semantic validation happens in registration and
    fixture runners.
    """
    return value if isinstance(value, Mapping) else {}


def sequence(value: Any) -> Sequence[Any]:
    """Normalize optional manifest list fields to a sequence for parsing.

    `None` becomes empty, strings are treated as a single value rather than a
    character sequence, and existing sequences pass through. This keeps manifest
    deserialization predictable for method-card IDs, dependency allowlists, and
    evidence reference payloads.
    """
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return value
    return (value,)


def parse_datetime(value: Any) -> datetime:
    """Parse stored manifest timestamps while tolerating missing legacy values.

    Existing `datetime` values pass through, ISO-8601 strings including `Z` suffixes
    are parsed, and missing values fall back to the current UTC time so older
    artifacts without `created_at` can still be loaded and revalidated.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)
