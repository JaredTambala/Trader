"""Signal-composition diagnostics for Quantitative Methods workflows."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.contracts import (
    ArtifactReference,
    SideEffect,
    ToolEnvelope,
    error_envelope,
    success_envelope,
    write_json_artifact,
)
from trader_research.domain import stable_research_id
from trader_research.knowledge.citation_validation import validate_citations
from trader_research.knowledge.method_cards import has_approved_method_card
from trader_research.knowledge.store import KnowledgeStore, KnowledgeStoreError
from trader_research.math_domain import MethodContract
from trader_research.math_registry import get_method
from trader_research.method_implementations.io import load_manifest
from trader_research.method_implementations.manifest import (
    MethodImplementationManifest,
    SIGNAL_RUNTIME_CONTRACT,
)


MATH_RUN_SIGNAL_DIAGNOSTICS = "math_run_signal_diagnostics"
SIGNAL_DIAGNOSTIC_SCHEMA_VERSION = "1"


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
class _Candidate:
    candidate_id: str
    signal_name: str
    parameters: Mapping[str, Any]
    implementation_id: str | None = None
    implementation_manifest: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class _CandidateFamily:
    candidate_family_id: str
    candidates: tuple[_Candidate, ...]
    tested_grid: Mapping[str, Any]

    @property
    def candidate_ids(self) -> frozenset[str]:
        return frozenset(candidate.candidate_id for candidate in self.candidates)

    def to_payload(self, original: Mapping[str, Any]) -> dict[str, Any]:
        return dict(original)


@dataclass(frozen=True)
class _SignalObservation:
    candidate_id: str
    signal_name: str
    symbol: str
    ts: str
    value: float
    session: str | None = None
    regime: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        return self.candidate_id, self.symbol, self.ts


@dataclass(frozen=True)
class _ForwardReturnLabel:
    symbol: str
    ts: str
    horizon: int
    forward_return: float

    @property
    def observation_key(self) -> tuple[str, str]:
        return self.symbol, self.ts

    @property
    def label_key(self) -> tuple[str, str, int]:
        return self.symbol, self.ts, self.horizon


@dataclass(frozen=True)
class _AlignedPair:
    candidate_id: str
    signal_name: str
    symbol: str
    ts: str
    value: float
    horizon: int
    forward_return: float
    session: str | None = None
    regime: str | None = None


@dataclass(frozen=True)
class _ImplementationRef:
    candidate_id: str
    implementation_id: str
    method_id: str
    status: str
    runtime_contract: str
    source_hash: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "implementation_id": self.implementation_id,
            "method_id": self.method_id,
            "status": self.status,
            "runtime_contract": self.runtime_contract,
            "source_hash": self.source_hash,
        }


def run_signal_diagnostics(
    *,
    artifact_root: str | Path,
    signal_observations: Sequence[Mapping[str, Any]],
    forward_return_labels: Sequence[Mapping[str, Any]],
    candidate_family_manifest: Mapping[str, Any],
    method_contracts: Sequence[Mapping[str, Any]],
    quantile_count: int = 5,
    data_quality_report: Mapping[str, Any] | None = None,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Produce diagnostics for declared signal compositions against labels.

    Args:
        artifact_root: Directory where the report artifact is written.
        signal_observations: Candidate signal outputs keyed by candidate, symbol,
            timestamp, and numeric trade-intent value.
        forward_return_labels: Forward returns keyed by symbol, timestamp, and
            horizon.
        candidate_family_manifest: Declared candidate family and tested grid.
        method_contracts: Rank-IC contracts with approved method-card evidence.
        quantile_count: Desired bucket count for continuous signals, clamped to
            the supported range of 2-10.
        data_quality_report: Optional upstream data-quality context.
        knowledge_store: Optional injected knowledge store for citation checks.

    Returns:
        A Quantitative Methods `ToolEnvelope` and a persisted
        `signal_diagnostic_report.json` artifact.
    """
    issues = _Issues()
    family = _candidate_family_from_manifest(candidate_family_manifest, issues)
    observations = _signal_observations_from_rows(signal_observations, family.candidate_ids, issues)
    labels = _forward_labels_from_rows(forward_return_labels, issues)
    pairs = _align_observations_to_labels(observations, labels, issues)
    _validate_rank_ic_contracts(
        artifact_root=artifact_root,
        method_contracts=method_contracts,
        horizons=sorted({pair.horizon for pair in pairs}),
        issues=issues,
        knowledge_store=knowledge_store,
    )
    implementation_refs = _implementation_refs(artifact_root, family.candidates, issues)
    if data_quality_report is not None and _data_quality_has_warnings(data_quality_report):
        issues.warnings.append("data_quality_report contains warnings or incomplete coverage")

    report = _build_report(
        original_family_manifest=candidate_family_manifest,
        family=family,
        observations=observations,
        pairs=pairs,
        implementation_refs=implementation_refs,
        quantile_count=max(2, min(int(quantile_count), 10)),
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

    candidates = []
    candidate_ids = []
    for item in _sequence(manifest.get("candidates")):
        if not isinstance(item, Mapping):
            issues.blockers.append("candidate_family_manifest.candidates must contain objects")
            continue
        candidate_id = str(item.get("candidate_id") or "").strip()
        if not candidate_id:
            issues.blockers.append("candidate candidate_id is required")
            continue
        candidate = _Candidate(
            candidate_id=candidate_id,
            signal_name=str(item.get("signal_name") or candidate_id),
            parameters=_mapping_or_empty(item.get("parameters")),
            implementation_id=str(item["implementation_id"]) if item.get("implementation_id") is not None else None,
            implementation_manifest=item.get("implementation_manifest")
            if isinstance(item.get("implementation_manifest"), Mapping)
            else None,
        )
        candidates.append(candidate)
        candidate_ids.append(candidate_id)

    if not candidates:
        issues.blockers.append("candidate_family_manifest.candidates is required")
    for candidate_id in _duplicates(candidate_ids):
        issues.blockers.append(f"duplicate candidate_id in candidate family: {candidate_id}")

    tested_grid = _mapping_or_empty(manifest.get("tested_grid"))
    return _CandidateFamily(
        candidate_family_id=family_id,
        candidates=tuple(candidates),
        tested_grid=tested_grid,
    )


def _signal_observations_from_rows(
    rows: Sequence[Mapping[str, Any]],
    candidate_ids: frozenset[str],
    issues: _Issues,
) -> tuple[_SignalObservation, ...]:
    observations = []
    seen_keys: set[tuple[str, str, str]] = set()
    for row in rows:
        observation = _signal_observation_from_row(row, candidate_ids, issues)
        if observation is None:
            continue
        if observation.key in seen_keys:
            issues.blockers.append(
                "duplicate signal observation key: "
                f"{observation.candidate_id}/{observation.symbol}/{observation.ts}"
            )
            continue
        seen_keys.add(observation.key)
        observations.append(observation)

    if not observations:
        issues.blockers.append("at least one valid signal observation is required")
    if len(observations) < len(rows):
        issues.warnings.append("some signal observations were rejected during validation")
    return tuple(observations)


def _signal_observation_from_row(
    row: Mapping[str, Any],
    candidate_ids: frozenset[str],
    issues: _Issues,
) -> _SignalObservation | None:
    candidate_id = str(row.get("candidate_id") or "").strip()
    symbol = str(row.get("symbol") or "").strip()
    ts = _timestamp_text(row.get("ts"))
    value = _finite_float(row.get("value"))
    if not candidate_id or not symbol or not ts:
        issues.blockers.append("signal observations require candidate_id, symbol, and ts")
        return None
    if candidate_ids and candidate_id not in candidate_ids:
        issues.blockers.append(f"signal observation references unknown candidate_id: {candidate_id}")
        return None
    if value is None:
        issues.blockers.append(
            f"signal observation has non-finite value for candidate_id={candidate_id} symbol={symbol} ts={ts}"
        )
        return None
    return _SignalObservation(
        candidate_id=candidate_id,
        signal_name=str(row.get("signal_name") or candidate_id),
        symbol=symbol,
        ts=ts,
        value=value,
        session=str(row["session"]) if row.get("session") is not None else None,
        regime=str(row["regime"]) if row.get("regime") is not None else None,
        metadata=_mapping_or_empty(row.get("metadata")),
    )


def _forward_labels_from_rows(
    rows: Sequence[Mapping[str, Any]],
    issues: _Issues,
) -> Mapping[tuple[str, str], tuple[_ForwardReturnLabel, ...]]:
    labels_by_observation: dict[tuple[str, str], list[_ForwardReturnLabel]] = defaultdict(list)
    seen_keys: set[tuple[str, str, int]] = set()
    for row in rows:
        label = _forward_label_from_row(row, issues)
        if label is None:
            continue
        if label.label_key in seen_keys:
            issues.blockers.append(
                f"duplicate forward return label key: {label.symbol}/{label.ts}/{label.horizon}"
            )
            continue
        seen_keys.add(label.label_key)
        labels_by_observation[label.observation_key].append(label)

    if not labels_by_observation:
        issues.blockers.append("at least one valid forward return label is required")
    return {key: tuple(value) for key, value in labels_by_observation.items()}


def _forward_label_from_row(
    row: Mapping[str, Any],
    issues: _Issues,
) -> _ForwardReturnLabel | None:
    symbol = str(row.get("symbol") or "").strip()
    ts = _timestamp_text(row.get("ts"))
    horizon = _int_value(row.get("horizon"))
    forward_return = _finite_float(row.get("forward_return"))
    if not symbol or not ts or horizon is None:
        issues.blockers.append("forward return labels require symbol, ts, and horizon")
        return None
    if horizon < 1:
        issues.blockers.append("forward return label horizon must be positive")
        return None
    if forward_return is None:
        issues.blockers.append(
            f"forward return label has non-finite value for symbol={symbol} ts={ts} horizon={horizon}"
        )
        return None
    return _ForwardReturnLabel(
        symbol=symbol,
        ts=ts,
        horizon=horizon,
        forward_return=forward_return,
    )


def _align_observations_to_labels(
    observations: Sequence[_SignalObservation],
    labels: Mapping[tuple[str, str], Sequence[_ForwardReturnLabel]],
    issues: _Issues,
) -> tuple[_AlignedPair, ...]:
    pairs = []
    missing_count = 0
    for observation in observations:
        matching_labels = labels.get((observation.symbol, observation.ts), ())
        if not matching_labels:
            missing_count += 1
            continue
        for label in matching_labels:
            pairs.append(
                _AlignedPair(
                    candidate_id=observation.candidate_id,
                    signal_name=observation.signal_name,
                    symbol=observation.symbol,
                    ts=observation.ts,
                    value=observation.value,
                    session=observation.session,
                    regime=observation.regime,
                    horizon=label.horizon,
                    forward_return=label.forward_return,
                )
            )
    if missing_count:
        issues.warnings.append(f"{missing_count} signal observations had no matching forward-return label")
    if not pairs:
        issues.blockers.append("no aligned signal observations and forward-return labels")
    return tuple(pairs)


def _validate_rank_ic_contracts(
    *,
    artifact_root: str | Path,
    method_contracts: Sequence[Mapping[str, Any]],
    horizons: Sequence[int],
    issues: _Issues,
    knowledge_store: KnowledgeStore | None,
) -> None:
    contracts_by_horizon = _rank_ic_contracts_by_horizon(method_contracts)
    for horizon in horizons:
        contract = contracts_by_horizon.get(horizon)
        if contract is None:
            issues.blockers.append(f"rank_ic method contract is required for horizon {horizon}")
            continue
        _validate_contract_evidence(
            artifact_root=artifact_root,
            contract=contract,
            expected_method_id="rank_ic",
            issues=issues,
            knowledge_store=knowledge_store,
        )


def _rank_ic_contracts_by_horizon(
    method_contracts: Sequence[Mapping[str, Any]],
) -> dict[int, MethodContract]:
    contracts = {}
    for payload in method_contracts:
        contract = MethodContract.from_mapping(payload)
        if contract.method_id != "rank_ic":
            continue
        horizon = _int_value(contract.parameters.get("horizon"))
        if horizon is not None:
            contracts[horizon] = contract
    return contracts


def _validate_contract_evidence(
    *,
    artifact_root: str | Path,
    contract: MethodContract,
    expected_method_id: str,
    issues: _Issues,
    knowledge_store: KnowledgeStore | None,
) -> None:
    try:
        entry = get_method(expected_method_id, knowledge_store=knowledge_store)
    except KnowledgeStoreError as exc:
        issues.blockers.append(str(exc))
        return
    if entry is None:
        issues.blockers.append(f"unsupported method_id: {expected_method_id}")
        return

    for name, spec in {spec.name: spec for spec in entry.parameters}.items():
        if spec.required and name not in contract.parameters:
            issues.blockers.append(f"missing required parameter: {name}")
            continue
        if name in contract.parameters:
            _validate_numeric_parameter(name, contract.parameters[name], spec.min_value, spec.max_value, issues)

    method_card_ids = _method_card_ids(contract)
    if not method_card_ids:
        issues.blockers.append(f"approved method-card evidence is required for {expected_method_id}")
        return
    try:
        approved = has_approved_method_card(
            artifact_root,
            method_card_ids,
            knowledge_store=knowledge_store,
            method_id=expected_method_id,
        )
    except KnowledgeStoreError as exc:
        issues.blockers.append(str(exc))
        return
    if not approved:
        issues.blockers.append(f"approved method-card evidence does not match {expected_method_id}")
        return
    if entry.approved_method_card_ids and not set(method_card_ids).intersection(entry.approved_method_card_ids):
        issues.warnings.append(f"method-card evidence for {expected_method_id} is not in the seeded registry allowlist")
    citation_result = validate_citations(
        artifact_root=artifact_root,
        artifact=contract.to_dict(),
        require_approved_method_card=True,
        knowledge_store=knowledge_store,
    )
    if not citation_result.ok:
        issues.blockers.append(f"knowledge citation validation failed for {expected_method_id}")


def _validate_numeric_parameter(
    name: str,
    raw_value: Any,
    min_value: float | None,
    max_value: float | None,
    issues: _Issues,
) -> None:
    value = _finite_float(raw_value)
    if value is None:
        issues.blockers.append(f"invalid parameter: {name}")
        return
    if min_value is not None and value < min_value:
        issues.blockers.append(f"parameter {name} is below minimum {min_value}")
    if max_value is not None and value > max_value:
        issues.blockers.append(f"parameter {name} is above maximum {max_value}")


def _implementation_refs(
    artifact_root: str | Path,
    candidates: Sequence[_Candidate],
    issues: _Issues,
) -> tuple[_ImplementationRef, ...]:
    refs = []
    for candidate in candidates:
        manifest = _implementation_manifest_for_candidate(artifact_root, candidate, issues)
        if manifest is None:
            continue
        if manifest.status != "validated":
            issues.blockers.append(f"candidate {candidate.candidate_id} implementation is not validated")
        if manifest.runtime_contract != SIGNAL_RUNTIME_CONTRACT:
            issues.blockers.append(f"candidate {candidate.candidate_id} implementation is not a Signal runtime contract")
        refs.append(
            _ImplementationRef(
                candidate_id=candidate.candidate_id,
                implementation_id=manifest.implementation_id,
                method_id=manifest.method_id,
                status=manifest.status,
                runtime_contract=manifest.runtime_contract,
                source_hash=manifest.source_hash,
            )
        )
    return tuple(refs)


def _implementation_manifest_for_candidate(
    artifact_root: str | Path,
    candidate: _Candidate,
    issues: _Issues,
) -> MethodImplementationManifest | None:
    if candidate.implementation_manifest is not None:
        return MethodImplementationManifest.from_dict(candidate.implementation_manifest)
    if candidate.implementation_id is None:
        issues.warnings.append(
            f"candidate {candidate.candidate_id} has no executable implementation reference; treating as observational"
        )
        return None
    try:
        return load_manifest(artifact_root, candidate.implementation_id)
    except (FileNotFoundError, ValueError) as exc:
        issues.blockers.append(f"candidate {candidate.candidate_id} implementation manifest could not be loaded: {exc}")
        return None


def _build_report(
    *,
    original_family_manifest: Mapping[str, Any],
    family: _CandidateFamily,
    observations: Sequence[_SignalObservation],
    pairs: Sequence[_AlignedPair],
    implementation_refs: Sequence[_ImplementationRef],
    quantile_count: int,
    issues: _Issues,
) -> dict[str, Any]:
    candidate_results = _candidate_results(family.candidates, observations, pairs, quantile_count)
    diagnostic_id = stable_research_id(
        "signal_diagnostic",
        {
            "candidate_family_id": family.candidate_family_id,
            "candidate_results": candidate_results,
            "warnings": issues.unique_warnings(),
            "blockers": issues.unique_blockers(),
        },
    )
    return {
        "artifact_type": "signal_diagnostic_report",
        "schema_version": SIGNAL_DIAGNOSTIC_SCHEMA_VERSION,
        "diagnostic_id": diagnostic_id,
        "candidate_family_id": family.candidate_family_id,
        "candidate_family_manifest": family.to_payload(original_family_manifest),
        "candidate_count": len(family.candidates),
        "tested_grid": dict(family.tested_grid),
        "status": "blocked" if issues.blocked else "completed",
        "input_counts": {
            "signal_observations": len(observations),
            "aligned_pairs": len(pairs),
        },
        "implementation_refs": [ref.to_payload() for ref in implementation_refs],
        "candidate_results": candidate_results,
        "warnings": issues.unique_warnings(),
        "blockers": issues.unique_blockers(),
    }


def _candidate_results(
    candidates: Sequence[_Candidate],
    observations: Sequence[_SignalObservation],
    pairs: Sequence[_AlignedPair],
    quantile_count: int,
) -> list[dict[str, Any]]:
    observations_by_candidate = _group_by_candidate(observations)
    pairs_by_candidate = _group_pairs_by_candidate(pairs)
    results = []
    for candidate in candidates:
        candidate_observations = observations_by_candidate.get(candidate.candidate_id, ())
        candidate_pairs = pairs_by_candidate.get(candidate.candidate_id, ())
        results.append(
            {
                "candidate_id": candidate.candidate_id,
                "signal_name": candidate.signal_name,
                "parameters": dict(candidate.parameters),
                "observation_count": len(candidate_observations),
                "aligned_pair_count": len(candidate_pairs),
                "turnover_proxy": _turnover_proxy(candidate_observations),
                "horizon_results": _horizon_results(candidate_pairs, quantile_count),
            }
        )
    return results


def _horizon_results(
    pairs: Sequence[_AlignedPair],
    quantile_count: int,
) -> list[dict[str, Any]]:
    results = []
    for horizon, horizon_pairs in sorted(_group_pairs_by_horizon(pairs).items()):
        results.append(_horizon_result(horizon, horizon_pairs, quantile_count))
    return results


def _horizon_result(
    horizon: int,
    pairs: Sequence[_AlignedPair],
    quantile_count: int,
) -> dict[str, Any]:
    values = [pair.value for pair in pairs]
    returns = [pair.forward_return for pair in pairs]
    rank_ic = _pearson(_ranks(values), _ranks(returns))
    discrete = _is_discrete_action(values)
    quantile_buckets = [] if discrete else _quantile_buckets(values, returns, quantile_count)
    warnings = []
    if len(pairs) < 4:
        warnings.append("small sample size; p-value omitted or approximate")
    if discrete:
        warnings.append("discrete action signal; quantile monotonicity skipped")
    return {
        "horizon": horizon,
        "sample_size": len(pairs),
        "ic": _pearson(values, returns),
        "rank_ic": rank_ic,
        "rank_ic_p_value": _correlation_p_value(rank_ic, len(pairs)),
        "hit_rate": _hit_rate(values, returns),
        "coverage": len(pairs),
        "action_conditioned_returns": _action_conditioned_returns(values, returns),
        "quantile_buckets": quantile_buckets,
        "monotonicity_score": None if discrete else _monotonicity_score(quantile_buckets),
        "breakdowns": {
            "symbol": _breakdown(pairs, "symbol"),
            "session": _breakdown(pairs, "session"),
            "regime": _breakdown(pairs, "regime"),
        },
        "warnings": warnings,
    }


def _persist_report(
    artifact_root: str | Path,
    report: Mapping[str, Any],
    issues: _Issues,
) -> ToolEnvelope:
    report_path = Path(artifact_root) / "signal_diagnostics" / f"{report['diagnostic_id']}.json"
    write_json_artifact(report, report_path)
    data = {"signal_diagnostic_report": report}
    artifacts = {
        "signal_diagnostic_report": ArtifactReference(
            artifact_type="signal_diagnostic_report",
            path=report_path,
            metadata={"id": report["diagnostic_id"]},
        ).to_dict()
    }
    if issues.blocked:
        return error_envelope(
            command=MATH_RUN_SIGNAL_DIAGNOSTICS,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="signal_diagnostic_failed",
            message="signal diagnostics failed",
            data={**data, "artifacts": artifacts},
        )
    return success_envelope(
        command=MATH_RUN_SIGNAL_DIAGNOSTICS,
        side_effect=SideEffect.LOCAL_MUTATING,
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


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    centered_x = [x - mean_x for x in xs]
    centered_y = [y - mean_y for y in ys]
    denom_x = sum(x * x for x in centered_x)
    denom_y = sum(y * y for y in centered_y)
    if denom_x <= 0.0 or denom_y <= 0.0:
        return None
    return sum(x * y for x, y in zip(centered_x, centered_y, strict=False)) / math.sqrt(denom_x * denom_y)


def _ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted((value, index) for index, value in enumerate(values))
    ranks = [0.0] * len(values)
    position = 0
    while position < len(indexed):
        end = position + 1
        while end < len(indexed) and indexed[end][0] == indexed[position][0]:
            end += 1
        average_rank = (position + 1 + end) / 2.0
        for _, original_index in indexed[position:end]:
            ranks[original_index] = average_rank
        position = end
    return ranks


def _correlation_p_value(correlation: float | None, sample_size: int) -> float | None:
    if correlation is None or sample_size < 4:
        return None
    clipped = max(min(correlation, 0.999999999999), -0.999999999999)
    z_score = abs(math.atanh(clipped) * math.sqrt(sample_size - 3))
    return math.erfc(z_score / math.sqrt(2.0))


def _hit_rate(values: Sequence[float], returns: Sequence[float]) -> float | None:
    decisions = tuple(
        (value, forward_return)
        for value, forward_return in zip(values, returns, strict=False)
        if value != 0.0 and forward_return != 0.0
    )
    if not decisions:
        return None
    hits = sum(1 for value, forward_return in decisions if math.copysign(1.0, value) == math.copysign(1.0, forward_return))
    return hits / len(decisions)


def _action_conditioned_returns(
    values: Sequence[float],
    returns: Sequence[float],
) -> dict[str, dict[str, float | int | None]]:
    grouped: dict[str, list[float]] = {"short": [], "flat": [], "long": []}
    for value, forward_return in zip(values, returns, strict=False):
        if value < 0.0:
            grouped["short"].append(forward_return)
        elif value > 0.0:
            grouped["long"].append(forward_return)
        else:
            grouped["flat"].append(forward_return)
    return {
        name: {
            "count": len(items),
            "mean_forward_return": sum(items) / len(items) if items else None,
        }
        for name, items in grouped.items()
    }


def _quantile_buckets(
    values: Sequence[float],
    returns: Sequence[float],
    quantile_count: int,
) -> list[dict[str, Any]]:
    ordered = sorted(zip(values, returns, strict=False), key=lambda item: item[0])
    buckets = []
    for bucket_index in range(quantile_count):
        start = bucket_index * len(ordered) // quantile_count
        end = (bucket_index + 1) * len(ordered) // quantile_count
        bucket = ordered[start:end]
        if not bucket:
            continue
        bucket_values = [item[0] for item in bucket]
        bucket_returns = [item[1] for item in bucket]
        buckets.append(
            {
                "bucket": bucket_index + 1,
                "count": len(bucket),
                "min_signal": min(bucket_values),
                "max_signal": max(bucket_values),
                "mean_signal": sum(bucket_values) / len(bucket_values),
                "mean_forward_return": sum(bucket_returns) / len(bucket_returns),
            }
        )
    return buckets


def _monotonicity_score(buckets: Sequence[Mapping[str, Any]]) -> float | None:
    if len(buckets) < 2:
        return None
    means = [float(bucket["mean_forward_return"]) for bucket in buckets]
    comparisons = [right >= left for left, right in zip(means, means[1:], strict=False)]
    return sum(1 for comparison in comparisons if comparison) / len(comparisons)


def _breakdown(pairs: Sequence[_AlignedPair], field_name: str) -> list[dict[str, Any]]:
    grouped = _group_pairs_by_field(pairs, field_name)
    rows = []
    for value, group in sorted(grouped.items(), key=lambda item: str(item[0])):
        signal_values = [pair.value for pair in group]
        forward_returns = [pair.forward_return for pair in group]
        rows.append(
            {
                "value": value,
                "sample_size": len(group),
                "ic": _pearson(signal_values, forward_returns),
                "rank_ic": _pearson(_ranks(signal_values), _ranks(forward_returns)),
                "hit_rate": _hit_rate(signal_values, forward_returns),
            }
        )
    return rows


def _turnover_proxy(observations: Sequence[_SignalObservation]) -> float | None:
    changes: list[float] = []
    for symbol_observations in _group_observations_by_symbol(observations).values():
        ordered = sorted(symbol_observations, key=lambda observation: observation.ts)
        values = [observation.value for observation in ordered]
        changes.extend(abs(right - left) for left, right in zip(values, values[1:], strict=False))
    if not changes:
        return None
    return sum(changes) / len(changes)


def _is_discrete_action(values: Sequence[float]) -> bool:
    return bool(values) and all(value in {-1.0, 0.0, 1.0} for value in values)


def _data_quality_has_warnings(report: Mapping[str, Any]) -> bool:
    return bool(report.get("warnings") or report.get("blockers") or report.get("complete") is False)


def _group_by_candidate(
    observations: Sequence[_SignalObservation],
) -> Mapping[str, tuple[_SignalObservation, ...]]:
    grouped: dict[str, list[_SignalObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.candidate_id].append(observation)
    return {key: tuple(value) for key, value in grouped.items()}


def _group_observations_by_symbol(
    observations: Sequence[_SignalObservation],
) -> Mapping[str, tuple[_SignalObservation, ...]]:
    grouped: dict[str, list[_SignalObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.symbol].append(observation)
    return {key: tuple(value) for key, value in grouped.items()}


def _group_pairs_by_candidate(
    pairs: Sequence[_AlignedPair],
) -> Mapping[str, tuple[_AlignedPair, ...]]:
    grouped: dict[str, list[_AlignedPair]] = defaultdict(list)
    for pair in pairs:
        grouped[pair.candidate_id].append(pair)
    return {key: tuple(value) for key, value in grouped.items()}


def _group_pairs_by_horizon(
    pairs: Sequence[_AlignedPair],
) -> Mapping[int, tuple[_AlignedPair, ...]]:
    grouped: dict[int, list[_AlignedPair]] = defaultdict(list)
    for pair in pairs:
        grouped[pair.horizon].append(pair)
    return {key: tuple(value) for key, value in grouped.items()}


def _group_pairs_by_field(
    pairs: Sequence[_AlignedPair],
    field_name: str,
) -> Mapping[str, tuple[_AlignedPair, ...]]:
    grouped: dict[str, list[_AlignedPair]] = defaultdict(list)
    for pair in pairs:
        value = getattr(pair, field_name)
        if value is not None:
            grouped[str(value)].append(pair)
    return {key: tuple(value) for key, value in grouped.items()}


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


def _timestamp_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "").strip()


def _int_value(value: Any) -> int | None:
    try:
        if isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


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
