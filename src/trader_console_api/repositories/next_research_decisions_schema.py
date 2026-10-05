"""Catalog contract for the research-owned next-decision projection.

The research package owns installation of ``research_next_decisions`` alongside
the canonical ``research_artifacts`` table.  Console only verifies that the
projection is present and compatible; startup never creates or repairs it.
"""

from __future__ import annotations


COLUMNS = {
    "artifact_id": "text",
    "decision_id": "text",
    "revision": "int4",
    "outcome": "text",
    "source_run_id": "text",
    "operator": "text",
    "decided_at": "timestamptz",
    "supersedes_artifact_id": "text",
    "decision_digest": "text",
    "payload": "jsonb",
}

CATALOG_SQL = """
SELECT column_name, udt_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'research_next_decisions'
"""


class NextResearchDecisionStorageUnavailable(RuntimeError):
    """Research next-decision storage is absent or incompatible."""


__all__ = ["CATALOG_SQL", "COLUMNS", "NextResearchDecisionStorageUnavailable"]
