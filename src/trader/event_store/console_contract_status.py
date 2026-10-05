"""Explain Console contract releases and consumer requirements without migrating.

This operator surface inspects only compatibility metadata and catalog columns.
It never installs views, grants access, enumerates deployments, or reads trading
rows. Consumer declarations describe code requirements, not running services.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from typing import Final

import psycopg

from .console_read_contract import (
    CONSOLE_READ_CONTRACT,
    CONSOLE_READ_CONTRACT_VERSION,
    ConsoleReadInspection,
    assess_console_read_compatibility,
    inspect_console_read_contract,
)


@dataclass(frozen=True)
class ContractRelease:
    """Describe a recorded release's affected relations and source-table owners."""

    version: int
    summary: str
    relations: tuple[str, ...]
    source_tables: tuple[str, ...]


RELEASES: Final = (
    ContractRelease(
        1,
        "Initial Console views; core source tables unchanged.",
        ("sessions", "runs", "cycles", "stock_bars", "crypto_bars", "signals",
         "indicators", "predictions", "orders", "fills", "positions"),
        ("trading_sessions", "runs", "run_events", "stock_bar_events",
         "crypto_bar_events", "signal_events", "indicator_events", "prediction_events",
         "order_events", "fill_events", "position_snapshots"),
    ),
    ContractRelease(
        2,
        "Add typed backtest evidence views; existing views and core source tables unchanged.",
        ("backtest_performance", "backtest_exposure",
         "backtest_equity_curve", "backtest_trades", "backtest_positions",
         "backtest_assumptions", "backtest_warnings", "backtest_provenance"),
        ("experiment_runs", "runs", "metrics_snapshots"),
    ),
    ContractRelease(
        3,
        "Add lifecycle identity projections and backtest evidence coverage; legacy rows remain readable as unknown.",
        ("signal_lifecycle", "order_lifecycle", "fill_lifecycle", "backtest_evidence_coverage"),
        ("signal_events", "order_events", "fill_events", "metrics_snapshots"),
    ),
    ContractRelease(
        4,
        "Add typed backtest comparison scope and explicit strategy variant fingerprints; legacy snapshots remain unavailable for comparison.",
        ("backtest_scope",),
        ("metrics_snapshots", "experiment_runs"),
    ),
    ContractRelease(
        5,
        "Add normalized comparison curves and compatibility-gated cohort rows; legacy snapshots remain unavailable for comparison.",
        ("backtest_comparison_runs", "backtest_comparison_curves"),
        ("metrics_snapshots", "experiment_runs"),
    ),
    ContractRelease(
        6,
        "Add producer-declared indicator series and decision-cycle-bound signal markers for backtest review.",
        ("indicator_series", "signal_markers"),
        ("indicator_events", "signal_events", "run_events", "experiment_runs", "metrics_snapshots"),
    ),
    ContractRelease(
        7,
        "Include standalone BacktestRunner runs in the published backtest review projections.",
        ("backtest_runs",),
        ("runs", "metrics_snapshots", "experiment_runs"),
    ),
    ContractRelease(
        8,
        "Derive backtest evidence, cash, positions, equity, and performance from persisted runtime evidence; metrics snapshots are no longer a Console read dependency.",
        ("backtest_scope", "backtest_performance", "backtest_exposure", "backtest_equity_curve",
         "backtest_comparison_curves", "backtest_comparison_runs", "backtest_trades", "backtest_positions",
         "backtest_assumptions", "backtest_warnings", "backtest_provenance", "backtest_evidence_coverage"),
        ("runs", "run_events", "stock_bar_events", "crypto_bar_events", "order_events", "fill_events", "position_snapshots"),
    ),
    ContractRelease(
        9,
        "Add typed risk composition, summary, and ordered per-manager decision evidence.",
        ("risk_composition", "risk_summary", "risk_decisions"),
        ("risk_compositions", "risk_decisions", "runs"),
    ),
    ContractRelease(
        10,
        "Publish exact Data manifest and quality evidence plus Evaluation, multiple-testing, and Adversarial/robustness review evidence with explicit qualification, claim, and limitation fields.",
        ("data_scope_evidence", "research_review_evidence"),
        ("research_artifacts",),
    ),
    ContractRelease(
        11,
        "Carry Console data-scope identity, benchmark, assumptions, and persisted backtest warnings into standalone review projections.",
        ("backtest_scope", "backtest_assumptions", "backtest_performance", "backtest_warnings"),
        ("runs", "metrics_snapshots", "run_events"),
    ),
)


@dataclass(frozen=True)
class ContractConsumer:
    """Declare one consumer's required version, relations and owning source path."""

    name: str
    required_version: int
    relations: tuple[str, ...]
    owner: str


_CONSOLE_API_RELATIONS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        relation
        for release in RELEASES
        for relation in release.relations
    )
)

CONSUMERS: Final = (
    ContractConsumer(
        "console-api",
        1,
        _CONSOLE_API_RELATIONS,
        "src/trader_console_api/repositories/schema_compatibility.py",
    ),
)


@dataclass(frozen=True)
class ConsumerStatus:
    """Report schema admission and a manual next action for one consumer."""

    name: str
    required_version: int
    state: str
    issues: tuple[str, ...]
    action: str


_INSTALL_ACTION: Final = (
    "Confirm the target database; set TRADER_CONSOLE_MIGRATION_DSN to its migration-owner DSN, "
    "then run: uv run trader-console-read-contract install. Re-run status afterwards. "
    "The installer does not grant new views to readers or mutate external consumer assets."
)


def assess_consumer(inspection: ConsoleReadInspection, consumer: ContractConsumer) -> ConsumerStatus:
    """Assess only the metadata and relations this consumer actually requires."""
    version = inspection.compatibility
    compatibility = assess_console_read_compatibility(
        installed_version=version.installed_version,
        minimum_consumer_version=version.minimum_consumer_version,
        consumer_version=consumer.required_version,
    )
    required = {"contract_versions", *consumer.relations}
    issues = tuple(issue for issue in inspection.issues if issue.split(":", 1)[-1] in required)
    if compatibility.reason:
        issues = (compatibility.reason, *issues)
    if not issues:
        state, action = "ready", "No migration required for this consumer."
    elif compatibility.reason == "console_consumer_too_old":
        state, action = "consumer_upgrade_required", "Upgrade the consumer; do not downgrade the database."
    elif compatibility.reason == "console_read_contract_invalid":
        state, action = "metadata_invalid", "Have the migration owner inspect invalid compatibility metadata."
    elif compatibility.reason in {"console_read_contract_missing", "console_read_contract_too_old"}:
        state, action = "upgrade_required", _INSTALL_ACTION
    else:
        state = "catalog_mismatch"
        action = "Required columns are missing, changed, or not visible to this connection. Check grants and catalog. "
        if (version.installed_version or 0) > CONSOLE_READ_CONTRACT_VERSION:
            action += "Use the matching newer producer tooling; this installer must not downgrade it."
        else:
            action += "If damaged, use the migration owner to review/repair the contract. " + _INSTALL_ACTION
    return ConsumerStatus(consumer.name, consumer.required_version, state, issues, action)


def run_status(*, offline: bool = False, consumer: str | None = None, json_output: bool = False) -> int:
    """Print a read-only migration report, or an offline requirement map.

    Args:
        offline: Do not resolve credentials or connect; report known requirements only.
        consumer: Restrict admission checks to one declared consumer, or check all.
        json_output: Emit structured JSON rather than human-readable text.

    Returns:
        Zero for admitted selected consumers or offline output, one for schema
        action required, and two when configuration/connection prevents inspection.

    Raises:
        ValueError: If the selected consumer is unknown.
    """
    selected = tuple(item for item in CONSUMERS if consumer is None or item.name == consumer)
    if not selected:
        raise ValueError(f"Unknown Console contract consumer: {consumer}")
    report: dict[str, object] = {
        "contract": CONSOLE_READ_CONTRACT,
        "latest_version": CONSOLE_READ_CONTRACT_VERSION,
        "database_checked": False,
        "releases": [asdict(release) for release in RELEASES],
        "requirements": [asdict(item) for item in selected],
    }
    if offline:
        _print_report(report, json_output)
        return 0
    dsn = os.environ.get("TRADER_CONSOLE_DATABASE_URL")
    if not dsn:
        report["error"] = "Set TRADER_CONSOLE_DATABASE_URL explicitly; no PG_* fallback is used."
        _print_report(report, json_output)
        return 2
    try:
        with psycopg.connect(
            dsn, connect_timeout=5,
            options="-c default_transaction_read_only=on -c statement_timeout=5000",
        ) as connection:
            report["database"] = {"host": connection.info.host, "port": connection.info.port,
                                  "name": connection.info.dbname}
            inspection = inspect_console_read_contract(connection)
    except psycopg.Error:
        # Adapter exception text may contain credentials. Do not print it or the DSN.
        report["error"] = (
            "Database inspection unavailable. Check connection, credentials, catalog access and timeout; "
            "migration requirements are unknown. No changes made."
        )
        _print_report(report, json_output)
        return 2
    version = inspection.compatibility
    statuses = tuple(assess_consumer(inspection, item) for item in selected)
    report.update({
        "database_checked": True,
        "installed_version": version.installed_version,
        "minimum_consumer_version": version.minimum_consumer_version,
        "pending_versions": None if version.installed_version is None else [
            release.version for release in RELEASES if release.version > version.installed_version
        ],
        "consumers": [asdict(status) for status in statuses],
    })
    _print_report(report, json_output)
    return int(any(status.state != "ready" for status in statuses))


def _print_report(report: dict[str, object], json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, indent=2))
        return
    print(f"Console SQL contract — latest known version: {report['latest_version']}")
    print("Scope: column names/order and metadata only; not view SQL, data quality, or deployed-service discovery.")
    if "database" in report:
        database = report["database"]
        assert isinstance(database, dict)
        print(f"Database: {database['host']}:{database['port']}/{database['name']}")
    if "error" in report:
        print(report["error"])
        return
    if report["database_checked"]:
        print(f"Installed: {report['installed_version']} | oldest admitted consumer: {report['minimum_consumer_version']}")
        print(f"Pending known versions: {report['pending_versions']}")
        if report["installed_version"] is not None and report["installed_version"] > CONSOLE_READ_CONTRACT_VERSION:
            print("Newer than this checkout: do not run this installer; obtain matching producer tooling.")
        for item in report["consumers"]:
            print(f"{item['name']}: requires {item['required_version']} — {item['state']}")
            if item["issues"]:
                print("  Issues: " + ", ".join(item["issues"]))
            print("  " + item["action"])
    else:
        print("Offline requirements only; no database inspected.")
    for release in report["releases"]:
        print(f"Release {release['version']}: {release['summary']}")
        print("  Views: " + ", ".join(release["relations"]))
        print("  Sources: " + ", ".join(release["source_tables"]))
    for requirement in report["requirements"]:
        print(f"Requirement {requirement['name']}: version {requirement['required_version']} ({requirement['owner']})")
