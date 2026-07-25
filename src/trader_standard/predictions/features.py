"""Maintained point-in-time bar feature provider."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Mapping, Sequence

from trader.event_store import EventStore
from trader.predictions import FeatureBatch, FeatureColumn, FeatureRow
from trader.signals import Bar
from trader_standard.bar_signals import fetch_recent_bars, table_for_asset_class


class BarFeatureProvider:
    """Build declared bar fields and return transforms with no future reads."""

    def __init__(
        self,
        *,
        feature_set: Mapping[str, Any],
        decision_scope: str,
    ) -> None:
        self._feature_set = dict(feature_set)
        self.feature_set_id = str(feature_set.get("feature_set_id") or "").strip()
        self.feature_set_digest = str(feature_set.get("feature_set_digest") or "").strip()
        self.decision_scope = str(decision_scope)
        if not self.feature_set_id or not self.feature_set_digest:
            raise ValueError("bar feature provider requires feature-set identity")
        raw_schema = feature_set.get("schema")
        if not isinstance(raw_schema, Sequence) or isinstance(raw_schema, (str, bytes)) or not raw_schema:
            raise ValueError("bar feature provider requires a non-empty feature schema")
        self._schema = tuple(_normalize_feature(item) for item in raw_schema)
        self.required_lookback = max(_feature_lookback(item) for item in self._schema)

    def build(
        self,
        *,
        decision_ts: datetime,
        symbols: Sequence[str],
        asset_class: str,
        timeframe: str,
        event_store: EventStore,
    ) -> FeatureBatch:
        """Read only bars available by the decision timestamp and build one row per symbol."""
        rows: list[FeatureRow] = []
        missing: list[str] = []
        table = table_for_asset_class(asset_class)
        for symbol in symbols:
            bars = fetch_recent_bars(
                event_store,
                table=table,
                symbol=symbol,
                timeframe=timeframe,
                limit=self.required_lookback,
                as_of_ts=decision_ts,
            )
            if len(bars) < self.required_lookback:
                missing.extend(f"{symbol}:{item['name']}" for item in self._schema)
                continue
            values = {str(item["name"]): _compute_feature(item, bars) for item in self._schema}
            unavailable = [name for name, value in values.items() if value is None]
            if unavailable:
                missing.extend(f"{symbol}:{name}" for name in unavailable)
                continue
            latest_ts = bars[0].ts
            rows.append(
                FeatureRow(
                    symbol=symbol,
                    as_of_ts=latest_ts,
                    availability_ts=latest_ts,
                    values=values,
                )
            )
        return FeatureBatch.build(
            feature_set_id=self.feature_set_id,
            feature_set_digest=self.feature_set_digest,
            decision_ts=decision_ts,
            schema=tuple(
                FeatureColumn(
                    name=str(item["name"]),
                    dtype=str(item["dtype"]),
                    nullable=bool(item["nullable"]),
                )
                for item in self._schema
            ),
            rows=rows,
            missing_features=missing,
        )


def _normalize_feature(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("feature schema entries must be mappings")
    item = dict(value)
    name = str(item.get("name") or "").strip()
    dtype = str(item.get("dtype") or "float64").strip()
    transform = item.get("transform")
    if not isinstance(transform, Mapping):
        raise ValueError(f"feature {name or '<unknown>'} requires a transform mapping")
    kind = str(transform.get("kind") or "").strip()
    field = str(transform.get("field") or "close").strip()
    periods = int(transform.get("periods") or 0)
    lag = int(transform.get("lag") or 0)
    if not name or not dtype:
        raise ValueError("feature name and dtype are required")
    if kind not in {"bar_field", "simple_return", "log_return"}:
        raise ValueError(f"unsupported maintained feature transform: {kind}")
    if field not in {"open", "high", "low", "close", "volume", "vwap", "trade_count"}:
        raise ValueError(f"unsupported bar field: {field}")
    if lag < 0 or periods < 0:
        raise ValueError("feature lag and periods must be non-negative")
    if kind != "bar_field" and periods < 1:
        raise ValueError(f"feature {kind} requires periods >= 1")
    return {
        "name": name,
        "dtype": dtype,
        "nullable": bool(item.get("nullable", False)),
        "transform": {"kind": kind, "field": field, "periods": periods, "lag": lag},
    }


def _feature_lookback(feature: Mapping[str, Any]) -> int:
    transform = feature["transform"]
    return int(transform["lag"]) + int(transform["periods"]) + 1


def _compute_feature(feature: Mapping[str, Any], bars: Sequence[Bar]) -> float | None:
    transform = feature["transform"]
    lag = int(transform["lag"])
    periods = int(transform["periods"])
    field = str(transform["field"])
    current = getattr(bars[lag], field)
    if current is None:
        return None
    if transform["kind"] == "bar_field":
        return _finite(current)
    previous = getattr(bars[lag + periods], field)
    if previous is None or float(previous) == 0:
        return None
    ratio = float(current) / float(previous)
    if transform["kind"] == "log_return":
        if ratio <= 0:
            return None
        return _finite(math.log(ratio))
    return _finite(ratio - 1.0)


def _finite(value: object) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("bar feature value must be finite")
    return number
