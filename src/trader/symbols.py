"""Symbol and asset-class normalization helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


_CRYPTO_QUOTES = ("USD", "USDT", "USDC")


@dataclass(frozen=True)
class BrokerPositionView:
    """Broker position normalized for configured-universe safety checks.

    Attributes keep both canonical values and raw provider values so error
    messages can explain exactly why a live broker position was rejected.
    """

    symbol: str
    asset_class: str
    qty: float
    avg_entry_price: float | None
    side: str
    raw_symbol: str
    raw_asset_class: str


def normalize_asset_class(asset_class: str | None) -> str:
    """Map provider-specific asset-class spellings into runtime categories.

    Known equity spellings collapse to `stocks`, crypto spellings collapse to
    `crypto`, and unknown values are returned normalized for explicit mismatch
    reporting.
    """
    normalized = str(asset_class or "").strip().lower()
    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[-1]
    if normalized in {"crypto", "cryptocurrency"}:
        return "crypto"
    if normalized in {"us_equity", "equity", "stock", "stocks"}:
        return "stocks"
    return normalized


def canonicalize_symbol(symbol: str | None, *, asset_class: str | None) -> str:
    """Normalize symbol spelling for the configured asset-class namespace.

    Crypto symbols supplied as `BTCUSD`/`BTCUSDT` are converted to slash form so
    market-data, broker-position, and config comparisons use one spelling.
    """
    normalized = str(symbol or "").strip().upper()
    normalized_asset_class = normalize_asset_class(asset_class)
    if normalized_asset_class == "crypto" and normalized and "/" not in normalized:
        for quote in _CRYPTO_QUOTES:
            if normalized.endswith(quote) and len(normalized) > len(quote):
                base = normalized[: -len(quote)]
                if base:
                    return f"{base}/{quote}"
    return normalized


def normalize_broker_positions(positions: Sequence[Mapping[str, object]]) -> list[BrokerPositionView]:
    """Convert broker-native position payloads into comparable runtime views.

    Invalid/empty symbols and effectively flat positions are dropped. Short
    positions with positive provider quantities are converted to negative signed
    quantities before validation.
    """
    normalized: list[BrokerPositionView] = []
    for position in positions:
        raw_symbol = str(position.get("symbol", "")).strip().upper()
        if not raw_symbol:
            continue
        raw_asset_class = str(position.get("asset_class", "")).strip()
        asset_class = normalize_asset_class(raw_asset_class)
        symbol = canonicalize_symbol(raw_symbol, asset_class=asset_class)
        qty_raw = position.get("qty", 0.0)
        try:
            qty = float(qty_raw)
        except (TypeError, ValueError):
            qty = 0.0
        side = str(position.get("side", "")).lower().strip()
        if side == "short" and qty > 0:
            qty = -qty
        if abs(qty) < 1e-12:
            continue
        avg_raw = position.get("avg_entry_price")
        avg_entry_price = float(avg_raw) if avg_raw is not None else None
        normalized.append(
            BrokerPositionView(
                symbol=symbol,
                asset_class=asset_class,
                qty=qty,
                avg_entry_price=avg_entry_price,
                side=side or ("long" if qty >= 0 else "short"),
                raw_symbol=raw_symbol,
                raw_asset_class=raw_asset_class,
            )
        )
    return normalized


def configured_symbol_set(symbols: Sequence[str], *, asset_class: str) -> set[str]:
    """Return configured symbols in the same canonical form as broker positions."""
    return {
        canonicalize_symbol(symbol, asset_class=asset_class)
        for symbol in symbols
        if str(symbol).strip()
    }


def find_unmatched_positions(
    positions: Sequence[BrokerPositionView],
    *,
    configured_symbols: Sequence[str],
    configured_asset_class: str,
) -> list[BrokerPositionView]:
    """Return broker positions that would make live trading unsafe.

    A mismatch is any broker position with a different normalized asset class or
    a symbol outside the configured universe when that universe is non-empty.
    """
    normalized_asset_class = normalize_asset_class(configured_asset_class)
    allowed_symbols = configured_symbol_set(configured_symbols, asset_class=normalized_asset_class)
    mismatches: list[BrokerPositionView] = []
    for position in positions:
        if position.asset_class != normalized_asset_class:
            mismatches.append(position)
            continue
        if allowed_symbols and position.symbol not in allowed_symbols:
            mismatches.append(position)
    return mismatches
