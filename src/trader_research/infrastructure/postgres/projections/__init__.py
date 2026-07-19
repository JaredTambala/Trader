"""Context-owned writers for typed research-artifact projections."""

from .experiments import PROJECTION_WRITERS as EXPERIMENT_PROJECTION_WRITERS
from .methodology import PROJECTION_WRITERS as METHODOLOGY_PROJECTION_WRITERS
from .registry import ProjectionRegistry, combine_projection_writers
from .review import PROJECTION_WRITERS as REVIEW_PROJECTION_WRITERS


def default_projection_registry() -> ProjectionRegistry:
    """Build the maintained projection registry used by Postgres infrastructure."""
    return combine_projection_writers(
        METHODOLOGY_PROJECTION_WRITERS,
        EXPERIMENT_PROJECTION_WRITERS,
        REVIEW_PROJECTION_WRITERS,
    )


__all__ = [
    "EXPERIMENT_PROJECTION_WRITERS",
    "METHODOLOGY_PROJECTION_WRITERS",
    "ProjectionRegistry",
    "REVIEW_PROJECTION_WRITERS",
    "combine_projection_writers",
    "default_projection_registry",
]
