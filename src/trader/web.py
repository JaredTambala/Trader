"""Web API placeholders for health and status endpoints."""

from __future__ import annotations

import time
from typing import Mapping


def health_payload() -> Mapping[str, object]:
    """Return a minimal health payload for future web wiring."""
    return {"status": "ok", "ts": time.time()}


def status_payload(last_run_id: str | None = None) -> Mapping[str, object]:
    """Return a minimal status payload for future web wiring."""
    payload = {"status": "unknown", "ts": time.time()}
    if last_run_id:
        payload["last_run_id"] = last_run_id
    return payload
