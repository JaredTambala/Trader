"""Contracts for the optional Optuna optimisation-engine boundary.

Subject: Provider profile isolation, credential-neutral identity, and canonical-ledger reconciliation.
Level: Offline provider-adapter contract.
Collaborators: Optuna adapter profile objects and an in-memory study double.
Guarantees: Profiles require isolated Postgres configuration and detect provider-ledger divergence.
Non-goals: Connecting to Postgres, executing trials, tuning strategies, or qualifying Optuna performance.
"""

from __future__ import annotations

import pytest

from trader_research.infrastructure.providers.optuna import OptunaOptimizationEngine


def test_optuna_adapter_requires_isolated_postgres_and_reconciles_canonical_trials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optuna profiles require isolated Postgres identity and reconcile against Trader trials."""
    monkeypatch.setattr(
        "trader_research.infrastructure.providers.optuna.metadata.version",
        lambda package: "4.2.0" if package == "optuna" else "unknown",
    )
    configured = OptunaOptimizationEngine(
        storage_url="postgresql://trader_optuna_writer:secret@db-a:5432/optuna",
        schema_name="trader_optuna",
        role_name="trader_optuna_writer",
    ).profile()
    same_identity_new_secret = OptunaOptimizationEngine(
        storage_url="postgresql://trader_optuna_writer:changed@db-a:5432/optuna",
        schema_name="trader_optuna",
        role_name="trader_optuna_writer",
    ).profile()
    different_database = OptunaOptimizationEngine(
        storage_url="postgresql://trader_optuna_writer:secret@db-b:5432/optuna",
        schema_name="trader_optuna",
        role_name="trader_optuna_writer",
    ).profile()
    wrong_role = OptunaOptimizationEngine(
        storage_url="postgresql://trader_app:secret@db-a:5432/optuna",
        role_name="trader_optuna_writer",
    ).profile()
    public_schema = OptunaOptimizationEngine(
        storage_url="postgresql://trader_optuna_writer:secret@db-a:5432/optuna",
        schema_name="public",
        role_name="trader_optuna_writer",
    ).profile()
    non_postgres = OptunaOptimizationEngine(
        storage_url="sqlite:///optuna.db",
        schema_name="trader_optuna",
        role_name="trader_optuna_writer",
    ).profile()

    assert configured.available is True
    assert (
        configured.configuration_digest == same_identity_new_secret.configuration_digest
    )
    assert configured.configuration_digest != different_database.configuration_digest
    assert "dedicated writer role" in str(wrong_role.reason)
    assert "dedicated non-public schema" in str(public_schema.reason)
    assert "PostgreSQL" in str(non_postgres.reason)

    from trader_research.infrastructure.providers.optuna import _OptunaSession

    class _State:
        name = "COMPLETE"

    class _Trial:
        state = _State()

    class _Study:
        trials = [_Trial()]

    with pytest.raises(
        ValueError, match="operational state has 1 terminal trials but Trader has 0"
    ):
        _OptunaSession(_Study(), [], 1, [])
