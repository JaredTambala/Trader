"""Write typed Postgres projections for Experiments-owned artifacts.

Each writer extracts normalized fields from an already validated canonical
record and upserts the corresponding query table within the caller's transaction.
Projection rows remain derived indexes and never replace the base artifact.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Any

from trader_research.foundation.artifacts import ResearchArtifactRecord
from trader_research.governance.artifacts import (
    IMPLEMENTATION_VERSION,
    IMPLEMENTATION_VALIDATION_REPORT,
    STRATEGY_SPECIFICATION,
    STRATEGY_SPECIFICATION_VALIDATION_REPORT,
    RISK_STACK_SPECIFICATION,
    RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
    BACKTEST_SPECIFICATION,
    BACKTEST_SPECIFICATION_VALIDATION_REPORT,
    PARAMETER_OPTIMIZATION_PLAN,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
    EXPERIMENT_TRACKING_PROJECTION_REPORT,
    BACKTEST_RUN,
)


def write_implementation_version(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields for one implementation-version record.

    The writer stores implementation identity, kind, lifecycle status, source
    hash, authoring origin, and the complete JSON payload. It uses the caller's
    active transaction and does not commit independently.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_implementation_versions (
            implementation_version_id, implementation_kind, name, version,
            status, source_hash, authoring_origin, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (implementation_version_id) DO UPDATE SET
            status = EXCLUDED.status,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("implementation_kind"),
            payload.get("name"),
            payload.get("version"),
            payload.get("status") or record.status,
            payload.get("source_hash") or record.source_hash,
            payload.get("authoring_origin"),
            json_value(payload),
        ],
    )


def write_implementation_validation_report(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields for an implementation-validation record.

    Validation identity, implementation lineage, kind, status, validity, source
    hash, and the complete payload are derived from ``record``. The caller owns
    transaction commit and rollback.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_implementation_validations (
            validation_id, implementation_version_id, implementation_kind,
            status, valid, source_hash, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (validation_id) DO UPDATE SET
            status = EXCLUDED.status,
            valid = EXCLUDED.valid,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("implementation_version_id"),
            payload.get("implementation_kind"),
            payload.get("status") or record.status,
            bool(payload.get("valid")),
            payload.get("source_hash") or record.source_hash,
            json_value(payload),
        ],
    )


def write_strategy_specification(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields for one strategy-specification record.

    The projection exposes implementation lineage, source hash, tunable fields,
    prediction decision scope and binding count, status, and the complete payload.
    It writes through the caller's transaction without committing.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_strategy_specifications (
            strategy_specification_id, implementation_version_id, status,
            source_hash, tunable_fields, decision_scope, prediction_binding_count, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (strategy_specification_id) DO UPDATE SET
            status = EXCLUDED.status,
            tunable_fields = EXCLUDED.tunable_fields,
            decision_scope = EXCLUDED.decision_scope,
            prediction_binding_count = EXCLUDED.prediction_binding_count,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("implementation_version_id"),
            payload.get("status") or record.status,
            payload.get("source_hash") or record.source_hash,
            [str(item) for item in payload.get("tunable_fields", [])],
            str(payload.get("decision_scope") or "per_symbol"),
            len(payload.get("prediction_bindings") or []),
            json_value(payload),
        ],
    )


def write_strategy_specification_validation_report(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert one strategy-specification validation projection.

    The row contains validation and specification identity, status, validity, and
    the canonical payload encoded by ``json_value``. Transaction lifecycle remains
    with the artifact store.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_strategy_specification_validations (
            validation_id, strategy_specification_id, status, valid, payload
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (validation_id) DO UPDATE SET
            status = EXCLUDED.status,
            valid = EXCLUDED.valid,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("strategy_specification_id"),
            payload.get("status") or record.status,
            bool(payload.get("valid")),
            json_value(payload),
        ],
    )


def write_risk_stack_specification(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields for one ordered risk-stack specification.

    Ordered manager implementation IDs, stack status, and the complete canonical
    payload are extracted from ``record``. The writer participates in the
    artifact store's existing transaction and does not commit.
    """
    payload = dict(record.payload)
    manager_ids = [
        str(item.get("implementation_version_id"))
        for item in payload.get("risk_managers", [])
        if isinstance(item, MappingABC)
    ]
    connection.execute(
        """
        INSERT INTO research_risk_stack_specifications (
            risk_stack_specification_id, implementation_version_ids, status, payload
        ) VALUES (%s, %s, %s, %s)
        ON CONFLICT (risk_stack_specification_id) DO UPDATE SET
            status = EXCLUDED.status,
            implementation_version_ids = EXCLUDED.implementation_version_ids,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            manager_ids,
            payload.get("status") or record.status,
            json_value(payload),
        ],
    )


def write_risk_stack_specification_validation_report(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert one risk-stack validation projection.

    Validation and stack identity, status, validity, and the complete payload are
    written for bounded queries. Any database error propagates to the artifact
    store so the base record and projection can roll back together.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_risk_stack_specification_validations (
            validation_id, risk_stack_specification_id, status, valid, payload
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (validation_id) DO UPDATE SET
            status = EXCLUDED.status,
            valid = EXCLUDED.valid,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("risk_stack_specification_id"),
            payload.get("status") or record.status,
            bool(payload.get("valid")),
            json_value(payload),
        ],
    )


def write_backtest_specification(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields for one canonical backtest specification.

    Strategy, risk, dataset, parent, selection, and variant lineage are flattened
    alongside status and the complete payload. The caller owns the surrounding
    artifact transaction.
    """
    payload = dict(record.payload)
    dataset = payload.get("dataset") or {}
    dataset_payload = dataset.get("payload") if isinstance(dataset, MappingABC) else {}
    connection.execute(
        """
        INSERT INTO research_backtest_specifications (
            backtest_specification_id, strategy_specification_id,
            risk_stack_specification_id, dataset_id, status,
            parent_specification_ref, selection_origin_ref, variant_reason, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (backtest_specification_id) DO UPDATE SET
            status = EXCLUDED.status,
            parent_specification_ref = EXCLUDED.parent_specification_ref,
            selection_origin_ref = EXCLUDED.selection_origin_ref,
            variant_reason = EXCLUDED.variant_reason,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("strategy_specification_id"),
            payload.get("risk_stack_specification_id"),
            dataset_payload.get("dataset_id")
            if isinstance(dataset_payload, MappingABC)
            else None,
            payload.get("status") or record.status,
            payload.get("parent_specification_ref"),
            payload.get("selection_origin_ref"),
            payload.get("variant_reason"),
            json_value(payload),
        ],
    )


def write_backtest_specification_validation_report(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert one backtest-specification validation projection.

    The row exposes validation and specification identity, status, validity,
    dataset hash, and the complete payload. Database failures propagate so the
    canonical artifact write remains atomic with this projection.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_backtest_specification_validations (
            validation_id, backtest_specification_id, status, valid, dataset_hash, payload
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (validation_id) DO UPDATE SET
            status = EXCLUDED.status,
            valid = EXCLUDED.valid,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("backtest_specification_id"),
            payload.get("status") or record.status,
            bool(payload.get("valid")),
            payload.get("dataset_hash"),
            json_value(payload),
        ],
    )


def write_parameter_optimization_plan(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields for one parameter-optimization plan.

    Base specification, objective, direction, seed, budget, parent, variant, and
    status fields are stored with the complete canonical payload. The operation
    uses but does not commit the caller's transaction.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_parameter_optimization_plans (
            optimization_plan_id, base_backtest_specification_id,
            objective_implementation_version_id, direction, seed, max_trials,
            status, parent_plan_ref, variant_reason, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (optimization_plan_id) DO UPDATE SET
            status = EXCLUDED.status,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("base_backtest_specification_id"),
            payload.get("objective_implementation_version_id"),
            payload.get("direction"),
            payload.get("seed"),
            payload.get("max_trials"),
            payload.get("status") or record.status,
            payload.get("parent_plan_ref"),
            payload.get("variant_reason"),
            json_value(payload),
        ],
    )


def write_parameter_optimization_run(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields for one parameter-optimization run.

    Plan and engine identity, seed, status, deterministic selection, selected
    backtest lineage, and the full payload are projected. Provider state remains
    bounded within the payload and is not made authoritative by this row.
    """
    payload = dict(record.payload)
    profile = payload.get("engine_profile") or {}
    selected_refs = payload.get("selected_child_refs") or {}
    connection.execute(
        """
        INSERT INTO research_parameter_optimization_runs (
            optimization_run_id, optimization_plan_id, engine_name, engine_version,
            engine_configuration_digest, seed, status, selected_trial_id,
            selected_backtest_specification_id, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (optimization_run_id) DO UPDATE SET
            status = EXCLUDED.status,
            selected_trial_id = EXCLUDED.selected_trial_id,
            selected_backtest_specification_id = EXCLUDED.selected_backtest_specification_id,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("optimization_plan_id"),
            profile.get("profile_name"),
            profile.get("provider_version"),
            profile.get("configuration_digest"),
            payload.get("seed"),
            payload.get("status") or record.status,
            payload.get("selected_trial_id"),
            selected_refs.get("backtest_specification_id"),
            json_value(payload),
        ],
    )


def write_parameter_optimization_trial(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields for one canonical optimization trial.

    Trial sequence, run and plan lineage, parameters, status, objective value,
    child backtest references, and the complete payload are written through the
    caller's active transaction.
    """
    payload = dict(record.payload)
    child_refs = payload.get("child_refs") or {}
    connection.execute(
        """
        INSERT INTO research_parameter_optimization_trials (
            trial_id, optimization_run_id, optimization_plan_id, sequence,
            status, objective_value, parameters, child_backtest_specification_id,
            child_backtest_run_id, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (trial_id) DO UPDATE SET
            status = EXCLUDED.status,
            objective_value = EXCLUDED.objective_value,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("optimization_run_id"),
            payload.get("optimization_plan_id"),
            payload.get("sequence"),
            payload.get("status") or record.status,
            payload.get("objective_value"),
            json_value(dict(payload.get("parameters") or {})),
            child_refs.get("backtest_specification_id"),
            child_refs.get("backtest_run_id"),
            json_value(payload),
        ],
    )


def write_experiment_tracking_projection_report(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert one non-authoritative tracking-projection report.

    The row exposes canonical run identity, selected tracking profile, status,
    the explicit authority flag, and complete projection evidence. It cannot
    promote provider state over the canonical Trader run.
    """
    payload = dict(record.payload)
    profile = payload.get("tracking_profile") or {}
    connection.execute(
        """
        INSERT INTO research_experiment_tracking_projections (
            projection_id, canonical_run_id, tracking_profile, status, authoritative, payload
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (projection_id) DO UPDATE SET
            status = EXCLUDED.status,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("canonical_run_id"),
            profile.get("profile_name"),
            payload.get("status") or record.status,
            bool(payload.get("authoritative")),
            json_value(payload),
        ],
    )


def write_backtest_run(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields and summary for one canonical backtest run.

    Run kind, status, dataset and specification lineage, selection and variant
    ancestry, summary metrics, and the complete result payload are stored. The
    artifact store owns transaction commit and conflict handling.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_backtest_runs (
            run_id, backtest_kind, status, dataset_id,
            backtest_specification_id, strategy_specification_id,
            risk_stack_specification_id, selection_origin_ref,
            parent_specification_ref, variant_reason, summary, payload
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id) DO UPDATE SET
            backtest_kind = EXCLUDED.backtest_kind,
            status = EXCLUDED.status,
            dataset_id = EXCLUDED.dataset_id,
            backtest_specification_id = EXCLUDED.backtest_specification_id,
            strategy_specification_id = EXCLUDED.strategy_specification_id,
            risk_stack_specification_id = EXCLUDED.risk_stack_specification_id,
            selection_origin_ref = EXCLUDED.selection_origin_ref,
            parent_specification_ref = EXCLUDED.parent_specification_ref,
            variant_reason = EXCLUDED.variant_reason,
            summary = EXCLUDED.summary,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("backtest_kind"),
            payload.get("status") or record.status,
            payload.get("dataset_id"),
            payload.get("backtest_specification_id"),
            payload.get("strategy_specification_id"),
            payload.get("risk_stack_specification_id"),
            payload.get("selection_origin_ref"),
            payload.get("parent_specification_ref"),
            payload.get("variant_reason"),
            json_value(dict(payload.get("summary") or {})),
            json_value(payload),
        ],
    )


PROJECTION_WRITERS = {
    IMPLEMENTATION_VERSION: write_implementation_version,
    IMPLEMENTATION_VALIDATION_REPORT: write_implementation_validation_report,
    STRATEGY_SPECIFICATION: write_strategy_specification,
    STRATEGY_SPECIFICATION_VALIDATION_REPORT: write_strategy_specification_validation_report,
    RISK_STACK_SPECIFICATION: write_risk_stack_specification,
    RISK_STACK_SPECIFICATION_VALIDATION_REPORT: write_risk_stack_specification_validation_report,
    BACKTEST_SPECIFICATION: write_backtest_specification,
    BACKTEST_SPECIFICATION_VALIDATION_REPORT: write_backtest_specification_validation_report,
    PARAMETER_OPTIMIZATION_PLAN: write_parameter_optimization_plan,
    PARAMETER_OPTIMIZATION_RUN: write_parameter_optimization_run,
    PARAMETER_OPTIMIZATION_TRIAL: write_parameter_optimization_trial,
    EXPERIMENT_TRACKING_PROJECTION_REPORT: write_experiment_tracking_projection_report,
    BACKTEST_RUN: write_backtest_run,
}
