"""Seeded method-card metadata for first Slice 5 evidence flows."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .domain import MethodCard
from .storage import KnowledgeRepository


SEEDED_METHOD_CARDS: tuple[MethodCard, ...] = (
    MethodCard(
        method_card_id="method_card_sma_seed_v1",
        method_id="sma",
        title="Simple moving average contract",
        family="indicator",
        status="approved",
        assumptions=("input observations are ordered", "period is a positive integer"),
        inputs=("price series",),
        outputs=("rolling mean series",),
        failure_modes=("insufficient warmup observations", "non-finite input values"),
    ),
    MethodCard(
        method_card_id="method_card_ema_seed_v1",
        method_id="ema",
        title="Exponential moving average contract",
        family="indicator",
        status="approved",
        assumptions=("input observations are ordered", "period controls smoothing"),
        inputs=("price series",),
        outputs=("exponentially weighted mean series",),
        failure_modes=("insufficient warmup observations", "non-finite input values"),
    ),
    MethodCard(
        method_card_id="method_card_rsi_seed_v1",
        method_id="rsi",
        title="Relative strength index contract",
        family="indicator",
        status="approved",
        assumptions=("input observations are ordered", "lossless flat windows produce bounded output"),
        inputs=("price series",),
        outputs=("bounded oscillator series",),
        failure_modes=("insufficient warmup observations", "division by zero edge cases"),
    ),
    MethodCard(
        method_card_id="method_card_rolling_volatility_seed_v1",
        method_id="rolling_volatility",
        title="Rolling volatility contract",
        family="transform",
        status="approved",
        assumptions=("returns are computed from ordered observations", "window is fixed before use"),
        inputs=("return series",),
        outputs=("rolling standard deviation series",),
        failure_modes=("insufficient warmup observations", "unstable tiny samples"),
    ),
    MethodCard(
        method_card_id="method_card_z_score_seed_v1",
        method_id="z_score",
        title="Z-score transform contract",
        family="transform",
        status="approved",
        assumptions=("scale estimate is non-zero", "window is fixed before use"),
        inputs=("numeric series",),
        outputs=("standardized series",),
        failure_modes=("zero variance window", "insufficient warmup observations"),
    ),
    MethodCard(
        method_card_id="method_card_rank_ic_seed_v1",
        method_id="rank_ic",
        title="Rank information coefficient diagnostic",
        family="signal_diagnostic",
        status="approved",
        assumptions=("signal and forward returns are aligned", "candidate family is declared before inference"),
        inputs=("signal observations", "forward return labels"),
        outputs=("rank correlation statistic", "p-value"),
        failure_modes=("missing labels", "overlapping horizon warnings", "small effective sample size"),
    ),
    MethodCard(
        method_card_id="method_card_benjamini_hochberg_seed_v1",
        method_id="benjamini_hochberg",
        title="Benjamini-Hochberg FDR correction",
        family="multiple_testing",
        status="approved",
        assumptions=("candidate family size is declared", "raw p-values come from a declared family"),
        inputs=("raw p-values", "false discovery rate"),
        outputs=("adjusted p-values", "rejection indicators"),
        failure_modes=("missing candidate family manifest", "invalid p-value range"),
    ),
)


def list_method_cards(
    artifact_root: str | Path,
    *,
    include_drafts: bool = False,
) -> tuple[MethodCard, ...]:
    """Return seeded and persisted method cards."""
    repository = KnowledgeRepository(artifact_root)
    cards = list(SEEDED_METHOD_CARDS)
    cards.extend(repository.list_persisted_method_cards())
    if not include_drafts:
        cards = [card for card in cards if card.status == "approved"]
    by_id = {card.method_card_id: card for card in cards}
    return tuple(by_id[key] for key in sorted(by_id))


def get_method_card(
    artifact_root: str | Path,
    method_card_id: str,
    *,
    include_drafts: bool = False,
) -> MethodCard | None:
    for card in list_method_cards(artifact_root, include_drafts=include_drafts):
        if card.method_card_id == method_card_id:
            return card
    return None


def method_cards_for_method(
    artifact_root: str | Path,
    method_id: str,
    *,
    include_drafts: bool = False,
) -> tuple[MethodCard, ...]:
    return tuple(
        card
        for card in list_method_cards(artifact_root, include_drafts=include_drafts)
        if card.method_id == method_id
    )


def search_method_cards(
    artifact_root: str | Path,
    query: str,
    *,
    family: str | None = None,
    include_drafts: bool = False,
    limit: int = 10,
) -> tuple[MethodCard, ...]:
    """Search method cards by simple deterministic text matching."""
    needle = query.strip().lower()
    cards = []
    for card in list_method_cards(artifact_root, include_drafts=include_drafts):
        if family and card.family != family:
            continue
        searchable = " ".join(
            (
                card.method_id,
                card.title,
                card.family,
                " ".join(card.assumptions),
                " ".join(card.failure_modes),
            )
        ).lower()
        if not needle or needle in searchable:
            cards.append(card)
    return tuple(cards[:limit])


def approved_method_card_ids_for_method(artifact_root: str | Path, method_id: str) -> tuple[str, ...]:
    return tuple(card.method_card_id for card in method_cards_for_method(artifact_root, method_id))


def has_approved_method_card(artifact_root: str | Path, method_card_ids: Sequence[str]) -> bool:
    cards = {card.method_card_id: card for card in list_method_cards(artifact_root)}
    return any(cards.get(str(card_id)) is not None and cards[str(card_id)].approved for card_id in method_card_ids)
