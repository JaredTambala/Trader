"""Assemble context-owned writers for typed Postgres projections.

Each canonical artifact type has at most one projection owner. The default
registry combines Experiments, Methodology, ML, Review, and Orchestration writers
while rejecting duplicate registrations at construction time.
"""

from .experiments import PROJECTION_WRITERS as EXPERIMENT_PROJECTION_WRITERS
from .methodology import PROJECTION_WRITERS as METHODOLOGY_PROJECTION_WRITERS
from .ml import PROJECTION_WRITERS as ML_PROJECTION_WRITERS
from .orchestration import (
    PROJECTION_WRITERS as ORCHESTRATION_PROJECTION_WRITERS,
)
from .registry import ProjectionRegistry, combine_projection_writers
from .review import PROJECTION_WRITERS as REVIEW_PROJECTION_WRITERS


def default_projection_registry() -> ProjectionRegistry:
    """Build the complete maintained Postgres projection registry.

    Context-owned Methodology, ML, Experiments, Review, and Orchestration mappings
    are combined, with duplicate artifact ownership rejected during construction.
    """
    return combine_projection_writers(
        METHODOLOGY_PROJECTION_WRITERS,
        ML_PROJECTION_WRITERS,
        EXPERIMENT_PROJECTION_WRITERS,
        REVIEW_PROJECTION_WRITERS,
        ORCHESTRATION_PROJECTION_WRITERS,
    )


__all__ = [
    "EXPERIMENT_PROJECTION_WRITERS",
    "METHODOLOGY_PROJECTION_WRITERS",
    "ML_PROJECTION_WRITERS",
    "ORCHESTRATION_PROJECTION_WRITERS",
    "ProjectionRegistry",
    "REVIEW_PROJECTION_WRITERS",
    "combine_projection_writers",
    "default_projection_registry",
]
