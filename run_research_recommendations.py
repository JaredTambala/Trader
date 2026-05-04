"""AI/tool-facing research recommendation entrypoint."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from trader.config import build_config, load_yaml_config, resolve_log_level
from trader.data import build_event_store
from trader.research import experiment_slug, list_experiment_comparison
from trader.tools.contracts import SideEffect, envelope_json, error_envelope, success_envelope, write_json_artifact
from trader.tools.recommendations import RecommendationSettings, build_recommendations_from_files


logger = logging.getLogger(__name__)


def main() -> None:
    """Build recommendations from persisted research comparison rows."""
    load_dotenv(".env")
    args = _parse_args()
    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    try:
        payload, output_path, warnings = _run(args, config_data)
        envelope = success_envelope(
            command="research_recommendations",
            side_effect=SideEffect.READ_ONLY,
            data=payload,
            artifacts={"recommendations": str(output_path)},
            warnings=warnings,
        )
    except Exception as exc:
        if args.json:
            print(
                envelope_json(
                    error_envelope(
                        command="research_recommendations",
                        side_effect=SideEffect.READ_ONLY,
                        message=str(exc),
                    )
                )
            )
            raise SystemExit(1) from exc
        raise
    if args.json:
        print(envelope_json(envelope))
        return
    print(f"recommendations path={output_path} recommendation_id={payload.get('recommendation_id')}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recommend research candidates for human review.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    parser.add_argument("--experiment", required=True, help="Experiment name to compare.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum experiment runs to compare.")
    parser.add_argument("--data-quality-report", help="Optional data-quality report JSON.")
    parser.add_argument("--operator-context", action="append", default=[], help="Optional Sprint 4 operator JSON path.")
    parser.add_argument("--prior-artifact", action="append", default=[], help="Optional prior strategy/result artifact path.")
    parser.add_argument("--output", help="Recommendation artifact output path.")
    parser.add_argument("--allow-missing-data-quality", action="store_true")
    parser.add_argument("--allow-data-quality-gaps", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit a stable tool JSON envelope.")
    return parser.parse_args()


def _run(args: argparse.Namespace, config_data: dict[str, object]) -> tuple[dict[str, object], Path, tuple[str, ...]]:
    event_store = build_event_store(build_config(config_data))
    try:
        comparison = list_experiment_comparison(
            event_store,
            experiment_name=args.experiment,
            limit=args.limit,
        )
    finally:
        event_store.close()
    data_quality_path = args.data_quality_report or _default_data_quality_path(args.experiment)
    output_path = Path(args.output) if args.output else Path("artifacts/recommendations") / f"{experiment_slug(args.experiment)}.json"
    settings = RecommendationSettings(
        allow_missing_data_quality=bool(args.allow_missing_data_quality),
        allow_data_quality_gaps=bool(args.allow_data_quality_gaps),
    )
    result = build_recommendations_from_files(
        comparison,
        experiment_name=str(args.experiment),
        data_quality_path=data_quality_path if data_quality_path and Path(data_quality_path).exists() else None,
        operator_context_paths=tuple(args.operator_context),
        prior_artifact_paths=tuple(args.prior_artifact),
        settings=settings,
    )
    write_json_artifact(result.payload, output_path)
    return dict(result.payload), output_path, tuple(result.warnings)


def _default_data_quality_path(experiment_name: str) -> str | None:
    candidate = Path("artifacts/discovery") / experiment_slug(experiment_name) / "data_quality.json"
    return str(candidate) if candidate.exists() else None


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
