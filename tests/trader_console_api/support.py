"""Shared typed Console fixtures used by contract and service tests.

Subject: Admitted implementation lineage fixtures.
Level: Test support.
Collaborators: Console Pydantic contracts only; no database or external adapter.
Guarantees: Fixtures preserve exact strategy/risk IDs, hashes, and passed reports.
Non-goals: Research admission or production lineage resolution.
"""

from typing import Literal

from trader_console_api.contracts import (
    ImplementationLineage,
    ImplementationValidationReport,
)


def implementation_lineage(
    profile_id: str = "noop",
    *,
    kind: Literal["strategy", "risk"] = "strategy",
    suffix: str = "strategy",
    status: Literal["passed", "blocked"] = "passed",
    blockers: tuple[str, ...] = (),
) -> ImplementationLineage:
    """Build a deterministic admitted strategy or risk lineage fixture."""
    implementation_kind: Literal["strategy", "risk_manager"] = (
        "risk_manager" if kind == "risk" else "strategy"
    )
    source_digest = ("b" if implementation_kind == "risk_manager" else "a") * 64
    version_id = f"implementation-{suffix}"
    validation_id = f"validation-{suffix}"
    report = ImplementationValidationReport(
        validation_id=validation_id,
        implementation_version_id=version_id,
        implementation_kind=implementation_kind,
        source_hash=source_digest,
        status=status,
        valid=status == "passed",
        blockers=blockers,
    )
    return ImplementationLineage(
        profile_id=profile_id,
        implementation_version_id=version_id,
        implementation_kind=implementation_kind,
        implementation_name=f"{profile_id} implementation",
        implementation_version="1.0.0",
        source_hash=source_digest,
        implementation_validation_id=validation_id,
        specification_id=f"specification-{suffix}",
        decision="exact_reuse",
        validation_report=report,
    )


__all__ = ["implementation_lineage"]
