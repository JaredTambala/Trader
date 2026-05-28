"""Environment loading for the local MCP research server."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values


@dataclass(frozen=True)
class McpEnvironment:
    """Resolved local MCP server environment.

    Attributes:
        environment: Environment label, such as `local`.
        transport: Transport used by the local MCP server.
        artifact_root: Root directory for future MCP/research artifacts.
        allow_broker_mutation: Whether broker-mutating MCP tools may be enabled.
        allow_raw_sql: Whether raw SQL MCP tools may be enabled.
        allow_data_loading: Whether data-loading MCP tools may be enabled.
        allow_backtests: Whether backtest MCP tools may be enabled.
    """

    environment: str
    transport: str
    artifact_root: Path
    allow_broker_mutation: bool
    allow_raw_sql: bool
    allow_data_loading: bool
    allow_backtests: bool

    def policy_flags(self) -> dict[str, bool]:
        """Return environment policy flags.

        Returns:
            Dictionary of environment-specific capability policy flags.
        """
        return {
            "allow_broker_mutation": self.allow_broker_mutation,
            "allow_raw_sql": self.allow_raw_sql,
            "allow_data_loading": self.allow_data_loading,
            "allow_backtests": self.allow_backtests,
        }


def load_local_environment(env_path: str | Path | None = None) -> McpEnvironment:
    """Load the local MCP server environment file.

    Args:
        env_path: Optional path to an env file. Defaults to the repository's
            `local.env` file.

    Returns:
        Resolved local MCP server environment. Process environment values
        override values from the env file.

    Raises:
        FileNotFoundError: If the env file does not exist.
        ValueError: If a required value is missing or malformed.
    """
    path = Path(env_path) if env_path is not None else _default_env_path()
    if not path.exists():
        raise FileNotFoundError(f"Local MCP env file not found: {path}")
    file_values = {key: value for key, value in dotenv_values(path).items() if value is not None}
    transport = _required_env("TRADER_MCP_TRANSPORT", file_values)
    if transport != "stdio":
        raise ValueError(f"Unsupported local MCP transport: {transport}")
    return McpEnvironment(
        environment=_required_env("TRADER_MCP_ENVIRONMENT", file_values),
        transport=transport,
        artifact_root=Path(_required_env("TRADER_MCP_ARTIFACT_ROOT", file_values)),
        allow_broker_mutation=_bool_env("TRADER_MCP_ALLOW_BROKER_MUTATION", file_values),
        allow_raw_sql=_bool_env("TRADER_MCP_ALLOW_RAW_SQL", file_values),
        allow_data_loading=_bool_env("TRADER_MCP_ALLOW_DATA_LOADING", file_values),
        allow_backtests=_bool_env("TRADER_MCP_ALLOW_BACKTESTS", file_values),
    )


def _default_env_path() -> Path:
    """Return the default local MCP env path.

    Returns:
        Repository-root `local.env` path.
    """
    return Path(__file__).resolve().parents[2] / "local.env"


def _required_env(name: str, file_values: Mapping[str, str]) -> str:
    """Return a required env value.

    Args:
        name: Environment variable name.
        file_values: Values loaded from the env file.

    Returns:
        Non-empty environment value.

    Raises:
        ValueError: If the value is missing or empty.
    """
    value = os.environ.get(name, file_values.get(name, "")).strip()
    if not value:
        raise ValueError(f"Missing required local MCP env value: {name}")
    return value


def _bool_env(name: str, file_values: Mapping[str, str]) -> bool:
    """Return a boolean env value.

    Args:
        name: Environment variable name.
        file_values: Values loaded from the env file.

    Returns:
        Parsed boolean value.

    Raises:
        ValueError: If the value is missing or not a supported boolean token.
    """
    value = _required_env(name, file_values).lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean local MCP env value for {name}: {value}")
