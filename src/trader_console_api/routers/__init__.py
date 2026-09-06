"""FastAPI transport routers for the Console API."""

from .health import router as health_router

__all__ = ["health_router"]
