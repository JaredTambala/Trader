"""Compatibility alias for runtime notification helpers.

The implementation lives in :mod:`trader.runtime.notifications`; this module
preserves the established ``trader.notifications`` import path.
"""

from __future__ import annotations

import sys as _sys

from .runtime import notifications as _notifications
from .runtime.notifications import *  # noqa: F401,F403

_sys.modules[__name__] = _notifications
