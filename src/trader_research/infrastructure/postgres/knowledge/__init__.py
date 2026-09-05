"""Expose the concrete Postgres adapter for research knowledge persistence."""

from .store import PostgresKnowledgeStore

__all__ = ["PostgresKnowledgeStore"]
