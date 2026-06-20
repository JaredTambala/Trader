"""Compatibility alias for runtime status helpers.

The implementation lives in :mod:`trader.runtime.status`; this module preserves
the established ``trader.runtime_status`` import path.
"""

from __future__ import annotations

import sys as _sys

from .runtime import status as _status
from .runtime.status import *  # noqa: F401,F403

_sys.modules[__name__] = _status
