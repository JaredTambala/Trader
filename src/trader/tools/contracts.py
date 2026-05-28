"""Compatibility shim for migrated research tool contracts.

The canonical implementations live in `trader_research.contracts`.
"""

from trader_research.contracts import (  # noqa: F401
    SCHEMA_VERSION,
    ArtifactReference,
    SideEffect,
    ToolEnvelope,
    envelope_json,
    error_envelope,
    success_envelope,
    write_json_artifact,
)
