"""Compatibility alias for Postgres knowledge-store persistence.

The implementation lives in :mod:`trader.knowledge.store`; this module preserves
the established ``trader.knowledge_store`` import path.
"""

from __future__ import annotations

import sys as _sys

from .knowledge import store as _store
from .knowledge.store import *  # noqa: F401,F403

_sys.modules[__name__] = _store
