"""Local worker entrypoint contracts for Console durable execution.

Subject: Environment bounds and explicit configuration requirements for worker startup.
Level: In-process entrypoint unit tests.
Collaborators: Worker helper functions and process environment; no pool or PostgreSQL.
Guarantees: Poll/lease settings stay bounded and a core YAML path is required by the runner composition.
Non-goals: Worker transaction behavior, BacktestRunner replay, and process supervision.
"""

from __future__ import annotations

import pytest

from trader_console_api.worker_entrypoint import _positive_env


def test_positive_environment_value_is_bounded(monkeypatch) -> None:
    """Accept a configured value inside the local worker safety bound."""
    monkeypatch.setenv("WORKER_TEST_VALUE", "30")
    assert _positive_env("WORKER_TEST_VALUE", 2, 60) == 30


def test_positive_environment_value_rejects_invalid_or_unbounded(monkeypatch) -> None:
    """Reject malformed and unbounded worker settings before opening a pool."""
    monkeypatch.setenv("WORKER_TEST_VALUE", "0")
    with pytest.raises(ValueError, match="between"):
        _positive_env("WORKER_TEST_VALUE", 2, 60)
    monkeypatch.setenv("WORKER_TEST_VALUE", "not-a-number")
    with pytest.raises(ValueError, match="integer"):
        _positive_env("WORKER_TEST_VALUE", 2, 60)
