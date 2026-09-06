"""Public package surface for the Trader Console API."""

from .application import AuthenticationProvider, ConsoleStartupError, create_app
from .configuration import (
    ConsoleApiSettings,
    ConsoleConfigurationError,
)
from .contracts import (
    BrokerAccountBinding,
    ConsoleEnvironment,
    ConsoleScope,
    TraderPrincipal,
)

__all__ = [
    "AuthenticationProvider",
    "BrokerAccountBinding",
    "ConsoleApiSettings",
    "ConsoleConfigurationError",
    "ConsoleEnvironment",
    "ConsoleScope",
    "ConsoleStartupError",
    "TraderPrincipal",
    "create_app",
]
