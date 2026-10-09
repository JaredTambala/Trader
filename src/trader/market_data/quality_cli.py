"""Core-owned JSON output contract for the data-quality CLI."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping


def data_quality_cli_envelope(
    report: Mapping[str, object],
    *,
    report_path: str | Path | None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Build the stable CLI JSON envelope without importing MCP transport.

    Args:
        report: JSON-ready quality report produced by the core quality service.
        report_path: Optional path where the report was written.
        generated_at: Timestamp for deterministic tests; defaults to UTC now.

    Returns:
        JSON-compatible read-only command envelope.
    """
    timestamp = generated_at or datetime.now(timezone.utc)
    return {
        "ok": True,
        "command": "data_quality",
        "agent_owner": "Data Agent",
        "side_effect": "read_only",
        "schema_version": "1",
        "generated_at": timestamp.isoformat(),
        "data": {
            "report": dict(report),
            "report_id": report.get("report_id"),
            "report_path": str(report_path) if report_path is not None else None,
        },
        "artifacts": {},
        "warnings": [],
        "errors": [],
    }


def render_data_quality_cli_json(
    report: Mapping[str, object],
    *,
    report_path: str | Path | None,
    generated_at: datetime | None = None,
) -> str:
    """Serialize the core-owned CLI envelope as stable pretty JSON."""
    return json.dumps(
        data_quality_cli_envelope(
            report,
            report_path=report_path,
            generated_at=generated_at,
        ),
        indent=2,
        sort_keys=True,
    )


__all__ = ["data_quality_cli_envelope", "render_data_quality_cli_json"]
