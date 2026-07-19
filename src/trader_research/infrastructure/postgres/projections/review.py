"""Postgres projection writers for review artifacts."""

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
    """Project one parameter_optimization_evaluation_report artifact."""
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
    """Project one parameter_optimization_audit_plan artifact."""
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
    """Project one parameter_optimization_robustness_report artifact."""
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
