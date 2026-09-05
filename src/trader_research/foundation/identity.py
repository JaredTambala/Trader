"""Build stable identifiers and hashes from normalized research payloads.

All helpers are deterministic and side-effect free. Values are converted to a
canonical JSON-compatible shape before hashing so equivalent evidence produces
the same identity across processes and storage adapters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def stable_research_id(prefix: str, payload: Mapping[str, Any]) -> str:
    """Build a readable deterministic ID from canonical JSON content.

    Normalized, key-sorted compact JSON is hashed with SHA-256; the first sixteen
    hex characters are appended to ``prefix``.
    """
    serialized = json.dumps(jsonable(payload), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def source_hash(source_code: str) -> str:
    """Return the full lowercase SHA-256 hex digest of UTF-8 source text.

    No whitespace or newline normalization is applied, so byte-level source
    changes always produce a different digest.
    """
    return hashlib.sha256(source_code.encode("utf-8")).hexdigest()


def json_payload_hash(payload: Mapping[str, Any]) -> str:
    """Hash a normalized mapping as canonical compact JSON.

    Keys are sorted after recursive ``jsonable`` conversion and the full SHA-256
    hex digest is returned without a ``sha256:`` prefix.
    """
    serialized = json.dumps(
        jsonable(payload),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def jsonable(value: Any) -> Any:
    """Recursively normalize a research value to JSON-compatible plain data.

    Mappings receive string keys, sequences become lists, sets are sorted,
    datetimes are converted to UTC ISO strings, enums use their values, and
    objects exposing ``to_dict`` are normalized through that representation.
    Primitive values pass through unchanged.

    Returns:
        A deterministic composition of JSON scalar, list, and dictionary values.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    return value
