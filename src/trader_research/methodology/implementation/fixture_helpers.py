"""Low-level indicator and signal fixture helpers."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from trader.indicators import Indicator
from trader.signals import Bar, Signal

from trader_research.foundation import stable_research_id
from trader_research.methodology.implementation.manifest import sequence


def run_indicator_fixture(indicator: Indicator, fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one indicator fixture and report output and no-lookahead mismatches.

    The helper builds deterministic bars from ascending closes, runs the indicator,
    restores results to input order with explicit warmup nulls, compares nested
    expected values with tolerance, and reruns prefixes to detect lookahead leaks.
    ValueErrors from the implementation become failed fixture reports instead of
    escaping the validation workflow.
    """
    fixture_id = str(fixture.get("fixture_id") or stable_research_id("fixture", fixture))
    closes = [float(value) for value in sequence(fixture.get("closes"))]
    expected = [expected_value(value) for value in sequence(fixture.get("expected"))]
    tolerance = float(fixture.get("tolerance") or 1e-9)
    warnings: list[str] = []
    bars = bars_from_ascending_closes(closes)
    try:
        raw_actual = list(indicator.compute_series(bars))
    except ValueError as exc:
        return {
            "fixture_id": fixture_id,
            "status": "failed",
            "message": str(exc),
            "input_count": len(closes),
            "expected": expected,
            "actual": [],
            "warnings": warnings,
        }
    actual = [None] * (indicator.window - 1) + list(reversed(raw_actual))
    mismatches: list[Mapping[str, Any]] = []
    if len(actual) != len(expected):
        mismatches.append({"reason": "output length mismatch", "expected_length": len(expected), "actual_length": len(actual)})
    for idx, (expected_item, actual_item) in enumerate(zip(expected, actual, strict=False)):
        if not values_match(expected_item, actual_item, tolerance=tolerance):
            mismatches.append({"index": idx, "expected": expected_item, "actual": actual_item})
    mismatches.extend(_lookahead_mismatches(indicator, closes, actual, tolerance=tolerance))
    return {
        "fixture_id": fixture_id,
        "status": "passed" if not mismatches else "failed",
        "input_count": len(closes),
        "warmup_null_count": indicator.window - 1,
        "expected": expected,
        "actual": [expected_value(value) for value in actual],
        "mismatches": mismatches,
        "warnings": warnings,
    }


def run_signal_fixture(signal: Signal, fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one signal fixture with final-output and prefix validation.

    The helper runs the signal over deterministic bars, compares the final output
    to the expected value, and optionally evaluates each prefix against
    `expected_prefix` to enforce warmup and no-lookahead behavior. Implementation
    ValueErrors are captured as structured mismatches for the validation report.
    """
    fixture_id = str(fixture.get("fixture_id") or stable_research_id("signal_fixture", fixture))
    closes = [float(value) for value in sequence(fixture.get("closes"))]
    expected = expected_value(fixture.get("expected"))
    tolerance = float(fixture.get("tolerance") or 1e-9)
    warnings: list[str] = []
    bars = bars_from_ascending_closes(closes)
    try:
        actual = signal.compute(bars)
    except ValueError as exc:
        return {
            "fixture_id": fixture_id,
            "status": "failed",
            "message": str(exc),
            "input_count": len(closes),
            "expected": expected,
            "actual": None,
            "warnings": warnings,
            "mismatches": [{"reason": "signal raised ValueError"}],
        }
    mismatches = []
    if not values_match(expected, actual, tolerance=tolerance):
        mismatches.append({"reason": "output mismatch", "expected": expected, "actual": actual})
    prefix_results = []
    expected_prefix = [expected_value(value) for value in sequence(fixture.get("expected_prefix"))]
    for idx, expected_item in enumerate(expected_prefix):
        prefix_closes = closes[: idx + 1]
        prefix_bars = bars_from_ascending_closes(prefix_closes)
        prefix_error: str | None
        try:
            prefix_actual = signal.compute(prefix_bars)
        except ValueError as exc:
            prefix_actual = None
            prefix_error = str(exc)
        else:
            prefix_error = None
        prefix_results.append(
            {
                "index": idx,
                "expected": expected_item,
                "actual": expected_value(prefix_actual),
                "error": prefix_error,
            }
        )
        if expected_item is None:
            if prefix_error is None:
                mismatches.append({"index": idx, "reason": "prefix expected warmup failure", "actual": prefix_actual})
            continue
        if prefix_error is not None:
            mismatches.append({"index": idx, "reason": "prefix raised ValueError", "message": prefix_error})
        elif not values_match(expected_item, prefix_actual, tolerance=tolerance):
            mismatches.append({"index": idx, "reason": "no-lookahead prefix mismatch", "expected": expected_item, "actual": prefix_actual})
    return {
        "fixture_id": fixture_id,
        "status": "passed" if not mismatches else "failed",
        "input_count": len(closes),
        "warmup_null_count": signal.window - 1,
        "expected": expected,
        "actual": expected_value(actual),
        "expected_prefix": expected_prefix,
        "prefix_results": prefix_results,
        "mismatches": mismatches,
        "warnings": warnings,
    }


def bars_from_ascending_closes(closes: Sequence[float]) -> list[Bar]:
    """Build reverse-chronological bars from ascending close prices.

    Fixture payloads are easier to read in chronological order, while the Trader
    runtime expects the newest bar first. This helper gives each synthetic bar a
    stable timestamp and OHLC value equal to the close so tests isolate indicator
    math rather than market-data construction.
    """
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [
        Bar(
            ts=base + timedelta(minutes=idx),
            open=float(close),
            high=float(close),
            low=float(close),
            close=float(close),
            volume=1.0,
            vwap=None,
            trade_count=None,
        )
        for idx, close in enumerate(closes)
    ]
    return list(reversed(bars))


def values_match(expected: Any, actual: Any, *, tolerance: float) -> bool:
    """Compare fixture values recursively with numeric tolerance.

    The comparator normalizes dataclasses, mappings, sequences, integers, and
    floats through `expected_value`, treats `None` as an exact warmup sentinel, and
    then compares nested structures key-by-key or item-by-item. Non-numeric leaf
    values fall back to equality.
    """
    expected = expected_value(expected)
    actual = expected_value(actual)
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, Mapping) or isinstance(actual, Mapping):
        if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
            return False
        if set(expected) != set(actual):
            return False
        return all(values_match(expected[key], actual[key], tolerance=tolerance) for key in sorted(expected))
    if isinstance(expected, (list, tuple)) or isinstance(actual, (list, tuple)):
        if not isinstance(expected, (list, tuple)) or not isinstance(actual, (list, tuple)):
            return False
        if len(expected) != len(actual):
            return False
        return all(
            values_match(expected_item, actual_item, tolerance=tolerance)
            for expected_item, actual_item in zip(expected, actual, strict=False)
        )
    try:
        return abs(float(expected) - float(actual)) <= tolerance
    except (TypeError, ValueError):
        return expected == actual


def expected_value(value: Any) -> Any:
    """Convert runtime outputs into JSON-stable values for fixture reports.

    Dataclass instances become dictionaries, mappings and sequences are normalized
    recursively, numeric values become floats, and `None` is preserved as the
    warmup sentinel. This makes expected, actual, and mismatch payloads comparable
    and serializable.
    """
    if value is None:
        return None
    if is_dataclass(value) and not isinstance(value, type):
        return {str(key): expected_value(inner) for key, inner in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): expected_value(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [expected_value(item) for item in value]
    if isinstance(value, (int, float)):
        return float(value)
    return value


def _lookahead_mismatches(indicator: Indicator, closes: Sequence[float], actual: Sequence[Any], *, tolerance: float) -> list[Mapping[str, Any]]:
    mismatches: list[Mapping[str, Any]] = []
    for idx in range(indicator.window - 1, len(closes)):
        prefix_bars = bars_from_ascending_closes(closes[: idx + 1])
        prefix_actual = list(indicator.compute_series(prefix_bars))
        if not prefix_actual:
            mismatches.append({"index": idx, "reason": "prefix produced no output"})
            continue
        prefix_value = prefix_actual[0]
        if not values_match(actual[idx], prefix_value, tolerance=tolerance):
            mismatches.append({"index": idx, "reason": "no-lookahead prefix mismatch", "expected": actual[idx], "actual": prefix_value})
    return mismatches
