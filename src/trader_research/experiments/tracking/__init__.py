"""Project canonical Trader evidence into non-authoritative tracking systems.

Tracking adapters receive already persisted experiment artifacts and may expose
them for analysis. Provider runs, tags, and metrics are convenience projections
and never replace Trader's canonical optimization ledger.
"""

from .services import ExperimentTrackingSinkRegistry, project_experiment_tracking

__all__ = ["ExperimentTrackingSinkRegistry", "project_experiment_tracking"]
