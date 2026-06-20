"""Compatibility alias for runtime trader-service orchestration.

The implementation lives in :mod:`trader.runtime.service`. This module keeps
``trader.trader_service`` import and monkeypatch paths stable for existing
operators, examples, and tests.
"""

from __future__ import annotations

import sys as _sys

from .runtime import service as _service
from .runtime.service import *  # noqa: F401,F403
from .runtime.service import _build_runtime_broker, _parse_market_data_notify  # noqa: F401

_sys.modules[__name__] = _service

if __name__ == "__main__":
    raise SystemExit(
        "trader.trader_service is a library module. "
        "Use run_trader_service.py (external entrypoint) to start the service."
    )
