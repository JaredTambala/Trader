"""Typed persisted evidence supplied to the human decision workspace."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import (
    BlockedEvidenceBasisContract,
    NextDecisionArtifactReference,
    SessionReviewLinkContract,
)


class DecisionEvidenceBasis(BaseModel):
    """Canonical references copied unchanged into a human decision command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_run_ref: NextDecisionArtifactReference
    data_ref: NextDecisionArtifactReference
    implementation_refs: tuple[NextDecisionArtifactReference, ...] = Field(min_length=1)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    review_refs: tuple[NextDecisionArtifactReference, ...] = ()
    session_review: SessionReviewLinkContract | None = None
    blocked_evidence: BlockedEvidenceBasisContract | None = None


class DecisionBasisResponse(BaseModel):
    """Read-only evidence availability, identity and permitted human outcomes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    status: Literal["available", "unavailable", "incompatible"]
    reason: str
    evidence: DecisionEvidenceBasis | None = None
    permitted_outcomes: tuple[Literal["reject", "refine", "continue"], ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_available_evidence(self) -> "DecisionBasisResponse":
        """Never expose actions without a verified persisted evidence basis."""
        if self.status == "available" and (self.evidence is None or not self.permitted_outcomes):
            raise ValueError("available decision basis requires evidence and permitted outcomes")
        if self.status != "available" and (self.evidence is not None or self.permitted_outcomes):
            raise ValueError("unavailable or incompatible decision basis cannot expose actions")
        return self
