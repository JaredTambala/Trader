"""Allowlisted profile catalogue and typed parameter contracts.

Subject: Maintained strategy/risk catalogue normalization and resolver boundaries.
Level: Pure unit contracts over standard implementations.
Collaborators: Catalogue descriptors, builders, and risk manager descriptors; no database or HTTP service.
Guarantees: Supported profiles resolve deterministically, typed bounds reject unsafe values, and fingerprints are stable.
Non-goals: Dataset coverage, Console persistence, worker execution, or profitability claims.
"""

from __future__ import annotations

import pytest

from trader_standard.catalogue import (
    CatalogueValidationError,
    fingerprint_definition,
    maintained_catalogue,
    normalize_asset_class,
    normalize_symbols,
    normalize_timeframe,
)


def test_catalogue_exposes_versioned_strategy_and_risk_profiles() -> None:
    """Expose the first-party Bollinger and safe risk profiles with typed metadata."""
    catalogue = maintained_catalogue()

    assert catalogue.version == "standard-1"
    assert {profile.profile_id for profile in catalogue.strategies} == {"noop", "bollinger_band"}
    assert {profile.profile_id for profile in catalogue.risks} == {
        "noop", "max_orders_per_run", "max_position_usd_per_symbol"
    }
    bollinger = catalogue.get("strategy", "bollinger_band", "standard-1")
    assert bollinger.lookback_bars == 21
    assert {parameter.name for parameter in bollinger.parameters} == {
        "period", "stddev_multiplier", "target_qty_when_long"
    }


def test_catalogue_normalizes_parameters_and_builds_allowlisted_objects() -> None:
    """Build exact maintained objects without accepting arbitrary import paths or callables."""
    catalogue = maintained_catalogue()
    parameters = catalogue.normalize_parameters(
        "strategy",
        "bollinger_band",
        {"period": "24", "stddev_multiplier": "2.5", "target_qty_when_long": "0.01"},
    )
    strategy = catalogue.build_strategy(
        "bollinger_band",
        version="standard-1",
        parameters=parameters,
        symbols=("BTC/USD",),
        asset_class="crypto",
        timeframe="1Min",
    )
    risk = catalogue.build_risk_manager(
        "max_orders_per_run", version="standard-1", parameters={"limit": "12"}
    )

    assert strategy.strategy_id == "bollinger_band"
    assert strategy.required_lookback == 25
    assert risk.risk_descriptor()["manager_id"] == "max_orders_per_run"
    assert risk.risk_descriptor()["parameters"] == {"limit": 12}


def test_catalogue_rejects_unknown_profiles_parameters_versions_and_bounds() -> None:
    """Reject unsupported profile identities and unsafe typed values before resolution."""
    catalogue = maintained_catalogue()

    with pytest.raises(CatalogueValidationError, match="Unknown strategy profile"):
        catalogue.get("strategy", "module.Class")
    with pytest.raises(CatalogueValidationError, match="Unsupported strategy profile version"):
        catalogue.get("strategy", "noop", "future-9")
    with pytest.raises(CatalogueValidationError, match="Unknown parameters"):
        catalogue.normalize_parameters("strategy", "noop", {"callable": "evil"})
    with pytest.raises(CatalogueValidationError, match="at most"):
        catalogue.normalize_parameters("strategy", "bollinger_band", {"period": 9999})


def test_catalogue_normalizers_canonicalize_scope_and_fingerprint_inputs() -> None:
    """Keep symbols, asset classes, timeframes, and definition hashes deterministic."""
    assert normalize_symbols((" aapl ", "AAPL", "btc/usd")) == ("AAPL", "BTC/USD")
    assert normalize_asset_class("stocks") == "stock"
    assert normalize_timeframe("1 hour") == "1Hour"
    assert fingerprint_definition({"b": 2, "a": 1}) == fingerprint_definition({"a": 1, "b": 2})
