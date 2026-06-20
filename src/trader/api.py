"""Compatibility alias for the FastAPI backtest backend.

The implementation lives in :mod:`trader.web.api`; this module preserves the
established ``trader.api`` import path and ``python -m trader.api`` entrypoint.
"""

from __future__ import annotations

import sys as _sys

from .web import api as _api
from .web.api import *  # noqa: F401,F403

_sys.modules[__name__] = _api

if __name__ == "__main__":
    _api.main()
