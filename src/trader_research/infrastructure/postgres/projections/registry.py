"""Registry for context-owned Postgres artifact projections."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from trader_research.foundation.artifacts import ResearchArtifactRecord


JsonValue = Callable[[Any], Any]
ProjectionWriter = Callable[[Any, ResearchArtifactRecord, JsonValue], None]


@dataclass(frozen=True)
class ProjectionRegistry:
    """Dispatch immutable artifact records to registered projection writers."""

    writers: Mapping[str, ProjectionWriter]

    def __post_init__(self) -> None:
        """Reject blank artifact keys and non-callable writers."""
        for artifact_type, writer in self.writers.items():
            if not artifact_type.strip():
                raise ValueError("projection artifact_type is required")
            if not callable(writer):
                raise TypeError(
                    f"projection writer for {artifact_type} must be callable"
                )

    def write(
        self,
        connection: Any,
        record: ResearchArtifactRecord,
        *,
        json_value: JsonValue,
    ) -> None:
        """Write a typed projection when the artifact type has registered one."""
        writer = self.writers.get(record.artifact_type)
        if writer is not None:
            writer(connection, record, json_value)


def combine_projection_writers(
    *groups: Mapping[str, ProjectionWriter],
) -> ProjectionRegistry:
    """Combine context writer groups while rejecting duplicate ownership."""
    combined: dict[str, ProjectionWriter] = {}
    for group in groups:
        duplicates = set(combined).intersection(group)
        if duplicates:
            names = ", ".join(sorted(duplicates))
            raise ValueError(f"duplicate projection writers: {names}")
        combined.update(group)
    return ProjectionRegistry(combined)
