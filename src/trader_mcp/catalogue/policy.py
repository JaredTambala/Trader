"""Environment loading for the local MCP research server."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal, Mapping

from dotenv import dotenv_values


@dataclass(frozen=True)
class McpEnvironment:
    """Resolved local MCP server environment.

    Attributes:
        environment: Environment label, such as `local`.
        transport: Transport used by the local MCP server.
        artifact_root: Root directory for future MCP/research artifacts.
        trader_config_path: Optional trader YAML config used to build the event store.
        tool_env_path: Optional dotenv file loaded only before tool execution config is built.
        allow_broker_mutation: Whether broker-mutating MCP tools may be enabled.
        allow_raw_sql: Whether raw SQL MCP tools may be enabled.
        allow_symbol_provider_discovery: Whether provider catalog discovery may make read-only network calls.
        allow_data_loading: Whether data-loading MCP tools may be enabled.
        allow_backtests: Whether backtest MCP tools may be enabled.
        allow_optimization: Whether generic optimization execution may be enabled.
        allow_external_research_writes: Whether any external research projection is allowed.
        allow_optuna_writes: Whether configured Optuna sampler state may be mutated.
        allow_experiment_tracking_writes: Whether tracking sinks may be mutated.
        allow_ml_runtime: Whether configured model adapters may load models for parity or inference.
        allow_coding_workspace: Whether isolated Coding Workspace mutations and checks are enabled.
        coding_workspace_root: Dedicated root for disposable candidate workspaces.
        coding_repository_root: Pinned Trader repository snapshot exposed read-only.
        coding_repository_revision: Exact revision represented by that snapshot.
        coding_container_image: Pinned image used for candidate checks.
    """

    environment: str
    transport: Literal["stdio"]
    artifact_root: Path
    trader_config_path: Path | None
    tool_env_path: Path | None
    allow_broker_mutation: bool
    allow_raw_sql: bool
    allow_symbol_provider_discovery: bool
    allow_data_loading: bool
    allow_backtests: bool
    embeddings_provider: str
    embeddings_model: str
    embeddings_base_url: str
    embeddings_api_key: str
    embeddings_timeout_seconds: float
    knowledge_store: str
    allow_optimization: bool = False
    allow_external_research_writes: bool = False
    allow_optuna_writes: bool = False
    allow_experiment_tracking_writes: bool = False
    allow_ml_runtime: bool = False
    optuna_storage_url: str = ""
    optuna_study_prefix: str = "trader"
    optuna_schema: str = "trader_optuna"
    optuna_role: str = "trader_optuna_writer"
    mlflow_tracking_uri: str = ""
    mlflow_optimization_experiment: str = "trader-backtest-optimization"
    mlflow_inference_profile: str = "mlflow_local_pyfunc"
    allow_coding_workspace: bool = False
    coding_workspace_root: Path | None = None
    coding_repository_root: Path | None = None
    coding_repository_revision: str = ""
    coding_container_image: str = ""

    def policy_flags(self) -> dict[str, bool]:
        """Return environment policy flags.

        Returns:
            Dictionary of environment-specific capability policy flags.
        """
        return {
            "allow_broker_mutation": self.allow_broker_mutation,
            "allow_raw_sql": self.allow_raw_sql,
            "allow_symbol_provider_discovery": self.allow_symbol_provider_discovery,
            "allow_data_loading": self.allow_data_loading,
            "allow_backtests": self.allow_backtests,
            "allow_optimization": self.allow_optimization,
            "allow_external_research_writes": self.allow_external_research_writes,
            "allow_optuna_writes": self.allow_optuna_writes,
            "allow_experiment_tracking_writes": self.allow_experiment_tracking_writes,
            "allow_ml_runtime": self.allow_ml_runtime,
            "allow_coding_workspace": self.allow_coding_workspace,
        }

    def embeddings_env(self) -> dict[str, str]:
        """Return embedding runtime environment values for knowledge tools."""
        return {
            "TRADER_RESEARCH_EMBEDDINGS_PROVIDER": self.embeddings_provider,
            "TRADER_RESEARCH_EMBEDDINGS_MODEL": self.embeddings_model,
            "TRADER_RESEARCH_EMBEDDINGS_BASE_URL": self.embeddings_base_url,
            "TRADER_RESEARCH_EMBEDDINGS_API_KEY": self.embeddings_api_key,
            "TRADER_RESEARCH_EMBEDDINGS_TIMEOUT_SECONDS": str(
                self.embeddings_timeout_seconds
            ),
        }

    def knowledge_store_env(self) -> dict[str, str]:
        """Return knowledge-store runtime environment values."""
        return {
            "TRADER_RESEARCH_KNOWLEDGE_STORE": self.knowledge_store,
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
    file_values = {
        key: value for key, value in dotenv_values(path).items() if value is not None
    }
    transport_value = _required_env("TRADER_MCP_TRANSPORT", file_values)
    if transport_value != "stdio":
        raise ValueError(f"Unsupported local MCP transport: {transport_value}")
    transport: Literal["stdio"] = "stdio"
    return McpEnvironment(
        environment=_required_env("TRADER_MCP_ENVIRONMENT", file_values),
        transport=transport,
        artifact_root=Path(_required_env("TRADER_MCP_ARTIFACT_ROOT", file_values)),
        trader_config_path=_optional_path_env(
            "TRADER_MCP_TRADER_CONFIG_PATH", file_values
        ),
        tool_env_path=_optional_path_env("TRADER_MCP_TOOL_ENV_PATH", file_values),
        allow_broker_mutation=_bool_env(
            "TRADER_MCP_ALLOW_BROKER_MUTATION", file_values
        ),
        allow_raw_sql=_bool_env("TRADER_MCP_ALLOW_RAW_SQL", file_values),
        allow_symbol_provider_discovery=_bool_env(
            "TRADER_MCP_ALLOW_SYMBOL_PROVIDER_DISCOVERY", file_values
        ),
        allow_data_loading=_bool_env("TRADER_MCP_ALLOW_DATA_LOADING", file_values),
        allow_backtests=_bool_env("TRADER_MCP_ALLOW_BACKTESTS", file_values),
        embeddings_provider=_optional_env(
            "TRADER_RESEARCH_EMBEDDINGS_PROVIDER", file_values
        ),
        embeddings_model=_optional_env("TRADER_RESEARCH_EMBEDDINGS_MODEL", file_values),
        embeddings_base_url=_optional_env(
            "TRADER_RESEARCH_EMBEDDINGS_BASE_URL", file_values
        ),
        embeddings_api_key=_optional_env(
            "TRADER_RESEARCH_EMBEDDINGS_API_KEY", file_values
        ),
        embeddings_timeout_seconds=_float_env(
            "TRADER_RESEARCH_EMBEDDINGS_TIMEOUT_SECONDS", file_values, default=30.0
        ),
        knowledge_store=_optional_env("TRADER_RESEARCH_KNOWLEDGE_STORE", file_values)
        or "postgres",
        allow_optimization=_optional_bool_env(
            "TRADER_MCP_ALLOW_OPTIMIZATION", file_values
        ),
        allow_external_research_writes=_optional_bool_env(
            "TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES", file_values
        ),
        allow_optuna_writes=_optional_bool_env(
            "TRADER_MCP_ALLOW_OPTUNA_WRITES", file_values
        ),
        allow_experiment_tracking_writes=_optional_bool_env(
            "TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES", file_values
        ),
        allow_ml_runtime=_optional_bool_env("TRADER_MCP_ALLOW_ML_RUNTIME", file_values),
        optuna_storage_url=_optional_env("TRADER_OPTUNA_STORAGE_URL", file_values),
        optuna_study_prefix=_optional_env("TRADER_OPTUNA_STUDY_PREFIX", file_values)
        or "trader",
        optuna_schema=_optional_env("TRADER_OPTUNA_SCHEMA", file_values)
        or "trader_optuna",
        optuna_role=_optional_env("TRADER_OPTUNA_ROLE", file_values)
        or "trader_optuna_writer",
        mlflow_tracking_uri=_optional_env("MLFLOW_TRACKING_URI", file_values),
        mlflow_optimization_experiment=(
            _optional_env("TRADER_MLFLOW_OPTIMIZATION_EXPERIMENT", file_values)
            or "trader-backtest-optimization"
        ),
        mlflow_inference_profile=(
            _optional_env("TRADER_MLFLOW_INFERENCE_PROFILE", file_values)
            or "mlflow_local_pyfunc"
        ),
        allow_coding_workspace=_optional_bool_env(
            "TRADER_MCP_ALLOW_CODING_WORKSPACE",
            file_values,
        ),
        coding_workspace_root=_optional_path_env(
            "TRADER_MCP_CODING_WORKSPACE_ROOT",
            file_values,
        ),
        coding_repository_root=_optional_path_env(
            "TRADER_MCP_CODING_REPOSITORY_ROOT",
            file_values,
        ),
        coding_repository_revision=_optional_env(
            "TRADER_MCP_CODING_REPOSITORY_REVISION",
            file_values,
        ),
        coding_container_image=_optional_env(
            "TRADER_MCP_CODING_CONTAINER_IMAGE",
            file_values,
        ),
    )


def _default_env_path() -> Path:
    """Return the default local MCP env path.

    Returns:
        Repository-root `local.env` path.
    """
    return Path(__file__).resolve().parents[3] / "local.env"


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


def _optional_path_env(name: str, file_values: Mapping[str, str]) -> Path | None:
    """Return an optional path env value.

    Args:
        name: Environment variable name.
        file_values: Values loaded from the env file.

    Returns:
        Path value when supplied, otherwise `None`.
    """
    value = os.environ.get(name, file_values.get(name, "")).strip()
    if not value:
        return None
    return Path(value)


def _optional_env(name: str, file_values: Mapping[str, str]) -> str:
    """Return an optional string env value."""
    return os.environ.get(name, file_values.get(name, "")).strip()


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


def _optional_bool_env(
    name: str, file_values: Mapping[str, str], *, default: bool = False
) -> bool:
    """Return an optional boolean environment value."""
    value = os.environ.get(name, file_values.get(name, "")).strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean local MCP env value for {name}: {value}")


def _float_env(name: str, file_values: Mapping[str, str], *, default: float) -> float:
    """Return a floating-point env value with a default."""
    value = os.environ.get(name, file_values.get(name, "")).strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid numeric local MCP env value for {name}: {value}"
        ) from exc
