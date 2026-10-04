"""Application context for the Console's configured environment and account."""

from ..contracts import ConsoleScope


class ContextService:
    """Expose public configuration without making connectivity or identity claims."""

    def __init__(self, scope: ConsoleScope) -> None:
        """Bind the service to the immutable, server-owned public scope."""
        self._scope = scope

    def context(self) -> ConsoleScope:
        """Return configured context without querying a database or broker."""
        return self._scope
