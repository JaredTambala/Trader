"""Compare persisted research experiment results."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv

from trader.config import build_config, load_yaml_config, resolve_log_level
from trader.data import build_event_store
from trader_research.research import list_experiment_comparison


logger = logging.getLogger(__name__)


def main() -> None:
    args = _parse_args()
    load_dotenv(".env")
    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    event_store = build_event_store(build_config(config_data))
    try:
        payload = list_experiment_comparison(
            event_store,
            experiment_name=args.experiment,
            limit=args.limit,
        )
    finally:
        event_store.close()
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return
    _print_table(payload["rows"])
    for warning in payload["warnings"]:
        print(f"WARNING: {warning}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare research experiment results.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    parser.add_argument("--experiment", required=True, help="Experiment name.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of runs to compare.")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    return parser.parse_args()


def _configure_logging(level_name: str | None = None) -> None:
    level_name = (level_name or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _print_table(rows: Sequence[Mapping[str, Any]]) -> None:
    headers = [
        "status",
        "run_id",
        "strategy",
        "return",
        "sharpe",
        "drawdown",
        "turnover",
        "fees",
        "slippage",
        "alpha",
        "beta",
        "warnings",
        "artifact_dir",
    ]
    table_rows = [
        [
            str(row.get("status") or ""),
            str(row.get("run_id") or ""),
            str(row.get("strategy_id") or ""),
            _fmt(row.get("total_return")),
            _fmt(row.get("sharpe")),
            _fmt(row.get("max_drawdown")),
            _fmt(row.get("turnover")),
            _fmt(row.get("fees")),
            _fmt(row.get("slippage")),
            _fmt(row.get("alpha")),
            _fmt(row.get("beta")),
            str(row.get("warnings_count") or 0),
            str(row.get("artifact_dir") or ""),
        ]
        for row in rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in table_rows)) if table_rows else len(headers[index])
        for index in range(len(headers))
    ]
    print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in table_rows:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _fmt(value: object) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError):
        return str(value)


if __name__ == "__main__":
    main()
