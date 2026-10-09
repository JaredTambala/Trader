"""Revisioned public evidence for the UJ-04 model-gate boundary.

This support contract records deterministic lifecycle evidence alongside the
model-gate result that was actually observed. It deliberately cannot represent
controlled acceptance while the repeated real-model gate is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import os
import platform
from typing import Any, Literal, Mapping

from trader_agents import first_slice_programs, first_slice_tool_catalogue
from trader_agents.model_runtime.profiles import DEVELOPMENT_MODEL_PROFILE_ID


UJ04_EVIDENCE_FIXTURE_ID = "uj04-public-session-completed-v1"
UJ04_EVIDENCE_CONTRACT = "UJ04QualificationEvidence"
UJ04_EVIDENCE_CONTRACT_VERSION = "1"
UJ04_FIXTURE_VERSION = "1"
UJ04_VERIFIER_VERSION = "1"
UJ04_QUALIFICATION_COMMAND = (
    "uv run pytest tests/cross_package/qualification/"
    "test_uj04_model_gate_evidence.py -q --basetemp=/tmp/trader-trd315-model-gate"
)

GateStatus = Literal["passed", "failed", "blocked", "not_run"]


@dataclass(frozen=True)
class GateEvidence:
    """Public result for one qualification gate."""

    status: GateStatus
    assertions: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    model_profile_id: str | None = None
    repetitions: int | None = None

    def __post_init__(self) -> None:
        """Reject ambiguous or internally inconsistent gate records."""
        if not self.assertions:
            raise ValueError("gate evidence requires at least one assertion")
        if len(set(self.assertions)) != len(self.assertions):
            raise ValueError("gate assertions must be unique")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("gate blockers must be unique")
        if self.status == "passed" and self.blockers:
            raise ValueError("a passed gate cannot contain blockers")
        if self.status in {"failed", "blocked", "not_run"} and not self.blockers:
            raise ValueError("an unavailable gate must name its blocker")
        if self.repetitions is not None and self.repetitions < 0:
            raise ValueError("gate repetitions cannot be negative")
        for value, label in (
            (self.assertions, "assertions"),
            (self.blockers, "blockers"),
        ):
            if any(not item or len(item) > 240 for item in value):
                raise ValueError(f"{label} must contain bounded non-empty text")

    def to_dict(self) -> dict[str, Any]:
        """Return the credential-free JSON representation."""
        return {
            "status": self.status,
            "assertions": list(self.assertions),
            "blockers": list(self.blockers),
            "model_profile_id": self.model_profile_id,
            "repetitions": self.repetitions,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GateEvidence":
        """Load one closed gate record."""
        expected = {"status", "assertions", "blockers", "model_profile_id", "repetitions"}
        if set(payload) != expected:
            raise ValueError("gate evidence fields do not match the closed contract")
        status = payload["status"]
        if status not in {"passed", "failed", "blocked", "not_run"}:
            raise ValueError("unsupported gate status")
        return cls(
            status=status,
            assertions=_string_tuple(payload["assertions"], "assertions"),
            blockers=_string_tuple(payload["blockers"], "blockers"),
            model_profile_id=_optional_string(payload["model_profile_id"]),
            repetitions=_optional_int(payload["repetitions"]),
        )


@dataclass(frozen=True)
class UJ04QualificationEvidence:
    """Immutable, revisioned evidence for one UJ-04 qualification run."""

    fixture_id: str
    fixture_version: str
    verifier_version: str
    contracts: Mapping[str, str]
    contract_version: str
    qualification_command: str
    checkout_commit: str
    environment: Mapping[str, str]
    evidence_revision: int
    deterministic_gate: GateEvidence
    model_gate: GateEvidence
    repeated_real_model_gate: GateEvidence
    controlled_acceptance: Literal["not_claimed"] = "not_claimed"

    def __post_init__(self) -> None:
        """Enforce identity, revision, and hard acceptance boundaries."""
        if self.fixture_id != UJ04_EVIDENCE_FIXTURE_ID:
            raise ValueError("evidence fixture identity does not match UJ-04")
        if self.fixture_version != UJ04_FIXTURE_VERSION:
            raise ValueError("unsupported UJ-04 fixture version")
        if self.verifier_version != UJ04_VERIFIER_VERSION:
            raise ValueError("unsupported UJ-04 verifier version")
        if self.contract_version != UJ04_EVIDENCE_CONTRACT_VERSION:
            raise ValueError("unsupported UJ-04 evidence contract version")
        if not self.contracts or any(not key or not value for key, value in self.contracts.items()):
            raise ValueError("evidence contracts must be named")
        if not self.qualification_command or not self.checkout_commit:
            raise ValueError("command and checkout commit are required")
        if self.evidence_revision <= 0:
            raise ValueError("evidence_revision must be positive")
        if self.controlled_acceptance != "not_claimed":
            raise ValueError("controlled acceptance is not representable by this contract")
        required_environment = {
            "python_version",
            "platform",
            "model_profile_id",
            "agent_program_id",
            "tool_catalog_id",
        }
        if required_environment - set(self.environment):
            raise ValueError("evidence environment is missing required identity")
        if self.repeated_real_model_gate.status == "passed":
            raise ValueError("repeated real-model acceptance cannot be recorded here")

    def to_dict(self) -> dict[str, Any]:
        """Return a stable, credential-free JSON object."""
        return {
            "fixture_id": self.fixture_id,
            "fixture_version": self.fixture_version,
            "verifier_version": self.verifier_version,
            "contracts": dict(sorted(self.contracts.items())),
            "contract_version": self.contract_version,
            "qualification_command": self.qualification_command,
            "checkout_commit": self.checkout_commit,
            "environment": dict(sorted(self.environment.items())),
            "evidence_revision": self.evidence_revision,
            "deterministic_gate": self.deterministic_gate.to_dict(),
            "model_gate": self.model_gate.to_dict(),
            "repeated_real_model_gate": self.repeated_real_model_gate.to_dict(),
            "controlled_acceptance": self.controlled_acceptance,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UJ04QualificationEvidence":
        """Load one exact evidence revision without compatibility fallbacks."""
        expected = {
            "fixture_id",
            "fixture_version",
            "verifier_version",
            "contracts",
            "contract_version",
            "qualification_command",
            "checkout_commit",
            "environment",
            "evidence_revision",
            "deterministic_gate",
            "model_gate",
            "repeated_real_model_gate",
            "controlled_acceptance",
        }
        if set(payload) != expected:
            raise ValueError("UJ-04 evidence fields do not match the closed contract")
        contracts = payload["contracts"]
        environment = payload["environment"]
        if not isinstance(contracts, Mapping) or not isinstance(environment, Mapping):
            raise ValueError("contracts and environment must be JSON objects")
        return cls(
            fixture_id=_required_string(payload["fixture_id"], "fixture_id"),
            fixture_version=_required_string(payload["fixture_version"], "fixture_version"),
            verifier_version=_required_string(payload["verifier_version"], "verifier_version"),
            contracts={str(key): str(value) for key, value in contracts.items()},
            contract_version=_required_string(payload["contract_version"], "contract_version"),
            qualification_command=_required_string(
                payload["qualification_command"], "qualification_command"
            ),
            checkout_commit=_required_string(payload["checkout_commit"], "checkout_commit"),
            environment={str(key): str(value) for key, value in environment.items()},
            evidence_revision=_required_int(payload["evidence_revision"], "evidence_revision"),
            deterministic_gate=_gate(payload["deterministic_gate"]),
            model_gate=_gate(payload["model_gate"]),
            repeated_real_model_gate=_gate(payload["repeated_real_model_gate"]),
            controlled_acceptance=payload["controlled_acceptance"],
        )


def build_uj04_model_gate_evidence(
    *, checkout_commit: str, evidence_revision: int
) -> UJ04QualificationEvidence:
    """Build the current UJ-04 evidence statement from admitted identities."""
    programs = first_slice_programs().public_manifest()["programs"]
    if not programs:
        raise ValueError("the admitted agent program catalogue is empty")
    return UJ04QualificationEvidence(
        fixture_id=UJ04_EVIDENCE_FIXTURE_ID,
        fixture_version=UJ04_FIXTURE_VERSION,
        verifier_version=UJ04_VERIFIER_VERSION,
        contracts={
            "console": "AgentSessionProjection",
            "agent": "RetainedTrajectory",
            "evidence": UJ04_EVIDENCE_CONTRACT,
        },
        contract_version=UJ04_EVIDENCE_CONTRACT_VERSION,
        qualification_command=UJ04_QUALIFICATION_COMMAND,
        checkout_commit=checkout_commit,
        environment={
            "python_version": platform.python_version(),
            "platform": platform.platform(aliased=True),
            "model_profile_id": DEVELOPMENT_MODEL_PROFILE_ID,
            "agent_program_id": str(programs[0]["program_id"]),
            "tool_catalog_id": first_slice_tool_catalogue().catalogue_id,
        },
        evidence_revision=evidence_revision,
        deterministic_gate=GateEvidence(
            status="passed",
            assertions=(
                "public session and terminal artifact identities agree",
                "concurrent Data and Strategy branches remain attributable",
                "fresh-process retained trajectory replay succeeds",
            ),
        ),
        model_gate=GateEvidence(
            status="failed",
            assertions=(
                "materially ambiguous brief must not produce executable work",
                "strict turn schema must hold before MCP dispatch",
            ),
            blockers=(
                "TRD-100: first supported model profile decision remains unresolved",
                "IMP-05: combined Coordinator model gate is failed",
            ),
            model_profile_id=DEVELOPMENT_MODEL_PROFILE_ID,
        ),
        repeated_real_model_gate=GateEvidence(
            status="not_run",
            assertions=(
                "frozen repeated campaign requires a passing single-run model gate",
            ),
            blockers=(
                "controlled real-model campaign is not promoted while the model gate is failed",
            ),
            model_profile_id=DEVELOPMENT_MODEL_PROFILE_ID,
            repetitions=0,
        ),
    )


def write_uj04_evidence(path: Path, evidence: UJ04QualificationEvidence) -> None:
    """Create one immutable evidence revision, refusing accidental overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(evidence.to_dict(), sort_keys=True, separators=(",", ":"))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.write("\n")
    except BaseException:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def read_uj04_evidence(path: Path) -> UJ04QualificationEvidence:
    """Read and validate one immutable evidence revision."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("UJ-04 evidence must be a JSON object")
    return UJ04QualificationEvidence.from_dict(payload)


def _gate(payload: Any) -> GateEvidence:
    if not isinstance(payload, Mapping):
        raise ValueError("gate evidence must be a JSON object")
    return GateEvidence.from_dict(payload)


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return tuple(value)


def _optional_string(value: Any) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError("optional text must be a string or null")
    return value


def _optional_int(value: Any) -> int | None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValueError("optional repetitions must be an integer or null")
    return value


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _required_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value
