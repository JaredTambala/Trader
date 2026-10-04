"""Canonical comparison scope and variant metadata for backtest results."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from ..portfolio import Position
from ..signals import Bar
from .models import BacktestAssumptions


BENCHMARK_ID = "equal_weight_buy_and_hold"
BENCHMARK_METHOD = "buy_and_hold"
BENCHMARK_ALLOCATION = "equal_weight"


@dataclass(frozen=True)
class ReviewInitialPosition:
    """Initial position state included in a backtest comparison scope."""

    symbol: str
    qty: float
    avg_price: float | None


@dataclass(frozen=True)
class BacktestReviewScope:
    """Producer-owned fields that must match for cross-run comparison."""

    asset_class: str
    symbols: tuple[str, ...]
    timeframe: str
    replay_start: datetime
    replay_end: datetime
    data_scope_id: str
    benchmark_id: str
    benchmark_method: str
    benchmark_allocation: str
    initial_cash: float
    initial_positions: tuple[ReviewInitialPosition, ...]
    assumptions: BacktestAssumptions
    scope_fingerprint: str


@dataclass(frozen=True)
class BacktestVariant:
    """Intentional strategy or parameter variation within one scope."""

    strategy_id: str | None
    strategy_version: str | None
    parameters: Mapping[str, object]
    parameters_fingerprint: str
    variant_fingerprint: str


def build_backtest_review_scope(
    *,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    replay_start: datetime,
    replay_end: datetime,
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    initial_cash: float,
    initial_positions: Sequence[Position],
    assumptions: BacktestAssumptions,
) -> BacktestReviewScope:
    """Build a canonical scope and hash the actual replay inputs.

    The data identity includes every normalized bar loaded for the replay,
    including indicator lookback bars. Symbols and initial positions are sorted
    before hashing so equivalent input ordering produces the same fingerprint.
    """
    normalized_symbols = tuple(sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}))
    normalized_positions = tuple(
        ReviewInitialPosition(
            symbol=str(position.symbol).strip().upper(),
            qty=float(position.qty),
            avg_price=None if position.avg_price is None else float(position.avg_price),
        )
        for position in sorted(
            initial_positions,
            key=lambda item: (
                str(item.symbol).strip().upper(),
                float(item.qty),
                item.avg_price if item.avg_price is not None else float("-inf"),
            ),
        )
    )
    data_scope_id = build_data_scope_id(bars_by_symbol)
    scope_payload = {
        "asset_class": str(asset_class).strip().lower(),
        "symbols": normalized_symbols,
        "timeframe": str(timeframe).strip(),
        "replay_start": _utc(replay_start).isoformat(),
        "replay_end": _utc(replay_end).isoformat(),
        "data_scope_id": data_scope_id,
        "benchmark": {
            "id": BENCHMARK_ID,
            "method": BENCHMARK_METHOD,
            "allocation": BENCHMARK_ALLOCATION,
        },
        "initial_state": {
            "cash": float(initial_cash),
            "positions": normalized_positions,
        },
        "assumptions": assumptions,
    }
    return BacktestReviewScope(
        asset_class=scope_payload["asset_class"],
        symbols=normalized_symbols,
        timeframe=scope_payload["timeframe"],
        replay_start=_utc(replay_start),
        replay_end=_utc(replay_end),
        data_scope_id=data_scope_id,
        benchmark_id=BENCHMARK_ID,
        benchmark_method=BENCHMARK_METHOD,
        benchmark_allocation=BENCHMARK_ALLOCATION,
        initial_cash=float(initial_cash),
        initial_positions=normalized_positions,
        assumptions=assumptions,
        scope_fingerprint=_fingerprint(scope_payload),
    )


def build_backtest_variant(
    *,
    strategy_id: str | None,
    strategy_version: str | None = None,
    parameters: Mapping[str, object] | None = None,
) -> BacktestVariant:
    """Build explicit variant metadata without mixing it into scope identity."""
    normalized_parameters = dict(parameters or {})
    parameters_fingerprint = _fingerprint(normalized_parameters)
    variant_fingerprint = _fingerprint(
        {
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "parameters": normalized_parameters,
        }
    )
    return BacktestVariant(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        parameters=normalized_parameters,
        parameters_fingerprint=parameters_fingerprint,
        variant_fingerprint=variant_fingerprint,
    )


def build_data_scope_id(bars_by_symbol: Mapping[str, Sequence[Bar]]) -> str:
    """Return a deterministic identity for the normalized replay bars."""
    digest = hashlib.sha256()
    normalized_bars = {
        str(key).strip().upper(): tuple(bars)
        for key, bars in bars_by_symbol.items()
        if str(key).strip()
    }
    for symbol in sorted(normalized_bars):
        _update_digest(digest, {"symbol": symbol})
        bars = normalized_bars[symbol]
        for bar in sorted(
            bars,
            key=lambda item: (
                _utc(item.ts).isoformat(),
                item.open,
                item.high,
                item.low,
                item.close,
                item.volume,
                item.vwap if item.vwap is not None else float("-inf"),
                item.trade_count if item.trade_count is not None else float("-inf"),
            ),
        ):
            _update_digest(
                digest,
                {
                    "symbol": symbol,
                    "ts": _utc(bar.ts).isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "vwap": bar.vwap,
                    "trade_count": bar.trade_count,
                },
            )
    return f"sha256:{digest.hexdigest()}"


def _fingerprint(value: object) -> str:
    """Hash canonical JSON-compatible content."""
    payload = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _update_digest(digest: Any, value: object) -> None:
    digest.update(
        json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    )
    digest.update(b"\n")


def _jsonable(value: object) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(inner) for key, inner in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("review scope values must be finite")
        return value
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "BENCHMARK_ALLOCATION",
    "BENCHMARK_ID",
    "BENCHMARK_METHOD",
    "BacktestReviewScope",
    "BacktestVariant",
    "ReviewInitialPosition",
    "build_backtest_review_scope",
    "build_backtest_variant",
    "build_data_scope_id",
]
