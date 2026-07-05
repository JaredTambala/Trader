"""Pure broker-response and broker-portfolio helpers for decision cycles."""

from __future__ import annotations

from typing import Mapping, Sequence

from ..config import Config
from ..portfolio import Portfolio, Position
from ..symbols import BrokerPositionView, find_unmatched_positions, normalize_broker_positions


def _resolve_broker_response_status(response: Mapping[str, object]) -> str:
    """Return the normalized broker response status for cycle decisions."""
    return str(response.get("status", "submitted"))


def _should_sync_portfolio_for_broker_response(
    *,
    status: str,
    sync_portfolio_on_fill: bool,
) -> bool:
    """Return whether a broker response should trigger portfolio synchronization."""
    return sync_portfolio_on_fill and status in {"filled", "partially_filled"}


def _build_processed_order_from_broker_response(
    order: Mapping[str, object],
    response: Mapping[str, object],
) -> Mapping[str, object] | None:
    """Build the processed-order evidence carried forward after broker response."""
    status = _resolve_broker_response_status(response)
    if status in {"rejected", "canceled", "expired", "error"}:
        return None
    processed_order = order
    fill_qty = response.get("fill_qty")
    fill_price = response.get("fill_price")
    if fill_qty is not None:
        processed_order = {**processed_order, "qty": float(fill_qty)}
    if fill_price is not None:
        processed_order = {**processed_order, "price": float(fill_price)}
    return processed_order


def _coerce_broker_cash(account: object) -> float:
    """Return a numeric cash balance from a broker account payload."""
    cash_raw = account.get("cash", 0.0) if isinstance(account, Mapping) else 0.0
    return float(cash_raw) if cash_raw is not None else 0.0


def _broker_position_views_to_positions(
    positions: Sequence[BrokerPositionView],
) -> dict[str, Position]:
    """Convert normalized broker position views into runtime positions."""
    return {
        position.symbol: Position(
            symbol=position.symbol,
            qty=position.qty,
            avg_price=position.avg_entry_price,
        )
        for position in positions
    }


def _validate_broker_positions(
    positions: Sequence[BrokerPositionView],
    config: Config,
) -> None:
    """Fail closed when broker positions are outside the configured universe."""
    mismatches = find_unmatched_positions(
        positions,
        configured_symbols=config.market_data_symbols,
        configured_asset_class=config.market_data_asset_class,
    )
    if not mismatches:
        return
    mismatch_text = ", ".join(
        "%s(asset_class=%s raw_symbol=%s raw_asset_class=%s qty=%s)"
        % (
            position.symbol,
            position.asset_class,
            position.raw_symbol,
            position.raw_asset_class or "<none>",
            position.qty,
        )
        for position in mismatches
    )
    raise ValueError(
        "Broker portfolio mismatch with configured trading universe "
        f"symbols={config.market_data_symbols} asset_class={config.market_data_asset_class}: {mismatch_text}"
    )


def _build_portfolio_from_broker_payload(
    *,
    account: object,
    positions_raw: Sequence[Mapping[str, object]],
    config: Config,
) -> Portfolio:
    """Build a validated runtime portfolio from broker account and position payloads."""
    normalized_positions = normalize_broker_positions(positions_raw)
    _validate_broker_positions(normalized_positions, config)
    return Portfolio(
        positions=_broker_position_views_to_positions(normalized_positions),
        cash_balance=_coerce_broker_cash(account),
    )


__all__ = [
    "_build_portfolio_from_broker_payload",
    "_build_processed_order_from_broker_response",
    "_broker_position_views_to_positions",
    "_coerce_broker_cash",
    "_resolve_broker_response_status",
    "_should_sync_portfolio_for_broker_response",
]
