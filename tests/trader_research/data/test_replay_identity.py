"""Unit contracts for qualified replay-data identity.

Subject: Deterministic bar-content identity and source semantics.
Level: In-process unit.
Collaborators: Typed ``BarRecord`` fixtures and Data identity helpers; no
database, provider, or runtime execution.
Guarantees: Equivalent row order is stable, while changed/partial rows and
source drift fail closed with actionable mismatch codes.
Non-goals: Provider loading, PostgreSQL persistence, or strategy performance.
"""

from datetime import UTC, datetime

import pytest

from trader.market_data.query_domain import BarRecord
from trader_research.data import (
    ReplayDataIdentityMismatch,
    build_replay_data_identity,
    validate_replay_data_identity,
)


BASE_TS = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)


def _records(*, source: str = "alpaca") -> tuple[BarRecord, ...]:
    return (
        BarRecord("AAPL", "1Min", BASE_TS, 100.0, 101.0, 99.0, 100.5, 10.0, None, None, source),
        BarRecord("AAPL", "1Min", BASE_TS.replace(minute=1), 100.5, 102.0, 100.0, 101.0, 11.0, None, None, source),
    )


def _identity(records: tuple[BarRecord, ...]) -> dict[str, object]:
    return build_replay_data_identity(
        records,
        provider="alpaca",
        source_policy="observed",
        asset_class="stocks",
        symbols=("AAPL",),
        timeframe="1Min",
        inspected_at=BASE_TS,
    ).to_dict()


def test_replay_identity_is_deterministic_and_order_independent() -> None:
    """The same qualified rows produce one content digest regardless of query order."""
    first = _identity(_records())
    second = _identity(tuple(reversed(_records())))

    assert first["algorithm"] == "sha256:bar-content-v1"
    assert first["content_digest"] == second["content_digest"]
    assert first["row_count"] == 2
    assert first["source_semantics"] == second["source_semantics"]


def test_replay_identity_accepts_unchanged_rows() -> None:
    """A re-read of the qualified rows returns an execution identity."""
    expected = _identity(_records())

    observed = validate_replay_data_identity(
        expected,
        _records(),
        provider="alpaca",
        source_policy="observed",
        asset_class="stocks",
        symbols=("AAPL",),
        timeframe="1Min",
        inspected_at=BASE_TS.replace(hour=13),
    )

    assert observed.content_digest == expected["content_digest"]
    assert observed.inspected_at.hour == 13


@pytest.mark.parametrize(
    ("records", "code"),
    [
        (tuple(record for index, record in enumerate(_records()) if index == 0), "bar_content_mismatch"),
        (
            (
                BarRecord("AAPL", "1Min", BASE_TS, 100.0, 101.0, 99.0, 100.75, 10.0, None, None, "alpaca"),
                _records()[1],
            ),
            "bar_content_mismatch",
        ),
        (_records(source="polygon"), "source_semantics_mismatch"),
    ],
)
def test_replay_identity_fails_closed_for_changed_partial_or_source_rows(
    records: tuple[BarRecord, ...],
    code: str,
) -> None:
    """Any post-inspection mutation or source substitution blocks replay."""
    expected = _identity(_records())

    with pytest.raises(ReplayDataIdentityMismatch) as exc_info:
        validate_replay_data_identity(
            expected,
            records,
            provider="alpaca",
            source_policy="observed",
            asset_class="stocks",
            symbols=("AAPL",),
            timeframe="1Min",
        )

    assert exc_info.value.code == code
