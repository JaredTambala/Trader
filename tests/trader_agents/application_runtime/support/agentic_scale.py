"""Strict measurements and persistence for bounded Agent scale evidence.

Scale profiles are application-runtime workloads with explicit ceilings, not
general performance targets or permission for unbounded model execution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tests.trader_agents.application_runtime.support.agentic_qualification import AgenticScenarioResult


AGENTIC_SCALE_PHASE = "AGENTIC_BOUNDED_SCALE"
AGENTIC_SCALE_PROFILES = frozenset(
    {
        "single_composite_session",
        "parallel_specialist_join",
        "fresh_process_recovery",
        "concurrent_multi_session",
    }
)
_PAYLOAD_FIELDS = frozenset(
    {
        "session_count",
        "scenario_ids",
        "model_calls",
        "tool_calls",
        "total_tokens",
        "duration_seconds",
        "revisions",
        "peak_concurrency",
        "trace_count",
        "span_count",
        "wall_seconds",
        "breached_ceilings",
    }
)


@dataclass(frozen=True)
class AgenticScaleResult:
    """Credential-free measurements for one controlled scale profile.

    Attributes:
        profile: One code-owned bounded-scale profile identity.
        status: ``passed`` only when all runs and ceilings passed.
        task_count: Number of specialist tasks represented by the profile.
        transition_count: Total public coordinator/candidate revisions.
        tool_call_count: Physical MCP calls observed in MLflow.
        checkpoint_bytes: Total bytes occupied by the checkpoint schema.
        artifact_count: Canonical research-artifact rows after the profile.
        database_bytes: Disposable qualification database size after the run.
        wall_seconds: Host-observed profile duration.
        payload: Closed aggregate agent, trace, and ceiling measurements.
    """

    profile: str
    status: str
    task_count: int
    transition_count: int
    tool_call_count: int
    checkpoint_bytes: int
    artifact_count: int
    database_bytes: int
    wall_seconds: float
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        """Reject unknown profiles, unsafe status, or malformed metrics."""
        if self.profile not in AGENTIC_SCALE_PROFILES:
            raise ValueError(f"unknown agentic scale profile: {self.profile}")
        if self.status not in {"passed", "blocked"}:
            raise ValueError("agentic scale status must be passed or blocked")
        for value, label in (
            (self.task_count, "task_count"),
            (self.transition_count, "transition_count"),
            (self.tool_call_count, "tool_call_count"),
            (self.checkpoint_bytes, "checkpoint_bytes"),
            (self.artifact_count, "artifact_count"),
            (self.database_bytes, "database_bytes"),
        ):
            if value < 0:
                raise ValueError(f"{label} cannot be negative")
        if self.wall_seconds < 0.0:
            raise ValueError("wall_seconds cannot be negative")
        if set(self.payload) != _PAYLOAD_FIELDS:
            raise ValueError("agentic scale payload does not match its closed contract")
        encoded = json.dumps(self.payload, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 32_000:
            raise ValueError("agentic scale payload exceeds 32000 bytes")
        breached = self.payload.get("breached_ceilings")
        if not isinstance(breached, list) or any(
            not isinstance(item, str) or not item for item in breached
        ):
            raise ValueError("breached_ceilings must be a string list")
        if self.status == "passed" and breached:
            raise ValueError("a passed scale profile cannot have breached ceilings")
        if self.status == "blocked" and not breached:
            raise ValueError("a blocked scale profile requires breached ceilings")


def build_agentic_scale_result(
    *,
    profile: str,
    results: Sequence[AgenticScenarioResult],
    task_count: int,
    span_count: int,
    wall_seconds: float,
    checkpoint_bytes: int,
    artifact_count: int,
    database_bytes: int,
    ceilings: Mapping[str, int | float],
    observed_peak_concurrency: int | None = None,
) -> AgenticScaleResult:
    """Aggregate scenario results and compare them with explicit ceilings.

    Args:
        profile: Code-owned profile identity.
        results: Complete scenario results included in this measurement.
        task_count: Specialist task count represented by the profile.
        span_count: Public MLflow span count for the exact sessions.
        wall_seconds: Host-observed duration for the complete profile.
        checkpoint_bytes: Current checkpoint-schema storage size.
        artifact_count: Current canonical research-artifact count.
        database_bytes: Current disposable database size.
        ceilings: Maximum values keyed by payload metric name.
        observed_peak_concurrency: Optional host-observed concurrency across
            sessions; otherwise the greatest scenario-local peak is used.

    Returns:
        Strict persisted-scale contract with every breached ceiling named.

    Raises:
        ValueError: If no results are supplied or a ceiling is unknown.
    """
    if not results:
        raise ValueError("an agentic scale profile requires scenario results")
    if observed_peak_concurrency is not None and observed_peak_concurrency < 0:
        raise ValueError("observed_peak_concurrency cannot be negative")
    metrics: dict[str, int | float] = {
        "session_count": sum(len(result.terminal_actions) for result in results),
        "model_calls": sum(result.model_calls for result in results),
        "tool_calls": sum(result.tool_calls for result in results),
        "total_tokens": sum(result.total_tokens for result in results),
        "duration_seconds": sum(result.duration_seconds for result in results),
        "revisions": sum(result.revisions for result in results),
        "peak_concurrency": (
            observed_peak_concurrency
            if observed_peak_concurrency is not None
            else max(result.peak_concurrency for result in results)
        ),
        "trace_count": sum(len(result.trace_ids) for result in results),
        "span_count": span_count,
        "wall_seconds": wall_seconds,
    }
    unknown = set(ceilings) - set(metrics)
    if unknown:
        raise ValueError(f"unknown agentic scale ceilings: {sorted(unknown)}")
    breached = [
        f"{name}:{metrics[name]}>{limit}"
        for name, limit in sorted(ceilings.items())
        if metrics[name] > limit
    ]
    breached.extend(
        f"scenario:{result.scenario_id}:{result.status}"
        for result in results
        if result.status != "passed"
    )
    payload: dict[str, Any] = {
        **metrics,
        "scenario_ids": [result.scenario_id for result in results],
        "breached_ceilings": breached,
    }
    return AgenticScaleResult(
        profile=profile,
        status="blocked" if breached else "passed",
        task_count=task_count,
        transition_count=int(metrics["revisions"]),
        tool_call_count=int(metrics["tool_calls"]),
        checkpoint_bytes=checkpoint_bytes,
        artifact_count=artifact_count,
        database_bytes=database_bytes,
        wall_seconds=wall_seconds,
        payload=payload,
    )


def measure_agentic_storage(
    connection: psycopg.Connection[Any],
    *,
    checkpoint_schema: str,
) -> Mapping[str, int]:
    """Measure checkpoint, canonical artifact, and database storage bytes."""
    with connection.cursor(row_factory=dict_row) as cursor:
        row = cursor.execute(
            "SELECT pg_database_size(current_database()) AS database_bytes, "
            "(SELECT count(*) FROM research_artifacts) AS artifact_count, "
            "COALESCE((SELECT sum(pg_total_relation_size(format('%%I.%%I', "
            "schemaname, tablename)::regclass)) FROM pg_tables "
            "WHERE schemaname = %s), 0) AS checkpoint_bytes",
            [checkpoint_schema],
        ).fetchone()
    if row is None:
        raise RuntimeError("agentic storage measurement returned no row")
    return {
        "checkpoint_bytes": int(row["checkpoint_bytes"]),
        "artifact_count": int(row["artifact_count"]),
        "database_bytes": int(row["database_bytes"]),
    }


def save_agentic_scale_result(
    connection: psycopg.Connection[Any],
    *,
    qualification_profile: str,
    freeze_revision: str,
    result: AgenticScaleResult,
) -> None:
    """Upsert one exact phase/profile result for the frozen revision."""
    connection.execute(
        """
        INSERT INTO verification_control.orchestration_scale_results (
            qualification_profile, freeze_revision, phase, profile, status,
            task_count, transition_count, tool_call_count, checkpoint_bytes,
            artifact_count, database_bytes, wall_seconds, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (qualification_profile, freeze_revision, phase, profile)
        DO UPDATE SET
            status = EXCLUDED.status,
            task_count = EXCLUDED.task_count,
            transition_count = EXCLUDED.transition_count,
            tool_call_count = EXCLUDED.tool_call_count,
            checkpoint_bytes = EXCLUDED.checkpoint_bytes,
            artifact_count = EXCLUDED.artifact_count,
            database_bytes = EXCLUDED.database_bytes,
            wall_seconds = EXCLUDED.wall_seconds,
            payload = EXCLUDED.payload,
            recorded_at = now()
        """,
        [
            qualification_profile,
            freeze_revision,
            AGENTIC_SCALE_PHASE,
            result.profile,
            result.status,
            result.task_count,
            result.transition_count,
            result.tool_call_count,
            result.checkpoint_bytes,
            result.artifact_count,
            result.database_bytes,
            result.wall_seconds,
            Jsonb(dict(result.payload)),
        ],
    )


def load_agentic_scale_results(
    connection: psycopg.Connection[Any],
    *,
    qualification_profile: str,
    freeze_revision: str,
) -> tuple[AgenticScaleResult, ...]:
    """Load strict scale results for one exact profile and frozen revision."""
    with connection.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute(
            "SELECT profile, status, task_count, transition_count, "
            "tool_call_count, checkpoint_bytes, artifact_count, database_bytes, "
            "wall_seconds, payload FROM "
            "verification_control.orchestration_scale_results "
            "WHERE qualification_profile = %s AND freeze_revision = %s "
            "AND phase = %s ORDER BY profile",
            [qualification_profile, freeze_revision, AGENTIC_SCALE_PHASE],
        ).fetchall()
    return tuple(
        AgenticScaleResult(
            profile=str(row["profile"]),
            status=str(row["status"]),
            task_count=int(row["task_count"]),
            transition_count=int(row["transition_count"]),
            tool_call_count=int(row["tool_call_count"]),
            checkpoint_bytes=int(row["checkpoint_bytes"]),
            artifact_count=int(row["artifact_count"]),
            database_bytes=int(row["database_bytes"]),
            wall_seconds=float(row["wall_seconds"]),
            payload=dict(row["payload"]),
        )
        for row in rows
    )
