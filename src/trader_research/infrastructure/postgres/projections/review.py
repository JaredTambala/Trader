"""Write typed Postgres projections for Review-owned artifacts.

Evaluation reports, audit plans, and robustness reports are reduced to stable
query fields while their complete evidence remains in canonical records. Writers
perform no experiment execution or independent review judgment.
"""

from __future__ import annotations

from typing import Any

from trader_research.foundation.artifacts import ResearchArtifactRecord
from trader_research.governance.artifacts import (
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
    PARAMETER_OPTIMIZATION_AUDIT_PLAN,
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
)


def write_parameter_optimization_evaluation_report(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert one optimization Evaluation-report projection.

    Report, optimization-run, holdout-run, and status fields are stored with the
    complete canonical payload. The writer performs no holdout assessment and
    uses the caller's active transaction.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_parameter_optimization_evaluations (
            report_id, optimization_run_id, holdout_backtest_run_id, status, payload
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (report_id) DO UPDATE SET status = EXCLUDED.status, payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("optimization_run_id"),
            payload.get("holdout_backtest_run_id"),
            payload.get("status") or record.status,
            json_value(payload),
        ],
    )


def write_parameter_optimization_audit_plan(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert one parameter-optimization audit-plan projection.

    Audit-plan identity, baseline-run lineage, status, and the complete canonical
    payload are written for bounded queries. The writer neither declares new
    attacks nor executes existing ones.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_parameter_optimization_audit_plans (
            audit_plan_id, baseline_optimization_run_id, status, payload
        ) VALUES (%s, %s, %s, %s)
        ON CONFLICT (audit_plan_id) DO UPDATE SET status = EXCLUDED.status, payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("baseline_optimization_run_id"),
            payload.get("status") or record.status,
            json_value(payload),
        ],
    )


def write_parameter_optimization_robustness_report(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert one optimization robustness-report projection.

    Report, audit-plan, and baseline-run identity, status, and the complete
    payload are written in the caller's transaction. No robustness judgment is
    recomputed or altered by this projection writer.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_parameter_optimization_robustness_reports (
            report_id, audit_plan_id, baseline_optimization_run_id, status, payload
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (report_id) DO UPDATE SET status = EXCLUDED.status, payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("audit_plan_id"),
            payload.get("baseline_optimization_run_id"),
            payload.get("status") or record.status,
            json_value(payload),
        ],
    )


PROJECTION_WRITERS = {
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT: write_parameter_optimization_evaluation_report,
    PARAMETER_OPTIMIZATION_AUDIT_PLAN: write_parameter_optimization_audit_plan,
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT: write_parameter_optimization_robustness_report,
}
