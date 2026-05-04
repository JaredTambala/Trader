"""Build a dry-run paper-promotion packet from a recommendation."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from dotenv import load_dotenv

from trader.config import load_yaml_config, resolve_log_level
from trader.tools.contracts import SideEffect, envelope_json, error_envelope, success_envelope
from trader.tools.promotion import build_promotion_packet


logger = logging.getLogger(__name__)


def main() -> None:
    """Prepare a dry-run paper-promotion packet."""
    load_dotenv(".env")
    args = _parse_args()
    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    try:
        if not args.dry_run:
            raise ValueError("Sprint 5 promotion packet generation only supports --dry-run")
        recommendation_payload = _load_json_mapping(args.recommendation_json)
        packet = build_promotion_packet(
            base_config_data=config_data,
            recommendation_payload=recommendation_payload,
            recommendation_id=str(args.recommendation_id),
            output_root=args.output_dir,
            operator_context_paths=tuple(args.operator_context),
        )
        envelope = success_envelope(
            command="prepare_paper_promotion",
            side_effect=SideEffect.LOCAL_MUTATING,
            data=packet,
            artifacts={
                "promotion_packet": packet.get("promotion_packet"),
                "proposed_config": packet.get("proposed_config"),
                "strategy_artifact": packet.get("strategy_artifact"),
                "dry_run_validation": packet.get("dry_run_validation"),
            },
        )
    except Exception as exc:
        if args.json:
            print(
                envelope_json(
                    error_envelope(
                        command="prepare_paper_promotion",
                        side_effect=SideEffect.LOCAL_MUTATING,
                        message=str(exc),
                    )
                )
            )
            raise SystemExit(1) from exc
        raise
    if args.json:
        print(envelope_json(envelope))
        return
    print(f"promotion_packet={packet.get('promotion_packet')} promotion_ready={packet.get('promotion_ready')}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a dry-run Alpaca paper-promotion packet.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    parser.add_argument("--recommendation-json", required=True, help="Recommendation JSON artifact path.")
    parser.add_argument("--recommendation-id", required=True, help="Candidate recommendation ID.")
    parser.add_argument("--operator-context", action="append", default=[], help="Optional Sprint 4 operator JSON path.")
    parser.add_argument("--output-dir", default="artifacts/promotions", help="Promotion artifact root.")
    parser.add_argument("--dry-run", action="store_true", help="Required; never starts paper trading.")
    parser.add_argument("--json", action="store_true", help="Emit a stable tool JSON envelope.")
    return parser.parse_args()


def _load_json_mapping(path: str | Path) -> dict[str, object]:
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return parsed


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
