"""Research-to-Console implementation-lineage adapter tests.

Subject: Revalidation of exact admitted implementation and validation evidence.
Level: Application adapter unit tests.
Collaborators: Patched research admission loader and typed Console contracts.
Guarantees: Research-owned version/name/hash/report evidence is compared before
authoring proceeds; drift fails closed.
Non-goals: PostgreSQL artifact persistence and source execution.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from trader_console_api.services.implementation_lineage import ResearchArtifactLineageResolver
from tests.trader_console_api.support import implementation_lineage


def test_resolver_rehydrates_canonical_validation_report(monkeypatch) -> None:
    """The resolver returns research report blockers/warnings without accepting opaque code."""
    lineage = implementation_lineage("noop")
    report = {
        "validation_id": lineage.implementation_validation_id,
        "implementation_version_id": lineage.implementation_version_id,
        "implementation_kind": "strategy",
        "source_hash": lineage.source_hash,
        "status": "passed",
        "valid": True,
        "blockers": [],
        "warnings": ["fixture warning"],
    }
    implementation = SimpleNamespace(
        implementation_version_id=lineage.implementation_version_id,
        implementation_kind="strategy",
        source_hash=lineage.source_hash,
        name=lineage.implementation_name,
        version=lineage.implementation_version,
        metadata={},
    )
    monkeypatch.setattr(
        "trader_console_api.services.implementation_lineage.load_passed_implementation",
        lambda *args, **kwargs: (implementation, report),
    )

    resolved = ResearchArtifactLineageResolver(object()).resolve(
        lineage,
        profile_id="noop",
        expected_kind="strategy",
    )

    assert resolved.validation_report.warnings == ("fixture warning",)


def test_resolver_fails_closed_on_source_hash_drift(monkeypatch) -> None:
    """A current research digest change cannot be silently submitted from stale authoring state."""
    lineage = implementation_lineage("noop")
    implementation = SimpleNamespace(
        implementation_version_id=lineage.implementation_version_id,
        implementation_kind="strategy",
        source_hash="c" * 64,
        name=lineage.implementation_name,
        version=lineage.implementation_version,
        metadata={},
    )
    monkeypatch.setattr(
        "trader_console_api.services.implementation_lineage.load_passed_implementation",
        lambda *args, **kwargs: (implementation, lineage.validation_report.model_dump()),
    )

    with pytest.raises(ValueError, match="source hash drifted"):
        ResearchArtifactLineageResolver(object()).resolve(
            lineage,
            profile_id="noop",
            expected_kind="strategy",
        )
