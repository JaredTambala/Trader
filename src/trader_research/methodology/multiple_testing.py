"""Multiple-testing controls for declared signal candidate families."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.foundation import ApplicationResult, error_result, stable_research_id, success_result
from trader_research.foundation.artifacts import ArtifactReference
from trader_research.knowledge.approved_cards import ApprovedMethodCardReadError, ApprovedMethodCardReader
from trader_research.methodology.contracts import MethodContract
from trader_research.methodology.implementation.io import write_json_artifact
from trader_research.methodology.registry import get_method


MATH_RUN_MULTIPLE_TESTING_REPORT = "math_run_multiple_testing_report"
MULTIPLE_TESTING_SCHEMA_VERSION = "1"


@dataclass
class _Issues:
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)

    def unique_warnings(self) -> list[str]:
        return list(dict.fromkeys(self.warnings))

    def unique_blockers(self) -> list[str]:
        return list(dict.fromkeys(self.blockers))


@dataclass(frozen=True)
class _CandidateFamily:
    candidate_family_id: str
    candidate_ids: tuple[str, ...]
    tested_grid: Mapping[str, Any]

    @property
    def candidate_count(self) -> int:
        return len(self.candidate_ids)


@dataclass(frozen=True)
class _MetricRow:
    candidate_id: str
    raw_p_value: float
    metric_name: str
    metric_value: float | None
    horizon: Any


@dataclass(frozen=True)
class _BenjaminiHochbergResult:
    candidate_id: str
    rank: int
    metric_name: str
    metric_value: float | None
    horizon: Any
    raw_p_value: float
    adjusted_p_value: float
    rejected: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "rank": self.rank,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "horizon": self.horizon,
            "raw_p_value": self.raw_p_value,
            "adjusted_p_value": self.adjusted_p_value,
            "rejected": self.rejected,
        }


def run_multiple_testing_report(
    *,
    artifact_root: str | Path,
    candidate_family_manifest: Mapping[str, Any],
    metric_matrix: Sequence[Mapping[str, Any]],
    method_contract: Mapping[str, Any],
    alpha: float | None = None,
    approved_card_reader: ApprovedMethodCardReader | None = None,
) -> ApplicationResult:
    """Apply Benjamini-Hochberg correction across one signal family.

    Args:
        artifact_root: Directory where the JSON report artifact is written.
        candidate_family_manifest: Declared signal candidate family, including
            the tested grid and candidate identifiers that define the correction
            universe.
        metric_matrix: Candidate-level p-values produced by an upstream signal
            diagnostic report.
        method_contract: Benjamini-Hochberg method contract with approved
            method-card evidence.
        alpha: Optional correction threshold override. When omitted, the value
            is read from the method contract parameters.
        approved_card_reader: Read-only approved-card evidence dependency.

    Returns:
        A Quantitative Methods `ApplicationResult` and a persisted
        `multiple_testing_report.json` artifact. Validation failures are
        returned as a failed result with blockers embedded in the artifact.
    """
    issues = _Issues()
    family = _candidate_family_from_manifest(candidate_family_manifest, issues)
    contract = MethodContract.from_mapping(method_contract)
    checked_alpha = _alpha_from_contract(contract, alpha, issues)
    _validate_bh_contract(
        contract=contract,
        issues=issues,
        approved_card_reader=approved_card_reader,
    )
    metric_rows = _metric_rows_from_matrix(metric_matrix, family.candidate_ids, issues)
    _validate_metric_coverage(family, metric_rows, issues)
    corrected_rows = _benjamini_hochberg(metric_rows, checked_alpha) if not issues.blocked else ()
    report = _build_report(
        candidate_family_manifest=candidate_family_manifest,
        family=family,
        alpha=checked_alpha,
        corrected_rows=corrected_rows,
        issues=issues,
    )
    return _persist_report(artifact_root, report, issues)


def _candidate_family_from_manifest(
    manifest: Mapping[str, Any],
    issues: _Issues,
) -> _CandidateFamily:
    family_id = str(manifest.get("candidate_family_id") or "").strip()
    if not family_id:
        issues.blockers.append("candidate_family_manifest.candidate_family_id is required")

    candidate_ids = []
    for item in _sequence(manifest.get("candidates")):
        if not isinstance(item, Mapping):
            issues.blockers.append("candidate_family_manifest.candidates must contain objects")
            continue
        candidate_id = str(item.get("candidate_id") or "").strip()
        if not candidate_id:
            issues.blockers.append("candidate candidate_id is required")
            continue
        candidate_ids.append(candidate_id)

    if not candidate_ids:
        issues.blockers.append("candidate_family_manifest.candidates is required")
    for candidate_id in _duplicates(candidate_ids):
        issues.blockers.append(f"duplicate candidate_id in candidate family: {candidate_id}")

    tested_grid = _mapping_or_empty(manifest.get("tested_grid"))
    return _CandidateFamily(
        candidate_family_id=family_id,
        candidate_ids=tuple(candidate_ids),
        tested_grid=tested_grid,
    )


def _alpha_from_contract(
    contract: MethodContract,
    override: float | None,
    issues: _Issues,
) -> float:
    raw_alpha = override if override is not None else contract.parameters.get("alpha")
    alpha = _finite_float(raw_alpha)
    if alpha is None:
        issues.blockers.append("alpha is required")
        return 0.05
    if alpha <= 0.0 or alpha > 1.0:
        issues.blockers.append("alpha must be greater than 0 and less than or equal to 1")
    return alpha


def _validate_bh_contract(
    *,
    contract: MethodContract,
    issues: _Issues,
    approved_card_reader: ApprovedMethodCardReader | None,
) -> None:
    if contract.method_id != "benjamini_hochberg":
        issues.blockers.append("method_contract.method_id must be benjamini_hochberg")
        return

    entry = get_method("benjamini_hochberg")
    if entry is None:
        issues.blockers.append("unsupported method_id: benjamini_hochberg")
        return

    method_card_ids = _method_card_ids(contract)
    if not method_card_ids:
        issues.blockers.append("approved method-card evidence is required for benjamini_hochberg")
        return

    if approved_card_reader is None:
        issues.blockers.append("approved method-card reader is required")
        return
    try:
        approved = approved_card_reader.has_approved_method_card(
            method_card_ids,
            method_id="benjamini_hochberg",
        )
    except ApprovedMethodCardReadError as exc:
        issues.blockers.append(str(exc))
        return
    if not approved:
        issues.blockers.append("approved method-card evidence does not match benjamini_hochberg")
        return



def _metric_rows_from_matrix(
    metric_matrix: Sequence[Mapping[str, Any]],
    candidate_ids: Sequence[str],
    issues: _Issues,
) -> tuple[_MetricRow, ...]:
    rows = []
    seen_candidate_ids: set[str] = set()
    known_candidate_ids = set(candidate_ids)
    for row in metric_matrix:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            issues.blockers.append("metric rows require candidate_id")
            continue
        if candidate_id not in known_candidate_ids:
            issues.blockers.append(f"metric row references unknown candidate_id: {candidate_id}")
            continue
        if candidate_id in seen_candidate_ids:
            issues.blockers.append(f"duplicate metric row candidate_id: {candidate_id}")
            continue
        seen_candidate_ids.add(candidate_id)

        p_value = _finite_float(row.get("p_value", row.get("raw_p_value")))
        if p_value is None or p_value < 0.0 or p_value > 1.0:
            issues.blockers.append(f"invalid p-value for candidate_id: {candidate_id}")
            continue
        rows.append(
            _MetricRow(
                candidate_id=candidate_id,
                raw_p_value=p_value,
                metric_name=str(row.get("metric_name") or "rank_ic_p_value"),
                metric_value=_finite_float(row.get("metric_value")),
                horizon=row.get("horizon"),
            )
        )

    if not rows:
        issues.blockers.append("metric_matrix must contain candidate p-values")
    return tuple(rows)


def _validate_metric_coverage(
    family: _CandidateFamily,
    metric_rows: Sequence[_MetricRow],
    issues: _Issues,
) -> None:
    row_candidate_ids = {row.candidate_id for row in metric_rows}
    for candidate_id in sorted(set(family.candidate_ids) - row_candidate_ids):
        issues.blockers.append(f"candidate family member is missing a p-value: {candidate_id}")


def _benjamini_hochberg(
    rows: Sequence[_MetricRow],
    alpha: float,
) -> tuple[_BenjaminiHochbergResult, ...]:
    ordered_rows = sorted(rows, key=lambda row: (row.raw_p_value, row.candidate_id))
    adjusted_by_candidate_id = _adjusted_p_values_by_candidate_id(ordered_rows)
    return tuple(
        _BenjaminiHochbergResult(
            candidate_id=row.candidate_id,
            rank=rank,
            metric_name=row.metric_name,
            metric_value=row.metric_value,
            horizon=row.horizon,
            raw_p_value=row.raw_p_value,
            adjusted_p_value=adjusted_by_candidate_id[row.candidate_id],
            rejected=adjusted_by_candidate_id[row.candidate_id] <= alpha,
        )
        for rank, row in enumerate(ordered_rows, start=1)
    )


def _adjusted_p_values_by_candidate_id(
    ordered_rows: Sequence[_MetricRow],
) -> dict[str, float]:
    candidate_count = len(ordered_rows)
    adjusted_by_candidate_id: dict[str, float] = {}
    running_minimum = 1.0
    for rank_index in range(candidate_count, 0, -1):
        row = ordered_rows[rank_index - 1]
        adjusted = min(running_minimum, row.raw_p_value * candidate_count / rank_index, 1.0)
        running_minimum = adjusted
        adjusted_by_candidate_id[row.candidate_id] = adjusted
    return adjusted_by_candidate_id


def _build_report(
    *,
    candidate_family_manifest: Mapping[str, Any],
    family: _CandidateFamily,
    alpha: float,
    corrected_rows: Sequence[_BenjaminiHochbergResult],
    issues: _Issues,
) -> dict[str, Any]:
    result_payloads = [row.to_payload() for row in corrected_rows]
    multiple_testing_id = stable_research_id(
        "multiple_testing",
        {
            "candidate_family_id": family.candidate_family_id,
            "alpha": alpha,
            "result_rows": result_payloads,
            "warnings": issues.unique_warnings(),
            "blockers": issues.unique_blockers(),
        },
    )
    return {
        "artifact_type": "multiple_testing_report",
        "schema_version": MULTIPLE_TESTING_SCHEMA_VERSION,
        "multiple_testing_id": multiple_testing_id,
        "candidate_family_id": family.candidate_family_id,
        "candidate_family_manifest": dict(candidate_family_manifest),
        "candidate_count": family.candidate_count,
        "tested_grid": dict(family.tested_grid),
        "correction_method": "benjamini_hochberg",
        "alpha": alpha,
        "status": "blocked" if issues.blocked else "completed",
        "results": result_payloads,
        "accepted_candidate_ids": [row.candidate_id for row in corrected_rows if row.rejected],
        "rejected_candidate_ids": [row.candidate_id for row in corrected_rows if not row.rejected],
        "warnings": issues.unique_warnings(),
        "blockers": issues.unique_blockers(),
    }


def _persist_report(
    artifact_root: str | Path,
    report: Mapping[str, Any],
    issues: _Issues,
) -> ApplicationResult:
    report_path = Path(artifact_root) / "multiple_testing" / f"{report['multiple_testing_id']}.json"
    write_json_artifact(report, report_path)
    data = {"multiple_testing_report": report}
    artifacts = {
        "multiple_testing_report": ArtifactReference(
            artifact_type="multiple_testing_report",
            path=report_path,
            metadata={"id": report["multiple_testing_id"]},
        ).to_dict()
    }
    if issues.blocked:
        return error_result(
            command=MATH_RUN_MULTIPLE_TESTING_REPORT,
            code="multiple_testing_failed",
            message="multiple-testing report failed",
            data={**data, "artifacts": artifacts},
        )
    return success_result(
        command=MATH_RUN_MULTIPLE_TESTING_REPORT,
        data=data,
        artifacts=artifacts,
        warnings=tuple(issues.unique_warnings()),
    )


def _method_card_ids(contract: MethodContract) -> tuple[str, ...]:
    return tuple(
        str(ref["method_card_id"])
        for ref in contract.knowledge_evidence_refs
        if ref.get("method_card_id") is not None
    )


def _duplicates(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if values.count(value) > 1}))


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return value
    return (value,)


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _finite_float(value: Any) -> float | None:
    try:
        if isinstance(value, bool):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed
