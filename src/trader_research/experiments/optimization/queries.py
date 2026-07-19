"""Provider-independent reads of canonical optimization ledgers."""

from __future__ import annotations

from trader_research.foundation import ApplicationResult, error_result, success_result
from trader_research.foundation.artifacts import ArtifactReference, ResearchArtifactStore, ResearchArtifactStoreError
from trader_research.governance.artifacts import PARAMETER_OPTIMIZATION_RUN

from .commands import RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS
from .ledger import load_validated_parameter_optimization_run


def get_parameter_optimization_results(
    *,
    optimization_run_ref: str,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Read canonical run and complete trial ledger independently of provider availability."""
    command = RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        run, trials = load_validated_parameter_optimization_run(
            artifact_store, optimization_run_ref
        )
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error(command, "parameter_optimization_lookup_failed", str(exc))
    return success_result(
        command=command,
        data={"parameter_optimization_run": run, "trials": trials},
        artifacts={
            "parameter_optimization_run": ArtifactReference(
                artifact_type=PARAMETER_OPTIMIZATION_RUN,
                uri=f"research://postgres/{PARAMETER_OPTIMIZATION_RUN}/{run['optimization_run_id']}",
                metadata={"status": run.get("status"), "trial_count": len(trials)},
            ).to_dict()
        },
    )


def _error(command: str, code: str, message: str) -> ApplicationResult:
    return error_result(
        command=command,
        code=code,
        message=message,
    )
