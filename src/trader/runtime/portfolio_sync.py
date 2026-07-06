"""Pure broker portfolio synchronization value builders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from ..portfolio import Position
from ..symbols import BrokerPositionView, configured_symbol_set, find_unmatched_positions, normalize_broker_positions
from .service_config import parse_initial_cash, parse_initial_positions

__all__ = [
    "BrokerPortfolioSyncSnapshot",
    "InitialPortfolioSeedConfig",
    "InitialPortfolioSeedDecision",
    "build_broker_portfolio_sync_snapshot",
    "build_initial_portfolio_seed",
    "format_broker_portfolio_mismatch",
    "matched_position_log_records",
    "mismatched_position_log_records",
    "resolve_initial_portfolio_seed_config",
]


@dataclass(frozen=True)
class BrokerPortfolioSyncSnapshot:
    """Normalized broker portfolio state prepared for local persistence."""

    cash: float
    positions: tuple[Position, ...]
    configured_symbols: frozenset[str]
    matched_positions: tuple[BrokerPositionView, ...]
    mismatches: tuple[BrokerPositionView, ...]


@dataclass(frozen=True)
class InitialPortfolioSeedConfig:
    """Resolved seed config that determines whether current state must be read."""

    should_inspect_existing: bool
    reason: str
    positions_config: object | None = None
    cash_config: object | None = None


@dataclass(frozen=True)
class InitialPortfolioSeedDecision:
    """Decision for whether to persist an initial portfolio seed snapshot."""

    should_seed: bool
    reason: str
    positions: tuple[Position, ...] = ()
    cash: float = 0.0


def build_broker_portfolio_sync_snapshot(
    *,
    account: Mapping[str, object],
    positions_raw: Sequence[Mapping[str, object]],
    configured_symbols: Sequence[str],
    configured_asset_class: str,
) -> BrokerPortfolioSyncSnapshot:
    """Normalize broker account/position payloads for startup portfolio sync.

    The returned `positions` intentionally includes matched and mismatched
    broker positions. The service persists the broker snapshot first, then fails
    closed on mismatches so local evidence reflects the venue state that caused
    the halt.
    """
    cash_raw = account.get("cash", 0.0)
    cash = float(cash_raw) if cash_raw is not None else 0.0
    normalized_positions = tuple(normalize_broker_positions(positions_raw))
    mismatches = tuple(
        find_unmatched_positions(
            normalized_positions,
            configured_symbols=configured_symbols,
            configured_asset_class=configured_asset_class,
        )
    )
    configured_symbol_values = frozenset(
        configured_symbol_set(
            configured_symbols,
            asset_class=configured_asset_class,
        )
    )
    matched_positions = tuple(position for position in normalized_positions if position not in mismatches)
    positions = tuple(
        Position(symbol=position.symbol, qty=position.qty, avg_price=position.avg_entry_price)
        for position in normalized_positions
    )
    return BrokerPortfolioSyncSnapshot(
        cash=cash,
        positions=positions,
        configured_symbols=configured_symbol_values,
        matched_positions=matched_positions,
        mismatches=mismatches,
    )


def resolve_initial_portfolio_seed_config(
    *,
    portfolio_source: str,
    config_snapshot: Mapping[str, object] | None,
) -> InitialPortfolioSeedConfig:
    """Return seed config if startup should inspect current portfolio state."""
    if portfolio_source == "alpaca":
        return InitialPortfolioSeedConfig(False, "portfolio_source_alpaca")
    if not config_snapshot or not isinstance(config_snapshot, Mapping):
        return InitialPortfolioSeedConfig(False, "missing_config_snapshot")
    service_cfg = config_snapshot.get("trader_service", {})
    if service_cfg is None or not isinstance(service_cfg, Mapping):
        return InitialPortfolioSeedConfig(False, "missing_trader_service_config")
    positions_cfg = service_cfg.get("initial_positions")
    cash_cfg = service_cfg.get("initial_cash")
    if positions_cfg is None and cash_cfg is None:
        return InitialPortfolioSeedConfig(False, "missing_seed_config")
    return InitialPortfolioSeedConfig(
        True,
        "configured",
        positions_config=positions_cfg,
        cash_config=cash_cfg,
    )


def build_initial_portfolio_seed(
    *,
    seed_config: InitialPortfolioSeedConfig,
    existing_positions_count: int,
    existing_cash_balance: float,
) -> InitialPortfolioSeedDecision:
    """Return the startup initial-portfolio seed decision.

    The service supplies existing portfolio state after `seed_config` confirms a
    seed is configured. This keeps event-store reads outside the pure helper.
    """
    if not seed_config.should_inspect_existing:
        return InitialPortfolioSeedDecision(False, seed_config.reason)
    if existing_positions_count or abs(existing_cash_balance) > 1e-12:
        return InitialPortfolioSeedDecision(False, "existing_state")
    positions = tuple(parse_initial_positions(seed_config.positions_config))
    cash = parse_initial_cash(seed_config.cash_config)
    return InitialPortfolioSeedDecision(True, "configured", positions=positions, cash=cash)


def matched_position_log_records(snapshot: BrokerPortfolioSyncSnapshot) -> list[dict[str, object]]:
    """Return compact log records for in-scope broker positions."""
    return [
        {"symbol": position.symbol, "asset_class": position.asset_class, "qty": position.qty}
        for position in snapshot.matched_positions
    ]


def mismatched_position_log_records(snapshot: BrokerPortfolioSyncSnapshot) -> list[dict[str, object]]:
    """Return compact log records for broker positions outside the configured universe."""
    return [
        {
            "symbol": position.symbol,
            "asset_class": position.asset_class,
            "raw_symbol": position.raw_symbol,
            "raw_asset_class": position.raw_asset_class,
            "qty": position.qty,
        }
        for position in snapshot.mismatches
    ]


def format_broker_portfolio_mismatch(mismatches: Sequence[BrokerPositionView]) -> str:
    """Build the fail-closed message for broker positions outside the universe."""
    return "Broker portfolio mismatch with configured trading universe: " + ", ".join(
        "%s/%s qty=%s" % (position.raw_symbol, position.raw_asset_class or "<none>", position.qty)
        for position in mismatches
    )
