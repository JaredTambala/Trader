"""Maintained strategy consumers for resolved model predictions."""

from __future__ import annotations

from datetime import datetime
import json
import math
from typing import Mapping, Sequence

from trader.event_store import EventStore
from trader.portfolio import Portfolio
from trader.predictions import (
    PredictionDecision,
    RuntimePredictionBinding,
    StrategyPrediction,
    canonical_json_hash,
)
from trader.strategies import Strategy
from trader_standard.bar_signals import fetch_recent_bars, table_for_asset_class


class PredictionDrivenStrategy(Strategy):
    """Interpret mapped prediction inputs through one declared consumer policy."""

    def __init__(
        self,
        *,
        symbols: Sequence[str],
        asset_class: str,
        timeframe: str,
        prediction_bindings: Sequence[RuntimePredictionBinding],
        prediction_binding_name: str,
        input_name: str,
        consumer_kind: str = "directional",
        order_qty: float = 1.0,
        decision_threshold: float = 0.0,
        long_count: int = 1,
        short_count: int = 1,
        long_regime: str = "risk_on",
        short_regime: str = "risk_off",
        active_regime: str = "active",
    ) -> None:
        self._symbols = tuple(str(item).strip().upper() for item in symbols if str(item).strip())
        self._asset_class = str(asset_class)
        self._timeframe = str(timeframe)
        by_name = {item.binding_name: item for item in prediction_bindings}
        try:
            self._binding = by_name[str(prediction_binding_name)]
        except KeyError as exc:
            raise ValueError(f"unknown runtime prediction binding: {prediction_binding_name}") from exc
        if set(by_name) != {str(prediction_binding_name)}:
            raise ValueError("maintained prediction strategy requires exactly its declared binding")
        self._input_name = str(input_name).strip()
        self._consumer_kind = str(consumer_kind)
        self._order_qty = _positive(order_qty, "order_qty")
        self._decision_threshold = _non_negative(decision_threshold, "decision_threshold")
        self._long_count = _positive_integer(long_count, "long_count")
        self._short_count = _positive_integer(short_count, "short_count")
        self._long_regime = str(long_regime)
        self._short_regime = str(short_regime)
        self._active_regime = str(active_regime)
        if not self._symbols or not self._input_name:
            raise ValueError("prediction strategy symbols and input_name are required")
        if self._consumer_kind not in {
            "directional",
            "ranking",
            "regime",
            "gating",
            "allocation",
        }:
            raise ValueError(f"unsupported prediction strategy consumer_kind: {self._consumer_kind}")
        if self._consumer_kind in {"ranking", "allocation"} and self._binding.decision_scope != "universe_snapshot":
            raise ValueError(f"{self._consumer_kind} prediction consumers require universe_snapshot scope")
        identity = {
            "symbols": self._symbols,
            "asset_class": self._asset_class,
            "timeframe": self._timeframe,
            "deployment_id": self._binding.deployment_id,
            "deployment_validation_id": self._binding.deployment_validation_id,
            "mapper_id": self._binding.mapper.mapper_id,
            "input_name": self._input_name,
            "consumer_kind": self._consumer_kind,
            "order_qty": self._order_qty,
            "decision_threshold": self._decision_threshold,
            "long_count": self._long_count,
            "short_count": self._short_count,
            "long_regime": self._long_regime,
            "short_regime": self._short_regime,
            "active_regime": self._active_regime,
        }
        self._strategy_id = f"prediction_driven:{canonical_json_hash(identity)[:20]}"

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def decision_scope(self) -> str:
        return self._binding.decision_scope

    @property
    def required_lookback(self) -> int:
        return self._binding.required_lookback

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        return self._generate(
            symbols=self._symbols,
            run_id=run_id,
            cycle_id=cycle_id,
            decision_ts=decision_ts,
            event_store=event_store,
            portfolio=portfolio,
        )

    def generate_orders_for_symbol(
        self,
        symbol: str,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        if self.decision_scope != "per_symbol":
            raise ValueError("universe_snapshot strategy cannot run through per-symbol callbacks")
        normalized = str(symbol).strip().upper()
        if normalized not in self._symbols:
            raise ValueError(f"symbol is outside the strategy universe: {normalized}")
        return self._generate(
            symbols=(normalized,),
            run_id=run_id,
            cycle_id=cycle_id,
            decision_ts=decision_ts,
            event_store=event_store,
            portfolio=portfolio,
        )

    def _generate(
        self,
        *,
        symbols: Sequence[str],
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> tuple[Mapping[str, object], ...]:
        decision = self._binding.evaluate(
            run_id=run_id,
            cycle_id=cycle_id,
            decision_ts=decision_ts,
            event_store=event_store,
            symbols=symbols,
        )
        inputs = tuple(item for item in decision.strategy_inputs if item.name == self._input_name)
        if not inputs:
            return ()
        for item in inputs:
            self._record_strategy_input(event_store, run_id, cycle_id, decision_ts, item, decision)
        if self._consumer_kind == "directional":
            targets = {
                str(item.symbol): self._order_qty * _direction(item.value, self._decision_threshold)
                for item in inputs
                if item.symbol
            }
        elif self._consumer_kind == "ranking":
            targets = self._ranking_targets(inputs)
        elif self._consumer_kind == "allocation":
            targets = self._allocation_targets(inputs, portfolio, event_store, decision_ts)
        elif self._consumer_kind == "regime":
            targets = {
                str(item.symbol): (
                    self._order_qty
                    if item.value == self._long_regime
                    else -self._order_qty
                    if item.value == self._short_regime
                    else 0.0
                )
                for item in inputs
                if item.symbol
            }
        else:
            targets = {
                str(item.symbol): (
                    self._order_qty
                    if item.value is True or item.value == self._active_regime
                    else 0.0
                )
                for item in inputs
                if item.symbol
            }
        evidence = {
            "binding_name": decision.binding_name,
            "deployment_id": decision.deployment_id,
            "deployment_validation_id": decision.deployment_validation_id,
            "model_version_id": decision.prediction_batch.model_identity.model_version_id,
            "feature_set_id": decision.feature_batch.feature_set_id,
            "feature_batch_hash": decision.feature_batch.input_hash,
            "prediction_event_ids": list(decision.prediction_event_ids),
            "mapper_id": decision.mapper_id,
            "mapper_parameters": dict(decision.mapper_parameters),
        }
        return tuple(
            order
            for symbol, target_qty in sorted(targets.items())
            if (
                order := _target_order(
                    symbol=symbol,
                    target_qty=target_qty,
                    current_qty=portfolio.positions.get(symbol).qty if symbol in portfolio.positions else 0.0,
                    decision_evidence=evidence,
                )
            )
            is not None
        )

    def _ranking_targets(self, inputs: Sequence[StrategyPrediction]) -> dict[str, float]:
        ranked = sorted(
            ((str(item.symbol), _number(item.value, self._input_name)) for item in inputs if item.symbol),
            key=lambda item: (-item[1], item[0]),
        )
        targets = {symbol: 0.0 for symbol, _ in ranked}
        for symbol, _ in ranked[: self._long_count]:
            targets[symbol] = self._order_qty
        for symbol, _ in ranked[-self._short_count :]:
            targets[symbol] = -self._order_qty
        return targets

    def _allocation_targets(
        self,
        inputs: Sequence[StrategyPrediction],
        portfolio: Portfolio,
        event_store: EventStore,
        decision_ts: datetime,
    ) -> dict[str, float]:
        prices = _latest_prices(
            event_store,
            symbols=tuple(str(item.symbol) for item in inputs if item.symbol),
            asset_class=self._asset_class,
            timeframe=self._timeframe,
            decision_ts=decision_ts,
        )
        value = portfolio.cash_balance + sum(
            position.qty * prices.get(symbol, position.avg_price or 0.0)
            for symbol, position in portfolio.positions.items()
        )
        if value <= 0:
            raise ValueError("allocation prediction consumer requires positive portfolio value")
        targets: dict[str, float] = {}
        for item in inputs:
            if not item.symbol or item.symbol not in prices:
                raise ValueError(f"allocation prediction is missing a current price for {item.symbol}")
            weight = _number(item.value, self._input_name)
            targets[item.symbol] = value * weight / prices[item.symbol]
        return targets

    def _record_strategy_input(
        self,
        event_store: EventStore,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        item: StrategyPrediction,
        decision: PredictionDecision,
    ) -> None:
        value = (
            float(item.value)
            if isinstance(item.value, (int, float))
            and not isinstance(item.value, bool)
            and math.isfinite(float(item.value))
            else None
        )
        event_store.record_event(
            "signal_events",
            {
                "run_id": run_id,
                "session_id": run_id,
                "cycle_id": cycle_id,
                "symbol": item.symbol,
                "signal_name": self._input_name,
                "signal_value": value,
                "target_qty": None,
                "generated_at": decision_ts,
                "prediction_event_refs": json.dumps(list(decision.prediction_event_ids), sort_keys=True),
                "mapper_id": decision.mapper_id,
                "payload": json.dumps(
                    {
                        "source_output_names": list(item.source_output_names),
                        "value": item.value,
                        "metadata": dict(item.metadata),
                    },
                    sort_keys=True,
                ),
            },
        )


def build_prediction_driven_strategy(**kwargs: object) -> PredictionDrivenStrategy:
    """Factory entrypoint for canonical implementation registration."""
    return PredictionDrivenStrategy(**kwargs)  # type: ignore[arg-type]


def _target_order(
    *,
    symbol: str,
    target_qty: float,
    current_qty: float,
    decision_evidence: Mapping[str, object],
) -> Mapping[str, object] | None:
    delta = target_qty - current_qty
    if abs(delta) < 1e-12:
        return None
    return {
        "symbol": symbol,
        "side": "buy" if delta > 0 else "sell",
        "qty": abs(delta),
        "order_type": "market",
        "decision_evidence": dict(decision_evidence),
    }


def _latest_prices(
    event_store: EventStore,
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    decision_ts: datetime,
) -> dict[str, float]:
    table = table_for_asset_class(asset_class)
    output: dict[str, float] = {}
    for symbol in symbols:
        bars = fetch_recent_bars(
            event_store,
            table=table,
            symbol=symbol,
            timeframe=timeframe,
            limit=1,
            as_of_ts=decision_ts,
        )
        if bars:
            output[symbol] = float(bars[0].close)
    return output


def _direction(value: object, threshold: float) -> float:
    number = _number(value, "directional prediction")
    return 1.0 if number > threshold else -1.0 if number < -threshold else 0.0


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite numeric content")
    return float(value)


def _positive(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number


def _non_negative(value: object, label: str) -> float:
    number = _number(value, label)
    if number < 0:
        raise ValueError(f"{label} must be non-negative")
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value
