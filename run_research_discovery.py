"""AI/tool-facing research discovery entrypoint."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from dotenv import load_dotenv

from trader.config import load_yaml_config, resolve_log_level
from trader.tools.contracts import SideEffect, envelope_json, error_envelope
from trader.tools.discovery import DiscoveryRequest, run_discovery


logger = logging.getLogger(__name__)


def main() -> None:
    """Run a research discovery workflow."""
    load_dotenv(".env")
    args = _parse_args()
    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    try:
        request = _request_from_args(config_data, args)
        envelope = run_discovery(config_data, request)
    except Exception as exc:
        if args.json:
            print(
                envelope_json(
                    error_envelope(
                        command="research_discovery",
                        side_effect=SideEffect.READ_ONLY if args.dry_run or args.data_mode == "plan" else SideEffect.LOCAL_MUTATING,
                        message=str(exc),
                    )
                )
            )
            raise SystemExit(1) from exc
        raise
    if args.json:
        print(envelope_json(envelope))
        return
    print(f"research_discovery ok={envelope.ok} artifacts={dict(envelope.artifacts)}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AI/tool research discovery.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    parser.add_argument("--symbols", help="Comma-separated symbols to research.")
    parser.add_argument("--asset-class", help="Asset class, e.g. stocks or crypto.")
    parser.add_argument("--timeframe", help="Timeframe, e.g. 1Min.")
    parser.add_argument("--since", help="Relative data window, e.g. 30d.")
    parser.add_argument("--start", help="Explicit data/backtest window start.")
    parser.add_argument("--end", help="Explicit data/backtest window end.")
    parser.add_argument("--strategies", help="Comma-separated strategy families.")
    parser.add_argument("--max-runs", type=int, default=25)
    parser.add_argument("--cost-profile", choices=("default", "conservative"), default="conservative")
    parser.add_argument("--risk-profile", default="default")
    parser.add_argument("--data-mode", choices=("plan", "backfill", "existing", "sample"), default="existing")
    parser.add_argument("--operator-context", action="append", default=[])
    parser.add_argument("--prior-artifact", action="append", default=[])
    parser.add_argument("--output-dir", default="artifacts/discovery")
    parser.add_argument("--experiment", default="demo_discovery")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit a stable tool JSON envelope.")
    return parser.parse_args()


def _request_from_args(config_data: Mapping[str, Any], args: argparse.Namespace) -> DiscoveryRequest:
    market_data = _mapping(config_data.get("market_data"))
    strategy = _mapping(config_data.get("strategy"))
    backtest = _mapping(config_data.get("backtest"))
    symbols = _parse_csv(args.symbols) or _parse_symbols(market_data.get("symbols")) or _parse_symbols(backtest.get("symbols"))
    asset_class = str(args.asset_class or market_data.get("asset_class") or backtest.get("asset_class") or "stocks")
    timeframe = str(args.timeframe or backtest.get("timeframe") or strategy.get("timeframe") or "1Min")
    strategy_families = _parse_csv(args.strategies) or (str(strategy.get("id", "trend_following")),)
    return DiscoveryRequest(
        symbols=tuple(symbols),
        asset_class=asset_class,
        timeframe=timeframe,
        strategy_families=tuple(strategy_families),
        data_mode=str(args.data_mode),
        since=args.since,
        start=_parse_datetime(args.start),
        end=_parse_datetime(args.end),
        max_runs=int(args.max_runs),
        cost_profile=str(args.cost_profile),
        risk_profile=str(args.risk_profile),
        output_dir=str(args.output_dir),
        experiment_name=str(args.experiment),
        dry_run=bool(args.dry_run),
        operator_context_paths=tuple(str(path) for path in args.operator_context),
        prior_artifact_paths=tuple(str(path) for path in args.prior_artifact),
    )


def _parse_csv(value: object) -> tuple[str, ...]:
    if value is None:
        return tuple()
    return tuple(item.strip() for item in str(value).split(",") if item.strip())


def _parse_symbols(value: object) -> tuple[str, ...]:
    if value is None:
        return tuple()
    if isinstance(value, str):
        return tuple(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(symbol).strip().upper() for symbol in value if str(symbol).strip())
    raise ValueError("symbols must be a comma-separated string or list")


def _parse_datetime(value: object | None) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _configure_logging(level_name: str | None = None) -> None:
    level_name = (level_name or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Logging configured level=%s", level_name)


if __name__ == "__main__":
    main()
