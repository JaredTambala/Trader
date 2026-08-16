"""Define small value objects shared by knowledge-domain contracts.

The values normalize timestamps, identifiers, statuses, and other common fields
at construction time so source, evidence, methodology, and card models do not
pass partially validated dictionaries between services.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


KNOWLEDGE_SCHEMA_VERSION = "2"
"""Schema version for local knowledge artifacts."""


KNOWLEDGE_EVIDENCE_UNIT_ARTIFACT_TYPE = "knowledge_evidence_unit"
"""Canonical artifact marker for stored source evidence units."""


SUPPORTED_SOURCE_EXTENSIONS = frozenset({".md", ".txt", ".pdf"})
"""File types accepted by the first knowledge-ingestion slice."""


SOURCE_TYPE_LABELS = frozenset(
    {
        "foundation_textbook",
        "method_textbook",
        "primary_paper",
        "software_documentation",
        "internal_note",
    }
)
"""Allowed source-type labels for registered knowledge documents."""


DEFAULT_SOURCE_TYPE = "internal_note"
"""Default source-type label for local notes and operator-authored documents."""


METHODOLOGY_CANDIDATE_STATUSES = frozenset({"discovered", "extracted", "validated", "blocked", "rejected"})
"""Allowed lifecycle states for methodology candidates before card approval."""


METHODOLOGY_EVIDENCE_PACKET_STATUSES = frozenset({"assembled", "blocked"})
"""Allowed lifecycle states for assembled methodology evidence packets."""


METHOD_CARD_STATUSES = frozenset({"approved", "draft", "planned", "rejected", "superseded"})
"""Allowed lifecycle states for canonical method-card records."""


METHOD_CARD_SET_STATUSES = frozenset({"active", "retired", "needs_review"})
"""Allowed lifecycle states for stable method-card aggregate records."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return _utc_now()


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _slug_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return value
    return (value,)


def _string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(value) if str(item).strip())


def _has_methodology_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return bool(value)
    return True
