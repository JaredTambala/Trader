"""Write typed projections for canonical orchestration governance records.

Objective, protocol, plan, and outcome writers expose workflow identity, status,
digests, and bounded summaries for operational queries. Full governance payloads
remain authoritative in the canonical artifact table.
"""

from __future__ import annotations

from typing import Any

from trader_research.foundation.artifacts import ResearchArtifactRecord
from trader_research.governance.artifacts import (
    EXPERIMENT_PROTOCOL,
    RESEARCH_OBJECTIVE,
    WORKFLOW_OUTCOME,
    WORKFLOW_PLAN,
)


def write_research_objective(
    connection: Any,
    record: ResearchArtifactRecord,
    json_value: Any,
) -> None:
    """Upsert query fields for one research objective.

    Objective identity, lifecycle status, requester, actor, and the complete
    canonical payload are written in the caller's transaction. The projection
    does not approve, terminate, or otherwise mutate the objective contract.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_objectives (
            objective_id, status, requested_by, actor, payload
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (objective_id) DO UPDATE SET
            status = EXCLUDED.status,
            requested_by = EXCLUDED.requested_by,
            actor = EXCLUDED.actor,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("status") or record.status,
            payload.get("requested_by"),
            payload.get("actor"),
            json_value(payload),
        ],
    )


def write_experiment_protocol(
    connection: Any,
    record: ResearchArtifactRecord,
    json_value: Any,
) -> None:
    """Upsert query fields for one immutable experiment protocol.

    Protocol and objective identity, status, requester, proposer, and the complete
    canonical payload are stored for bounded queries. Transaction lifecycle is
    owned by the artifact store.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_experiment_protocols (
            protocol_id, objective_id, status, requested_by, proposed_by, payload
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (protocol_id) DO UPDATE SET
            objective_id = EXCLUDED.objective_id,
            status = EXCLUDED.status,
            requested_by = EXCLUDED.requested_by,
            proposed_by = EXCLUDED.proposed_by,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("objective_id"),
            payload.get("status") or record.status,
            payload.get("requested_by"),
            payload.get("proposed_by"),
            json_value(payload),
        ],
    )


def write_workflow_plan(
    connection: Any,
    record: ResearchArtifactRecord,
    json_value: Any,
) -> None:
    """Upsert query fields for one deterministic workflow plan.

    Plan, objective, protocol, template, requester, actor, and status fields are
    flattened with the complete payload. The writer assumes the record was
    already validated and does not compile or execute the workflow.
    """
    payload = dict(record.payload)
    objective = dict(payload.get("objective_ref") or {})
    protocol = dict(payload.get("protocol_ref") or {})
    connection.execute(
        """
        INSERT INTO research_workflow_plans (
            plan_id, objective_id, protocol_id, template_id, template_version,
            status, requested_by, actor, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (plan_id) DO UPDATE SET
            objective_id = EXCLUDED.objective_id,
            protocol_id = EXCLUDED.protocol_id,
            template_id = EXCLUDED.template_id,
            template_version = EXCLUDED.template_version,
            status = EXCLUDED.status,
            requested_by = EXCLUDED.requested_by,
            actor = EXCLUDED.actor,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            objective.get("artifact_id"),
            protocol.get("artifact_id"),
            payload.get("template_id"),
            payload.get("template_version"),
            payload.get("status") or record.status,
            payload.get("requested_by"),
            payload.get("actor"),
            json_value(payload),
        ],
    )


def write_workflow_outcome(
    connection: Any,
    record: ResearchArtifactRecord,
    json_value: Any,
) -> None:
    """Upsert query fields for one terminal workflow outcome.

    Outcome, workflow, and plan identity, terminal status, review-reference count,
    requester, actor, and the complete payload are projected. Specialist evidence
    remains referenced rather than copied into separate ownership.
    """
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_workflow_outcomes (
            outcome_id, workflow_id, plan_id, status, review_ref_count,
            requested_by, actor, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (outcome_id) DO UPDATE SET
            workflow_id = EXCLUDED.workflow_id,
            plan_id = EXCLUDED.plan_id,
            status = EXCLUDED.status,
            review_ref_count = EXCLUDED.review_ref_count,
            requested_by = EXCLUDED.requested_by,
            actor = EXCLUDED.actor,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload.get("workflow_id"),
            payload.get("plan_id"),
            payload.get("status") or record.status,
            len(payload.get("review_verdict_refs") or ()),
            payload.get("requested_by"),
            payload.get("actor"),
            json_value(payload),
        ],
    )


PROJECTION_WRITERS = {
    RESEARCH_OBJECTIVE: write_research_objective,
    EXPERIMENT_PROTOCOL: write_experiment_protocol,
    WORKFLOW_PLAN: write_workflow_plan,
    WORKFLOW_OUTCOME: write_workflow_outcome,
}
