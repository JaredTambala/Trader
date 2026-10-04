"""Subject: comparison view request and response contracts.

Level: Contract unit tests.
Collaborators: Pydantic validation only.
Guarantees: Invalid keys, duplicate selections, invalid references, and oversized
selections are rejected before repository code runs.
Non-goals: Persistence, evidence eligibility, HTTP status mapping, and UI behavior.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from trader_console_api.comparison_contracts import ComparisonViewDefinition


def test_definition_requires_reference_from_selected_runs() -> None:
    """A nonempty selection has an explicit reference run inside that selection."""
    with pytest.raises(ValidationError, match="reference_run_id"):
        ComparisonViewDefinition(
            name="invalid", run_ids=("run-a",), reference_run_id="other"
        )


def test_definition_rejects_duplicate_and_unknown_keys() -> None:
    """Metric and series choices are closed, unique transport values."""
    with pytest.raises(ValidationError, match="unique"):
        ComparisonViewDefinition(
            name="invalid", metric_keys=("strategy_sharpe", "strategy_sharpe")
        )
    with pytest.raises(ValidationError):
        ComparisonViewDefinition(name="invalid", series_keys=("made_up",))


def test_definition_rejects_more_than_twenty_runs() -> None:
    """The saved definition remains bounded independently of SQL pagination."""
    with pytest.raises(ValidationError):
        ComparisonViewDefinition(
            name="too many", run_ids=tuple(f"run-{index}" for index in range(21)),
            reference_run_id="run-0",
        )


def test_empty_definition_has_no_reference_but_still_has_display_choices() -> None:
    """An empty draft is valid for building a view before runs are selected."""
    definition = ComparisonViewDefinition(name="empty", run_ids=(), reference_run_id=None)
    assert definition.metric_keys == ("strategy_total_return",)
