"""Deterministic target-conditioned claim-span selection."""

from __future__ import annotations

import hashlib
import re
from typing import Mapping, Sequence

from trader_research.domain import stable_research_id

from .domain import EvidenceClaimSpan, KnowledgeChunk, MethodologyCandidate
from .evidence_profiles import EvidenceRoleProfile


CLAIM_SPAN_VERSION = "1"
"""Version for deterministic claim segmentation and target binding."""

_CLAIM_RE = re.compile(r"[^.;!?]+(?:[.;!?]+|$)", re.MULTILINE)
_LABEL_RE = re.compile(
    r"(?:^|[.;]\s+|\n\s*)(?P<label>[A-Z][A-Za-z][A-Za-z0-9 /,+-]{2,90}?"
    r"(?:\s+\([A-Z][A-Z0-9]{1,12}\))?)\s*:",
    re.MULTILINE,
)
_LOOSE_LABEL_RE = re.compile(
    r"(?P<label>[A-Z][A-Za-z0-9+-]+(?:\s+[A-Z][A-Za-z0-9+-]+){1,7}"
    r"(?:\s+\([A-Z][A-Z0-9]{1,12}\))?)\s*:",
)


def select_role_claim_spans(
    chunk: KnowledgeChunk,
    role: EvidenceRoleProfile,
    candidate: MethodologyCandidate,
    *,
    fallback_binding: str,
) -> tuple[tuple[EvidenceClaimSpan, ...], tuple[EvidenceClaimSpan, ...]]:
    """Select exact role-bearing spans and bind each to the target method.

    A chunk can return both accepted and rejected spans. Rejection applies to one
    local claim attribution only; it never grants exclusive ownership of the
    surrounding evidence unit to another method.
    """
    labels = _label_markers(chunk.text)
    direct_terms, alias_terms = _target_terms(candidate)
    accepted: list[EvidenceClaimSpan] = []
    rejected: list[EvidenceClaimSpan] = []
    for range_start, range_end in _claim_ranges(chunk.text, labels):
        start, end, text = _trimmed_span(chunk.text, range_start, range_end)
        if not text:
            continue
        matched_terms = tuple(term for term in role.search_terms if _term_occurs(term, text))
        if role.role_id == "definition" and (_contains_any(text, direct_terms) or _contains_any(text, alias_terms)):
            matched_terms = tuple(dict.fromkeys((*matched_terms, "method_label")))
        if not matched_terms:
            continue
        active_label = _active_label(labels, start)
        binding = _span_binding(
            text,
            start=start,
            active_label=active_label,
            labels=labels,
            direct_terms=direct_terms,
            alias_terms=alias_terms,
            fallback_binding=fallback_binding,
        )
        local_labels = tuple(
            dict.fromkeys(
                label
                for label in (active_label, *(item[1] for item in labels if start <= item[0] < end))
                if label
            )
        )
        claim_span = _claim_span(
            chunk,
            role_id=role.role_id,
            target_method=candidate.title,
            start=start,
            end=end,
            text=text,
            target_binding=binding,
            matched_terms=matched_terms,
            method_labels=local_labels,
        )
        if binding in {"direct_label", "alias_label", "same_sentence", "same_paragraph", "nearby_context"}:
            accepted.append(claim_span)
        else:
            rejected.append(claim_span)
    return tuple(accepted), tuple(rejected)


def claim_span_from_mapping(payload: Mapping[str, object]) -> EvidenceClaimSpan:
    """Parse a claim span carried inside packet role evidence."""
    return EvidenceClaimSpan.from_dict(payload)


def _span_binding(
    text: str,
    *,
    start: int,
    active_label: str | None,
    labels: Sequence[tuple[int, str]],
    direct_terms: Sequence[str],
    alias_terms: Sequence[str],
    fallback_binding: str,
) -> str:
    if active_label and _matches_any(active_label, direct_terms):
        return "direct_label"
    if active_label and _matches_any(active_label, alias_terms):
        return "alias_label"
    if _contains_any(text, direct_terms) or _contains_any(text, alias_terms):
        return "same_sentence"
    if active_label is not None:
        return "rejected"
    if any(position > start and _matches_any(label, (*direct_terms, *alias_terms)) for position, label in labels):
        return "rejected"
    if fallback_binding in {"direct_label", "alias_label", "same_sentence", "same_paragraph", "nearby_context"}:
        return fallback_binding
    return "weak"


def _claim_span(
    chunk: KnowledgeChunk,
    *,
    role_id: str,
    target_method: str,
    start: int,
    end: int,
    text: str,
    target_binding: str,
    matched_terms: Sequence[str],
    method_labels: Sequence[str],
) -> EvidenceClaimSpan:
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return EvidenceClaimSpan(
        span_id=stable_research_id(
            "knowledge_claim_span",
            {
                "chunk_id": chunk.chunk_id,
                "start_char": start,
                "end_char": end,
                "text_hash": text_hash,
                "evidence_role": role_id,
                "target_method": target_method,
                "target_binding": target_binding,
                "version": CLAIM_SPAN_VERSION,
            },
        ),
        start_char=start,
        end_char=end,
        text=text,
        text_hash=text_hash,
        evidence_role=role_id,
        target_method=target_method,
        target_binding=target_binding,
        matched_terms=tuple(dict.fromkeys(matched_terms)),
        method_labels=tuple(dict.fromkeys(method_labels)),
        extraction_version=CLAIM_SPAN_VERSION,
    )


def _label_markers(text: str) -> tuple[tuple[int, str], ...]:
    markers = {
        (match.start("label"), match.group("label").strip())
        for pattern in (_LABEL_RE, _LOOSE_LABEL_RE)
        for match in pattern.finditer(text)
    }
    return tuple(sorted(markers, key=lambda item: (item[0], item[1])))


def detect_local_method_labels(text: str) -> tuple[str, ...]:
    """Return generic local labels used for cross-unit context binding."""
    return tuple(dict.fromkeys(label for _, label in _label_markers(text)))


def _claim_ranges(text: str, labels: Sequence[tuple[int, str]]) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    for match in _CLAIM_RE.finditer(text):
        boundaries = [match.start()]
        boundaries.extend(position for position, _ in labels if match.start() < position < match.end())
        boundaries.append(match.end())
        ranges.extend(
            (start, end)
            for start, end in zip(boundaries, boundaries[1:])
            if end > start
        )
    return tuple(ranges)


def _active_label(labels: Sequence[tuple[int, str]], start: int) -> str | None:
    active = None
    for position, label in labels:
        if position > start:
            break
        active = label
    return active


def _target_terms(candidate: MethodologyCandidate) -> tuple[tuple[str, ...], tuple[str, ...]]:
    identity = candidate.method_identity if isinstance(candidate.method_identity, Mapping) else {}
    direct = (candidate.title, str(identity.get("canonical_name") or ""), str(identity.get("source_name") or ""))
    aliases: list[str] = []
    for key in ("aliases", "abbreviations"):
        values = identity.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            aliases.extend(str(value) for value in values)
    return (
        tuple(dict.fromkeys(term.strip() for term in direct if term.strip())),
        tuple(dict.fromkeys(term.strip() for term in aliases if term.strip())),
    )


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int, str]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end, text[start:end]


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    normalized = _normalize(text)
    return any(_normalize(term) in normalized for term in terms if _normalize(term))


def _term_occurs(term: str, text: str) -> bool:
    normalized_term = _normalize(term)
    normalized_text = _normalize(text)
    if not normalized_term or not normalized_text:
        return False
    if normalized_term == "=":
        return "=" in text
    if " " in normalized_term:
        return normalized_term in normalized_text
    return re.search(rf"\b{re.escape(normalized_term)}(?:s|es)?\b", normalized_text) is not None


def _matches_any(label: str, terms: Sequence[str]) -> bool:
    normalized_label = _normalize(label)
    return any(
        normalized_label == _normalize(term)
        or normalized_label.startswith(f"{_normalize(term)} ")
        or _normalize(term).startswith(f"{normalized_label} ")
        for term in terms
        if _normalize(term)
    )


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))
