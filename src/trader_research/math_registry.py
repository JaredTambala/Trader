"""Maintained method registry for Quantitative Methods tools."""

from __future__ import annotations

from typing import Mapping

from .math_domain import MethodRegistryEntry, ParameterSpec


METHOD_REGISTRY: Mapping[str, MethodRegistryEntry] = {
    "sma": MethodRegistryEntry(
        method_id="sma",
        family="indicator",
        status="approved",
        purpose="Compute a simple moving average over a fixed lookback window.",
        parameters=(ParameterSpec("period", "int", min_value=2, max_value=500),),
        inputs=("price series",),
        outputs=("rolling mean series",),
        assumptions=("input observations are ordered", "period is fixed before evaluation"),
        failure_modes=("insufficient warmup observations", "non-finite input values"),
        artifact_outputs=("indicator_contract.json",),
        warmup="period - 1 observations",
        nan_policy="propagate",
        no_lookahead=True,
        approved_method_card_ids=("method_card_sma_seed_v1",),
    ),
    "ema": MethodRegistryEntry(
        method_id="ema",
        family="indicator",
        status="approved",
        purpose="Compute an exponentially weighted moving average over a fixed lookback window.",
        parameters=(ParameterSpec("period", "int", min_value=2, max_value=500),),
        inputs=("price series",),
        outputs=("exponentially weighted mean series",),
        assumptions=("input observations are ordered", "period is fixed before evaluation"),
        failure_modes=("insufficient warmup observations", "non-finite input values"),
        artifact_outputs=("indicator_contract.json",),
        warmup="period observations for seeded average",
        nan_policy="propagate",
        no_lookahead=True,
        approved_method_card_ids=("method_card_ema_seed_v1",),
    ),
    "rsi": MethodRegistryEntry(
        method_id="rsi",
        family="indicator",
        status="approved",
        purpose="Compute relative strength index from ordered price observations.",
        parameters=(ParameterSpec("period", "int", min_value=2, max_value=500),),
        inputs=("price series",),
        outputs=("bounded oscillator series",),
        assumptions=("input observations are ordered", "period is fixed before evaluation"),
        failure_modes=("insufficient warmup observations", "zero-loss edge cases"),
        artifact_outputs=("indicator_contract.json",),
        warmup="period + 1 observations",
        nan_policy="propagate",
        no_lookahead=True,
        approved_method_card_ids=("method_card_rsi_seed_v1",),
    ),
    "rolling_volatility": MethodRegistryEntry(
        method_id="rolling_volatility",
        family="transform",
        status="approved",
        purpose="Compute rolling standard deviation for a return or numeric series.",
        parameters=(
            ParameterSpec("window", "int", min_value=2, max_value=1000),
            ParameterSpec("ddof", "int", required=False, min_value=0, max_value=1, default=1),
        ),
        inputs=("return series",),
        outputs=("rolling standard deviation series",),
        assumptions=("window is fixed before evaluation", "input observations are ordered"),
        failure_modes=("insufficient warmup observations", "unstable tiny samples"),
        artifact_outputs=("indicator_contract.json",),
        warmup="window observations",
        nan_policy="propagate",
        no_lookahead=True,
        approved_method_card_ids=("method_card_rolling_volatility_seed_v1",),
    ),
    "z_score": MethodRegistryEntry(
        method_id="z_score",
        family="transform",
        status="approved",
        purpose="Standardize a numeric series with a rolling mean and standard deviation.",
        parameters=(ParameterSpec("window", "int", min_value=2, max_value=1000),),
        inputs=("numeric series",),
        outputs=("standardized series",),
        assumptions=("window is fixed before evaluation", "scale estimate is non-zero"),
        failure_modes=("zero variance window", "insufficient warmup observations"),
        artifact_outputs=("indicator_contract.json",),
        warmup="window observations",
        nan_policy="propagate",
        no_lookahead=True,
        approved_method_card_ids=("method_card_z_score_seed_v1",),
    ),
    "rank_ic": MethodRegistryEntry(
        method_id="rank_ic",
        family="signal_diagnostic",
        status="planned",
        purpose="Compute rank information coefficient between signals and forward-return labels.",
        parameters=(ParameterSpec("horizon", "int", min_value=1, max_value=252),),
        inputs=("signal observations", "forward return labels"),
        outputs=("rank correlation statistic", "p-value"),
        assumptions=("candidate family is declared before inference", "labels are aligned without lookahead"),
        failure_modes=("missing labels", "overlapping horizon warnings", "small effective sample size"),
        artifact_outputs=("signal_diagnostic_report.json",),
        warmup="requires aligned signal and label observations",
        nan_policy="drop_pairwise",
        no_lookahead=True,
        requires_evidence=True,
        approved_method_card_ids=("method_card_rank_ic_seed_v1",),
    ),
    "benjamini_hochberg": MethodRegistryEntry(
        method_id="benjamini_hochberg",
        family="multiple_testing",
        status="planned",
        purpose="Adjust p-values to control false discovery rate across a declared candidate family.",
        parameters=(ParameterSpec("alpha", "float", min_value=0.0, max_value=1.0),),
        inputs=("raw p-values", "candidate family manifest"),
        outputs=("adjusted p-values", "rejection indicators"),
        assumptions=("candidate family size is declared before inference",),
        failure_modes=("invalid p-values", "missing candidate family manifest"),
        artifact_outputs=("multiple_testing_report.json",),
        warmup="not applicable",
        nan_policy="reject_missing",
        no_lookahead=True,
        requires_evidence=True,
        approved_method_card_ids=("method_card_benjamini_hochberg_seed_v1",),
    ),
}


def list_methods(*, family: str | None = None, status: str | None = None, include_planned: bool = True) -> tuple[MethodRegistryEntry, ...]:
    methods = []
    for entry in METHOD_REGISTRY.values():
        if family and entry.family != family:
            continue
        if status and entry.status != status:
            continue
        if not include_planned and entry.status != "approved":
            continue
        methods.append(entry)
    return tuple(sorted(methods, key=lambda item: item.method_id))


def get_method(method_id: str) -> MethodRegistryEntry | None:
    return METHOD_REGISTRY.get(method_id)
