"""Compatibility alias for runtime metrics sampling.

The implementation lives in :mod:`trader.runtime.metrics`; this module preserves
the established ``trader.metrics`` import path.
"""

from __future__ import annotations

import sys as _sys

from .runtime import metrics as _metrics
from .runtime.metrics import *  # noqa: F401,F403

_sys.modules[__name__] = _metrics
