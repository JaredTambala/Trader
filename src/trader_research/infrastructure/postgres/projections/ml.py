"""Postgres projection writers for ML deployment artifacts."""

from __future__ import annotations

from typing import Any

from trader_research.foundation.artifacts import ResearchArtifactRecord
from trader_research.governance.artifacts import (
    ML_DEPLOYMENT_MANIFEST,
    ML_DEPLOYMENT_VALIDATION_REPORT,
)


def write_ml_deployment(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Project one immutable raw-inference deployment manifest."""
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_ml_deployments (
            deployment_id, model_version_id, feature_set_id, adapter_profile,
            inference_scope, decision_scope, eligibility, status, payload
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (deployment_id) DO UPDATE SET
            model_version_id = EXCLUDED.model_version_id,
            feature_set_id = EXCLUDED.feature_set_id,
            adapter_profile = EXCLUDED.adapter_profile,
            inference_scope = EXCLUDED.inference_scope,
            decision_scope = EXCLUDED.decision_scope,
            eligibility = EXCLUDED.eligibility,
            status = EXCLUDED.status,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload["model_version"]["payload"]["model_version_id"],
            payload["feature_set"]["payload"]["feature_set_id"],
            payload["adapter_profile"]["profile_name"],
            payload["inference_scope"],
            payload["decision_scope"],
            [str(item) for item in payload.get("eligibility", [])],
            payload.get("status") or record.status,
            json_value(payload),
        ],
    )


def write_ml_deployment_validation(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Project one deployment validation result."""
    payload = dict(record.payload)
    adapter_evidence = dict(payload.get("adapter_evidence") or {})
    connection.execute(
        """
        INSERT INTO research_ml_deployment_validations (
            validation_id, deployment_id, status, valid, adapter_status, payload
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (validation_id) DO UPDATE SET
            deployment_id = EXCLUDED.deployment_id,
            status = EXCLUDED.status,
            valid = EXCLUDED.valid,
            adapter_status = EXCLUDED.adapter_status,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload["deployment_id"],
            payload.get("status") or record.status,
            bool(payload.get("valid")),
            str(adapter_evidence.get("status") or "not_run"),
            json_value(payload),
        ],
    )


PROJECTION_WRITERS = {
    ML_DEPLOYMENT_MANIFEST: write_ml_deployment,
    ML_DEPLOYMENT_VALIDATION_REPORT: write_ml_deployment_validation,
}
