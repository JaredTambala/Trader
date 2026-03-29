"""Tests for runtime symbol normalization and mismatch detection."""

from trader.symbols import (
    canonicalize_symbol,
    find_unmatched_positions,
    normalize_asset_class,
    normalize_broker_positions,
)


def test_canonicalize_crypto_pair_without_collapsing_equity_symbol() -> None:
    assert canonicalize_symbol("BTCUSD", asset_class="crypto") == "BTC/USD"
    assert canonicalize_symbol("BTC", asset_class="stocks") == "BTC"


def test_find_unmatched_positions_detects_cross_asset_mismatch() -> None:
    positions = normalize_broker_positions(
        [
            {
                "symbol": "BTC",
                "asset_class": "us_equity",
                "qty": "-1",
                "avg_entry_price": "39.77",
                "side": "short",
            }
        ]
    )

    mismatches = find_unmatched_positions(
        positions,
        configured_symbols=("BTC/USD",),
        configured_asset_class="crypto",
    )

    assert len(mismatches) == 1
    assert mismatches[0].symbol == "BTC"
    assert mismatches[0].asset_class == "stocks"


def test_normalize_asset_class_handles_enum_style_values() -> None:
    assert normalize_asset_class("assetclass.crypto") == "crypto"
    assert normalize_asset_class("AssetClass.US_EQUITY") == "stocks"


def test_normalize_broker_positions_normalizes_enum_style_crypto_pair() -> None:
    positions = normalize_broker_positions(
        [
            {
                "symbol": "BTCUSD",
                "asset_class": "assetclass.crypto",
                "qty": "0.009974999",
                "avg_entry_price": "65648.0",
                "side": "long",
            }
        ]
    )

    assert len(positions) == 1
    assert positions[0].symbol == "BTC/USD"
    assert positions[0].asset_class == "crypto"
