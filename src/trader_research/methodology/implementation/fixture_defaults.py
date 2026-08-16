"""Provide deterministic fixture inputs for maintained method implementations.

Fixtures use bounded synthetic series and explicit parameters to exercise known
method contracts reproducibly. They contain no market-data reads, network calls,
or runtime state from live trading.
"""

from __future__ import annotations

from typing import Any, Mapping


def default_indicator_fixtures(method_id: str) -> tuple[Mapping[str, Any], ...]:
    """Return built-in deterministic indicator fixtures for maintained methods.

    Fixtures provide small ordered close-price sequences, expected warmup/output
    values, and numeric tolerances used when no caller-supplied fixture payload is
    provided. Unknown method IDs return an empty tuple so callers can emit a clear
    fixtures-required error instead of silently passing untested implementations.
    """
    fixtures = {
        "sma": (
            {
                "fixture_id": "sma_period_3_linear",
                "closes": [1, 2, 3, 4, 5],
                "expected": [None, None, 2.0, 3.0, 4.0],
                "tolerance": 1e-9,
            },
        ),
        "ema": (
            {
                "fixture_id": "ema_period_3_linear",
                "closes": [1, 2, 3, 4, 5, 6],
                "expected": [None, None, 2.0, 3.0, 4.0, 5.0],
                "tolerance": 1e-9,
            },
        ),
        "rsi": (
            {
                "fixture_id": "rsi_period_5_uptrend",
                "closes": [1, 2, 3, 4, 5, 6],
                "expected": [None, None, None, None, None, 100.0],
                "tolerance": 1e-9,
            },
        ),
        "rolling_volatility": (
            {
                "fixture_id": "rolling_volatility_window_3_linear",
                "closes": [1, 2, 3, 4, 5],
                "expected": [None, None, 1.0, 1.0, 1.0],
                "tolerance": 1e-9,
            },
        ),
        "z_score": (
            {
                "fixture_id": "z_score_window_3_linear",
                "closes": [1, 2, 3, 4, 5],
                "expected": [None, None, 1.0, 1.0, 1.0],
                "tolerance": 1e-9,
            },
        ),
        "bollinger_wma_band_rule": (
            {
                "fixture_id": "bollinger_wma_period_3_linear",
                "closes": [1, 2, 3, 4, 5],
                "expected": [
                    None,
                    None,
                    {
                        "middle": 2.0,
                        "upper": 3.632993161855452,
                        "lower": 0.36700683814454793,
                        "bandwidth": 1.632993161855452,
                    },
                    {
                        "middle": 3.0,
                        "upper": 4.6329931618554525,
                        "lower": 1.367006838144548,
                        "bandwidth": 1.088662107903635,
                    },
                    {
                        "middle": 4.0,
                        "upper": 5.6329931618554525,
                        "lower": 2.367006838144548,
                        "bandwidth": 0.8164965809277261,
                    },
                ],
                "tolerance": 1e-9,
            },
        ),
    }
    return fixtures.get(method_id, tuple())


def default_signal_fixtures(method_id: str) -> tuple[Mapping[str, Any], ...]:
    """Return built-in deterministic signal fixtures for maintained signal methods.

    Signal fixtures include full-series expectations plus prefix expectations for
    warmup and no-lookahead checks. Unknown method IDs return no fixtures, forcing
    the higher-level runner to fail explicitly unless the caller provides custom
    validation data.
    """
    fixtures = {
        "bollinger_bwma_action_signal": (
            {
                "fixture_id": "bollinger_bwma_action_lower_band_buy",
                "closes": [10.0] * 19 + [1.0],
                "expected": 1.0,
                "expected_prefix": [None] * 19 + [1.0],
                "tolerance": 1e-9,
            },
            {
                "fixture_id": "bollinger_bwma_action_upper_band_sell",
                "closes": [10.0] * 19 + [20.0],
                "expected": -1.0,
                "expected_prefix": [None] * 19 + [-1.0],
                "tolerance": 1e-9,
            },
            {
                "fixture_id": "bollinger_bwma_action_in_band_no_action",
                "closes": [10.0] * 20,
                "expected": 0.0,
                "expected_prefix": [None] * 19 + [0.0],
                "tolerance": 1e-9,
            },
        ),
    }
    return fixtures.get(method_id, tuple())
