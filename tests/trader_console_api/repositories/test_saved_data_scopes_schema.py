"""Subject: explicit saved data scope storage installer contract.

Level: Installer SQL contract test.
Collaborators: SQL constants only; no database server.
Guarantees: the additive table has the exact columns and hard-cutover evidence states.
Non-goals: executing DDL or testing PostgreSQL locking behavior.
"""

from trader_console_api.repositories.saved_data_scopes_schema import COLUMNS, INSTALL_SQL


def test_saved_scope_schema_declares_exact_identity_and_evidence_columns() -> None:
    """The installer stores one immutable identity and mutable qualification state."""
    assert "CREATE TABLE IF NOT EXISTS console_app.saved_data_scopes" in INSTALL_SQL
    assert "UNIQUE (scope_id, fingerprint)" in INSTALL_SQL
    assert "UNIQUE (scope_id, idempotency_key)" in INSTALL_SQL
    assert "evidence_status IN ('active', 'stale', 'unavailable')" in INSTALL_SQL
    assert COLUMNS["scope"] == "jsonb"
    assert COLUMNS["saved_scope_id"] == "uuid"
