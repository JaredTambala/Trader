"""Helper builders for the trader_standard strategy examples."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from trader.config import Config
from trader.risk import (
    RiskManager,
    RiskPipeline,
)
from trader_standard.risk import (
    HaltRiskManager,
    MaxGrossExposureRiskManager,
    MaxOrdersPerRunRiskManager,
    MaxPositionUsdPerSymbolRiskManager,
    NoOpRiskManager,
    OpenBuyOrderLimitRiskManager,
)
from trader_standard.strategies import (
    CompositeStopPolicy,
    FixedStopLossPolicy,
    StopPolicy,
    TrailingStopPolicy,
    build_bollinger_band_strategy,
    build_mean_reversion_strategy,
    build_trend_following_strategy,
)


def build_library_strategy(config_data: Mapping[str, Any], config: Config):
    """Build one of the built-in policy-driven strategies from passive YAML input."""
    strategy_cfg = config_data.get("strategy", {})
    if not isinstance(strategy_cfg, Mapping):
        raise ValueError("strategy section must be a mapping")
    strategy_id = str(strategy_cfg.get("id", "trend_following"))
    symbols = config.market_data_symbols
    asset_class = config.market_data_asset_class
    timeframe = config.strategy_timeframe

    if strategy_id == "trend_following":
        settings = _section(strategy_cfg, "trend_following")
        return build_trend_following_strategy(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            target_qty_when_long=_float(settings.get("target_qty_when_long"), 1.0),
            stop_policy=_build_stop_policy(settings),
            ema_fast_period=_int(settings.get("ema_fast_period"), 12),
            ema_slow_period=_int(settings.get("ema_slow_period"), 26),
            macd_fast_period=_int(settings.get("macd_fast_period"), 12),
            macd_slow_period=_int(settings.get("macd_slow_period"), 26),
            macd_signal_period=_int(settings.get("macd_signal_period"), 9),
        )
    if strategy_id == "mean_reversion":
        settings = _section(strategy_cfg, "mean_reversion")
        return build_mean_reversion_strategy(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            target_qty_when_long=_float(settings.get("target_qty_when_long"), 1.0),
            stop_policy=_build_stop_policy(settings),
            rsi_period=_int(settings.get("rsi_period"), 14),
            oversold=_float(settings.get("oversold"), 30.0),
            exit_rsi=_float(settings.get("exit_rsi"), 50.0),
            mean_period=_int(settings.get("mean_period"), 20),
            stretch_pct=_float(settings.get("stretch_pct"), 0.02),
        )
    if strategy_id == "bollinger_band":
        settings = _section(strategy_cfg, "bollinger_band")
        return build_bollinger_band_strategy(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            target_qty_when_long=_float(settings.get("target_qty_when_long"), 1.0),
            stop_policy=_build_stop_policy(settings),
            period=_int(settings.get("period"), 20),
            stddev_multiplier=_float(settings.get("stddev_multiplier"), 2.0),
        )
    raise ValueError(f"Unsupported built-in strategy id: {strategy_id}")


def build_library_risk_manager(risk_cfg: Mapping[str, object] | None = None) -> RiskManager:
    """Build a risk pipeline from passive YAML input."""
    risk_cfg = risk_cfg or {}
    managers: list[RiskManager] = []
    if bool(risk_cfg.get("halted", False)):
        managers.append(HaltRiskManager())
    if risk_cfg.get("max_orders_per_run") is not None:
        managers.append(MaxOrdersPerRunRiskManager(limit=int(risk_cfg["max_orders_per_run"])))
    if risk_cfg.get("max_gross_usd") is not None:
        managers.append(MaxGrossExposureRiskManager(limit_usd=float(risk_cfg["max_gross_usd"])))
    if risk_cfg.get("max_pos_usd_per_symbol") is not None:
        managers.append(
            MaxPositionUsdPerSymbolRiskManager(limit_usd=float(risk_cfg["max_pos_usd_per_symbol"]))
        )
    if risk_cfg.get("max_open_buy_orders_per_symbol") is not None:
        managers.append(
            OpenBuyOrderLimitRiskManager(
                max_open_buy_orders_per_symbol=int(risk_cfg["max_open_buy_orders_per_symbol"])
            )
        )
    if not managers:
        return NoOpRiskManager()
    return RiskPipeline(managers)


def with_runtime_mode(config: Config, *, mode: str) -> Config:
    """Return a copy of the config with a different runtime mode."""
    return replace(config, mode=mode)


def _build_stop_policy(settings: Mapping[str, Any]) -> StopPolicy | None:
    policies: list[StopPolicy] = []
    fixed_pct = settings.get("fixed_stop_loss_pct")
    if fixed_pct is not None:
        policies.append(FixedStopLossPolicy(stop_loss_pct=float(fixed_pct)))
    trailing_pct = settings.get("trailing_stop_pct")
    if trailing_pct is not None:
        policies.append(TrailingStopPolicy(trailing_stop_pct=float(trailing_pct)))
    if not policies:
        return None
    if len(policies) == 1:
        return policies[0]
    return CompositeStopPolicy(policies)


def _section(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"strategy.{key} must be a mapping")
    return value


def _int(value: object, default: int) -> int:
    return default if value is None else int(value)


def _float(value: object, default: float) -> float:
    return default if value is None else float(value)
