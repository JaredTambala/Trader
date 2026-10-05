"""Contract migration visibility without installation or database writes.

Subject: Consumer impact, release map, and status CLI safety.
Level: Unit and in-process CLI contract.
Collaborators: Real catalog/compatibility logic with recording connections.
Guarantees: Only affected consumers need upgrades; status is bounded and secret-safe.
Non-goals: Database enforcement, dataset correctness, or deployment discovery.
"""

from contextlib import nullcontext
import json
from types import SimpleNamespace

import psycopg
import pytest

from trader.event_store import console_contract_status as status
from trader.event_store import console_read_contract as contract


class Connection:
    def __init__(self, version=(1, 1), missing=()):
        self.version = version
        self.missing = missing
        self.info = SimpleNamespace(host="127.0.0.1", port=55432, dbname="test_console")
        self.queries = []

    def execute(self, query, parameters=None):
        self.queries.append((query, parameters))
        if "information_schema.columns" in query:
            columns = {"contract_versions": contract.CONSOLE_READ_CONTRACT_COLUMNS,
                       **contract.CONSOLE_READ_COLUMNS}
            if self.version == (1, 1):
                removed = {name for release in status.RELEASES[1:] for name in release.relations}
                columns = {name: cols for name, cols in columns.items() if name not in removed}
            elif self.version == (2, 1):
                columns = {name: cols for name, cols in columns.items()
                           if name not in status.RELEASES[2].relations}
            rows = [(name, column) for name, cols in columns.items() if name not in self.missing for column in cols]
            return SimpleNamespace(fetchall=lambda: rows)
        if "to_regclass" in query:
            return SimpleNamespace(fetchone=lambda: (None if "contract_versions" in self.missing else "present",))
        return SimpleNamespace(fetchone=lambda: self.version)


def test_release_inventory_covers_every_view_and_current_version():
    """New views must be attributed to a release before the status map admits them."""
    relations = [name for release in status.RELEASES for name in release.relations]
    assert set(relations) == set(contract.CONSOLE_READ_COLUMNS)
    assert [release.version for release in status.RELEASES] == list(range(1, contract.CONSOLE_READ_CONTRACT_VERSION + 1))
    assert contract.CONSOLE_READ_MINIMUM_CONSUMER_VERSION == 1
    for consumer in status.CONSUMERS:
        assert set(consumer.relations) <= set(contract.CONSOLE_READ_COLUMNS)


@pytest.mark.parametrize(("version", "missing", "states"), [
    ((1, 1), (), ("catalog_mismatch",)),
    ((2, 1), (), ("catalog_mismatch",)),
    ((2, 1), ("backtest_trades",), ("catalog_mismatch",)),
    ((2, 1), ("stock_bars",), ("catalog_mismatch",)),
    ((3, 1), (), ("ready",)),
    ((3, 3), (), ("consumer_upgrade_required",)),
    ((2, 3), (), ("metadata_invalid",)),
    ((0, 0), (), ("metadata_invalid",)),
    (None, ("contract_versions",), ("upgrade_required",)),
])
def test_consumer_admission_distinguishes_upgrade_drift_and_compatibility(version, missing, states):
    """One consumer's missing relations must not force migrations on unrelated consumers."""
    inspection = contract.inspect_console_read_contract(Connection(version, missing))
    assert tuple(status.assess_consumer(inspection, item).state for item in status.CONSUMERS) == states


def test_api_catalog_damage_is_reported_without_recommending_a_downgrade():
    """A missing view required by a current API resource fails admission without downgrade advice."""
    inspection = contract.inspect_console_read_contract(Connection((5, 1), ("backtest_trades",)))
    assessment = status.assess_consumer(inspection, status.CONSUMERS[0])
    assert assessment.state == "catalog_mismatch"
    assert "newer producer tooling" not in assessment.action


def test_offline_cli_explains_owners_without_connecting(monkeypatch, capsys):
    """Offline release/consumer discovery must work without credentials or a database."""
    monkeypatch.setattr(status.psycopg, "connect", lambda *args, **kwargs: pytest.fail("offline connection"))
    assert contract.main(["status", "--offline", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["database_checked"] is False
    assert "installed_version" not in report
    assert [(item["name"], item["required_version"]) for item in report["requirements"]] == [("console-api", 1)]


@pytest.mark.parametrize(("consumer", "exit_code"), [(None, 0), ("console-api", 0)])
def test_status_reads_only_and_reports_target_without_credentials(monkeypatch, capsys, consumer, exit_code):
    """Status uses explicit bounded read-only connections and returns per-consumer admission."""
    connection = Connection((5, 1))
    calls = []
    def connect(dsn, **kwargs):
        calls.append((dsn, kwargs))
        return nullcontext(connection)
    monkeypatch.setattr(status.psycopg, "connect", connect)
    monkeypatch.setenv("TRADER_CONSOLE_DATABASE_URL", "postgresql://user:secret@127.0.0.1/test_console")
    assert status.run_status(consumer=consumer, json_output=True) == exit_code
    output = capsys.readouterr().out
    report = json.loads(output)
    assert "secret" not in output
    assert report["database"]["name"] == "test_console"
    assert report["installed_version"] == 5
    assert report["pending_versions"] == [6, 7, 8, 9, 10, 11]
    assert calls[0][1] == {"connect_timeout": 5, "options": "-c default_transaction_read_only=on -c statement_timeout=5000"}
    assert all(query.lstrip().startswith("SELECT") for query, _ in connection.queries)
    assert any(params == ["trader_console"] for _, params in connection.queries)


def test_missing_config_never_falls_back_to_general_database_credentials(monkeypatch, capsys):
    """Unset inspection DSNs produce an actionable failure, regardless of ambient PG credentials."""
    monkeypatch.delenv("TRADER_CONSOLE_DATABASE_URL", raising=False)
    monkeypatch.setenv("PG_PASSWORD", "not-authorized")
    monkeypatch.setattr(status.psycopg, "connect", lambda *args, **kwargs: pytest.fail("fallback connection"))
    assert contract.main(["status", "--json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert "Set TRADER_CONSOLE_DATABASE_URL" in report["error"]
    assert report["database_checked"] is False


def test_connection_failure_is_unknown_not_a_pending_migration(monkeypatch, capsys):
    """Connection failures must not leak exception secrets or fabricate installed state."""
    monkeypatch.setenv("TRADER_CONSOLE_DATABASE_URL", "postgresql://user:secret@localhost/test")
    def unavailable(*args, **kwargs):
        raise psycopg.OperationalError("password secret connection rejected")
    monkeypatch.setattr(status.psycopg, "connect", unavailable)
    assert status.run_status(json_output=True) == 2
    output = capsys.readouterr().out
    assert "secret" not in output
    report = json.loads(output)
    assert "requirements are unknown" in report["error"]
    assert "installed_version" not in report


def test_human_status_lists_manual_action_and_pending_view_names(monkeypatch, capsys):
    """The plain report names impacted views and a safe manual installer next step."""
    monkeypatch.setenv("TRADER_CONSOLE_DATABASE_URL", "postgresql://unused")
    monkeypatch.setattr(status.psycopg, "connect", lambda *args, **kwargs: nullcontext(Connection((1, 1), ("stock_bars",))))
    assert contract.main(["status"]) == 1
    output = capsys.readouterr().out
    assert "console-api: requires 1 — catalog_mismatch" in output
    assert "backtest_equity_curve" in output
    assert "TRADER_CONSOLE_MIGRATION_DSN" in output


def test_partial_metadata_does_not_issue_an_invalid_version_query():
    """Broken metadata catalog is diagnosed before querying absent version columns."""
    connection = Connection(missing=("contract_versions",))
    inspection = contract.inspect_console_read_contract(connection)
    assert "console_read_catalog_mismatch:contract_versions" in inspection.issues
    assert not any("WHERE contract_name" in query for query, _ in connection.queries)
