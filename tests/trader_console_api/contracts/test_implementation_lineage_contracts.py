"""Console implementation-lineage contract tests.

Subject: Typed strategy/risk admission evidence accepted by authoring.
Level: Pydantic contract tests.
Collaborators: Console public contracts and a deterministic fixture.
Guarantees: Exact IDs and hashes are bound to a passed validation report and
opaque imports/callables cannot cross the API boundary.
Non-goals: Research artifact persistence and source execution.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from trader_console_api.contracts import BacktestPreflightRequest, ImplementationLineage
from tests.trader_console_api.support import implementation_lineage


def test_lineage_requires_matching_validation_evidence() -> None:
    """Nested validation evidence cannot be replaced by a different source hash."""
    with pytest.raises(ValidationError, match="source hash"):
        ImplementationLineage.model_validate(
            {
                **implementation_lineage().model_dump(mode="json"),
                "validation_report": {
                    **implementation_lineage().validation_report.model_dump(mode="json"),
                    "source_hash": "c" * 64,
                },
            }
        )


def test_authoring_rejects_opaque_imports_and_callables() -> None:
    """The request admits IDs and reports, never executable import/callable values."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        BacktestPreflightRequest.model_validate(
            {
                "strategy_profile_id": "noop",
                "strategy_implementation_lineage": {
                    **implementation_lineage().model_dump(mode="json"),
                    "import_path": "malicious.module:factory",
                },
                "risk_profile_id": "noop",
                "risk_implementation_lineage": implementation_lineage(
                    kind="risk", suffix="risk"
                ).model_dump(mode="json"),
                "asset_class": "stock",
                "symbols": ["AAPL"],
                "timeframe": "1Min",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T01:00:00Z",
            }
        )
