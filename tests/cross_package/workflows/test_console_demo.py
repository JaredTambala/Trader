"""Contracts for explicit demo composition across core schema and Console API.

Subject: Dedicated fixture identity and bootstrap inputs.
Level: Offline composition contract.
Collaborators: Real configuration builders; environment overrides only, no database.
Guarantees: Demo cannot inherit a trading DSN or account identity and ports are bounded.
Non-goals: PostgreSQL readiness and browser behavior, covered by the Docker workflow.
"""

from psycopg.conninfo import conninfo_to_dict
import pytest

from examples.console_demo.runtime import api_settings, demo_dsn


def test_demo_ignores_general_database_and_account_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ignore ambient trading settings so the demo always has an explicit synthetic identity."""
    monkeypatch.setenv("PG_DB", "trading")
    monkeypatch.setenv("TRADER_CONSOLE_DATABASE_URL", "postgresql://production/real")
    monkeypatch.setenv("TRADER_CONSOLE_SCOPE_ENVIRONMENT", "paper")
    settings = api_settings()
    connection = conninfo_to_dict(settings.database_url.get_secret_value())
    assert connection["dbname"] == "trader_console_demo"
    assert connection["host"] == "127.0.0.1"
    assert connection["port"] == "55432"
    assert settings.scope.environment == "synthetic_demo"
    assert settings.scope.scope_id == "console-demo"
    assert settings.scope.broker_account_display_label is None


@pytest.mark.parametrize("port", [0, 1023, 65536, True])
def test_demo_rejects_invalid_port_before_connection(port: int) -> None:
    """Reject unsafe port values without contacting any database."""
    with pytest.raises(ValueError, match="demo database port"):
        demo_dsn(port)
