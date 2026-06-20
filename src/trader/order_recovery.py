"""Compatibility alias for runtime order recovery workflows.

The implementation lives in :mod:`trader.runtime.orders`; this module preserves
the established ``trader.order_recovery`` import path.
"""

from __future__ import annotations

import sys as _sys

from .runtime import orders as _orders
from .runtime.orders import *  # noqa: F401,F403

_sys.modules[__name__] = _orders
