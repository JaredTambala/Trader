"""Dependency-light canonical identity for qualified market-data replay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


REPLAY_DATA_IDENTITY_ALGORITHM = "sha256:bar-content-v1"


@dataclass(frozen=True)
class ReplayDataSourceSemantics:
    """Source and scope terms used to qualify one replay dataset."""

    provider: str | None
    source_policy: str
    observed_sources: tuple[str, ...]
    asset_class: str
    symbols: tuple[str, ...]
    timeframe: str
    bar_type: str

    def to_dict(self) -> dict[str, object]:
        """Return canonical JSON-compatible source semantics."""
        return {
            "provider": self.provider,
            "source_policy": self.source_policy,
            "observed_sources": list(self.observed_sources),
            "asset_class": self.asset_class,
            "symbols": list(self.symbols),
            "timeframe": self.timeframe,
            "bar_type": self.bar_type,
        }


@dataclass(frozen=True)
class ReplayDataIdentity:
    """Digest and evidence metadata for the exact bars a replay may consume."""

    algorithm: str
    content_digest: str
    row_count: int
    source_semantics: ReplayDataSourceSemantics
    inspected_at: datetime

    def to_dict(self) -> dict[str, object]:
        """Return the persisted identity payload."""
        return {
            "algorithm": self.algorithm,
            "content_digest": self.content_digest,
            "row_count": self.row_count,
            "source_semantics": self.source_semantics.to_dict(),
            "inspected_at": self.inspected_at.isoformat(),
        }


class ReplayDataIdentityMismatch(ValueError):
    """Raised when current replay rows cannot prove the qualified identity."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def build_replay_data_identity(
    records: Sequence[Any],
    *,
    provider: str | None,
    source_policy: str | None,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    bar_type: str = "trade_bar",
    inspected_at: datetime | None = None,
) -> ReplayDataIdentity:
    """Build a deterministic identity for the exact rows available to replay."""
    normalized_symbols = tuple(sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}))
    normalized_sources = tuple(sorted({str(record.source or "unknown").strip() or "unknown" for record in records}))
    semantics = ReplayDataSourceSemantics(
        provider=_optional_text(provider),
        source_policy=str(source_policy or "observed").strip() or "observed",
        observed_sources=normalized_sources,
        asset_class=str(asset_class).strip().lower(),
        symbols=normalized_symbols,
        timeframe=str(timeframe).strip(),
        bar_type=str(bar_type).strip() or "trade_bar",
    )
    digest = hashlib.sha256()
    _digest_update(digest, {"algorithm": REPLAY_DATA_IDENTITY_ALGORITHM, "source_semantics": semantics.to_dict()})
    canonical_records = sorted(
        records,
        key=lambda record: (
            str(record.symbol).strip().upper(),
            _utc(record.ts).isoformat(),
            str(record.source or "unknown"),
            str(record.timeframe).strip(),
        ),
    )
    for record in canonical_records:
        _digest_update(digest, _canonical_record(record))
    return ReplayDataIdentity(
        algorithm=REPLAY_DATA_IDENTITY_ALGORITHM,
        content_digest=f"sha256:{digest.hexdigest()}",
        row_count=len(canonical_records),
        source_semantics=semantics,
        inspected_at=_utc(inspected_at or datetime.now(timezone.utc)),
    )


def validate_replay_data_identity(
    expected: Mapping[str, Any],
    records: Sequence[Any],
    *,
    provider: str | None,
    source_policy: str | None,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    bar_type: str = "trade_bar",
    inspected_at: datetime | None = None,
) -> ReplayDataIdentity:
    """Recompute and require a qualified replay identity before execution."""
    actual = build_replay_data_identity(
        records,
        provider=provider,
        source_policy=source_policy,
        asset_class=asset_class,
        symbols=symbols,
        timeframe=timeframe,
        bar_type=bar_type,
        inspected_at=inspected_at,
    )
    if str(expected.get("algorithm") or "") != REPLAY_DATA_IDENTITY_ALGORITHM:
        raise ReplayDataIdentityMismatch("identity_algorithm_mismatch", "qualified replay identity algorithm is unsupported")
    expected_semantics = expected.get("source_semantics")
    if not isinstance(expected_semantics, Mapping):
        raise ReplayDataIdentityMismatch("identity_missing_source_semantics", "qualified replay identity has no source semantics")
    expected_sources = tuple(sorted(str(item).strip() or "unknown" for item in expected_semantics.get("observed_sources", ())))
    actual_sources = actual.source_semantics.observed_sources
    if expected_sources != actual_sources:
        raise ReplayDataIdentityMismatch(
            "source_semantics_mismatch",
            f"qualified replay sources {expected_sources!r} do not match current sources {actual_sources!r}",
        )
    expected_digest = str(expected.get("content_digest") or "")
    if expected_digest != actual.content_digest:
        raise ReplayDataIdentityMismatch(
            "bar_content_mismatch",
            f"qualified replay digest {expected_digest!r} does not match current digest {actual.content_digest!r}",
        )
    expected_rows = expected.get("row_count")
    if isinstance(expected_rows, bool) or not isinstance(expected_rows, int) or expected_rows != actual.row_count:
        raise ReplayDataIdentityMismatch(
            "bar_content_mismatch",
            f"qualified replay row count {expected_rows!r} does not match current row count {actual.row_count}",
        )
    actual_semantics = actual.source_semantics.to_dict()
    for field in ("provider", "source_policy", "asset_class", "symbols", "timeframe", "bar_type"):
        expected_value = expected_semantics.get(field)
        actual_value = actual_semantics.get(field)
        if field == "symbols":
            expected_value = sorted(str(item).strip().upper() for item in expected_value or ())
        if expected_value != actual_value:
            raise ReplayDataIdentityMismatch(
                "source_semantics_mismatch",
                f"qualified replay source semantics field {field!r} does not match current evidence",
            )
    return actual


def _canonical_record(record: Any) -> dict[str, object]:
    """Return one BarRecord in the identity's canonical representation."""
    return {
        "symbol": str(record.symbol).strip().upper(),
        "timeframe": str(record.timeframe).strip(),
        "ts": _utc(record.ts).isoformat(),
        "open": _canonical_number(record.open),
        "high": _canonical_number(record.high),
        "low": _canonical_number(record.low),
        "close": _canonical_number(record.close),
        "volume": _canonical_number(record.volume),
        "vwap": _canonical_number(record.vwap),
        "trade_count": _canonical_number(record.trade_count),
        "source": str(record.source or "unknown").strip() or "unknown",
    }


def _digest_update(digest: Any, payload: Mapping[str, object]) -> None:
    """Append one canonical JSON line to a SHA-256 digest."""
    digest.update(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))
    digest.update(b"\n")


def _canonical_number(value: float | None) -> str | None:
    """Normalize a finite numeric value without platform-specific formatting."""
    if value is None:
        return None
    numeric = float(value)
    if numeric != numeric or numeric in {float("inf"), float("-inf")}:
        raise ValueError("replay identity bars must contain finite numeric values")
    return format(numeric, ".17g")


def _optional_text(value: object) -> str | None:
    """Normalize optional source metadata."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _utc(value: datetime) -> datetime:
    """Normalize an identity timestamp to an aware UTC value."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "REPLAY_DATA_IDENTITY_ALGORITHM",
    "ReplayDataIdentity",
    "ReplayDataIdentityMismatch",
    "ReplayDataSourceSemantics",
    "build_replay_data_identity",
    "validate_replay_data_identity",
]
