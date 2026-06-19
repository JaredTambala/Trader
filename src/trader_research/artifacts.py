"""Artifact loading and validation for AI/tool workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
import csv
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class LoadedArtifacts:
    """Container for partially loaded strategy artifacts and recoverable warnings.

    Artifact loading is intentionally best-effort for research tools: callers can
    still rank recommendations or build promotion metadata when optional context
    files are missing, malformed, or unsupported. The `artifacts` mapping stores
    parsed JSON payloads and CSV summaries keyed by file stem, while `warnings`
    carries human-readable diagnostics that should be surfaced in tool envelopes.
    """

    artifacts: Mapping[str, Any]
    warnings: Sequence[str] = field(default_factory=tuple)


def load_json_file(path: str | Path) -> Mapping[str, Any]:
    """Read a JSON artifact and enforce the mapping contract expected by tools.

    Research artifacts are passed around as structured objects, so arrays or scalar
    JSON documents are rejected at the boundary instead of being handled later by
    downstream ranking, promotion, or metadata builders. File and JSON decoding
    errors are deliberately left to the caller so batch loaders can decide whether
    to fail hard or continue with warnings.
    """
    artifact_path = Path(path)
    parsed = json.loads(artifact_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, Mapping):
        raise ValueError(f"JSON artifact must be a mapping: {artifact_path}")
    return parsed


def load_operator_context(paths: Sequence[str | Path]) -> tuple[list[Mapping[str, Any]], list[str]]:
    """Load optional operator-context JSON files without aborting the workflow.

    Each path is parsed through `load_json_file` and appended to the returned
    context list only when it satisfies the mapping contract. Missing, malformed,
    or non-object files become warnings so discovery and recommendation tools can
    continue with the remaining evidence while still reporting which context was
    ignored.
    """
    contexts: list[Mapping[str, Any]] = []
    warnings: list[str] = []
    for path in paths:
        try:
            contexts.append(load_json_file(path))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            warnings.append(f"Failed to load operator context {path}: {exc}")
    return contexts, warnings


def load_strategy_artifacts(paths: Sequence[str | Path]) -> LoadedArtifacts:
    """Load known strategy/result artifact files.

    Optional CSV artifacts are summarized by row count and headers. Missing or unsupported
    files are reported as warnings rather than hard failures so a tool client can proceed
    with partial context.
    """
    artifacts: dict[str, Any] = {}
    warnings: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            warnings.append(f"Artifact missing: {path}")
            continue
        key = _artifact_key(path)
        try:
            if path.suffix.lower() == ".json":
                artifacts[key] = load_json_file(path)
            elif path.suffix.lower() == ".csv":
                artifacts[key] = _summarize_csv(path)
            else:
                warnings.append(f"Unsupported artifact type: {path}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            warnings.append(f"Failed to load artifact {path}: {exc}")
    return LoadedArtifacts(artifacts=artifacts, warnings=tuple(warnings))


def build_strategy_artifact_metadata(
    *,
    strategy: Mapping[str, Any],
    parameters: Mapping[str, Any],
    risk_profile: Mapping[str, Any],
    data_assumptions: Mapping[str, Any],
    suite_id: str | None,
    suite_member_id: str | None,
    experiment_id: str | None,
    run_id: str | None,
    output_files: Mapping[str, str],
    recommendation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble reproducible metadata for exported strategy artifact bundles.

    The returned payload snapshots strategy identity, parameters, risk and data
    assumptions, optional suite/run identifiers, output-file locations, and the
    current source revision. Inputs are copied into plain dictionaries so the
    metadata can be serialized independently of caller-owned mappings and later
    used for promotion, review, or artifact provenance checks.
    """
    return {
        "schema_version": "1",
        "strategy": dict(strategy),
        "parameters": dict(parameters),
        "risk_profile": dict(risk_profile),
        "data_assumptions": dict(data_assumptions),
        "suite_id": suite_id,
        "suite_member_id": suite_member_id,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "output_files": dict(output_files),
        "recommendation": dict(recommendation or {}),
        "source_revision": _git_info(),
        "package": {"name": "trader", "version": _package_version()},
    }


def _artifact_key(path: Path) -> str:
    name = path.name.lower()
    if name in {
        "result.json",
        "metrics.json",
        "provenance.json",
        "equity_curve.csv",
        "benchmark_curve.csv",
        "positions.csv",
        "trades.csv",
    }:
        return path.stem
    return path.stem


def _summarize_csv(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    return {
        "path": str(path),
        "columns": list(reader.fieldnames or ()),
        "row_count": len(rows),
    }


def _git_info() -> dict[str, Any]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {"sha": sha or None, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"sha": None, "dirty": None}


def _package_version() -> str:
    try:
        return version("trader")
    except PackageNotFoundError:
        return "unknown"
