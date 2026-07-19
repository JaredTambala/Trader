"""Stable content-derived research identifiers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def stable_research_id(prefix: str, payload: Mapping[str, Any]) -> str:
    """Build a deterministic identifier from a JSON-compatible payload."""
    serialized = json.dumps(jsonable(payload), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def source_hash(source_code: str) -> str:
    """Return a SHA-256 digest for source text."""
    return hashlib.sha256(source_code.encode("utf-8")).hexdigest()


def json_payload_hash(payload: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 digest for a JSON-compatible payload."""
    serialized = json.dumps(
        jsonable(payload),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def jsonable(value: Any) -> Any:
    """Normalize shared research values into JSON-compatible plain data."""
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
