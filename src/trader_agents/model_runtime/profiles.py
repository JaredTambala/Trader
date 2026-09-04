"""Versioned model and agent-program profiles for the first agentic slice."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any

from trader_research.foundation import json_payload_hash

from trader_agents.contracts.domain import AgentRole


DEVELOPMENT_MODEL_PROFILE_ID = "ollama-lfm25-8b-json-v1"
"""Pinned local model profile selected for bounded agentic evaluation."""

OLLAMA_LFM25_8B_DIGEST = (
    "9cf756159fc2f3b9128c6a3f544ec90c5e9b8afdbb4179a57b8aea9de589cfb2"
)
"""Exact Ollama content digest selected for bounded agentic evaluation."""

REJECTED_QWEN35_9B_MODEL_PROFILE_ID = "ollama-qwen35-9b-json-v5"
"""Historical profile identity rejected by bounded model-choice tests."""

OLLAMA_QWEN35_9B_DIGEST = (
    "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7"
)
"""Historical Ollama content digest retained with the rejected profile."""

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ModelProfile:
    """Provider-neutral configuration for one admitted model identity.

    Attributes:
        profile_id: Stable identity stored in sessions and traces.
        provider: Supported provider adapter name.
        model: Provider model identifier.
        model_revision: Immutable provider revision served for ``model``.
        base_url: Provider endpoint without credentials.
        temperature: Sampling temperature for control decisions.
        context_window_tokens: Maximum input-plus-output context admitted for
            one provider call.
        max_output_tokens: Maximum generated tokens per call.
        timeout_seconds: Provider request timeout.
        thinking: Whether provider-specific internal thinking is enabled.
    """

    profile_id: str
    provider: str
    model: str
    model_revision: str
    base_url: str
    temperature: float = 0.0
    context_window_tokens: int = 8_192
    max_output_tokens: int = 2_048
    timeout_seconds: float = 120.0
    thinking: bool = False

    def __post_init__(self) -> None:
        """Validate stable identity and bounded call settings."""
        for value, label in (
            (self.profile_id, "profile_id"),
            (self.provider, "provider"),
            (self.model, "model"),
            (self.model_revision, "model_revision"),
            (self.base_url, "base_url"),
        ):
            if not str(value).strip():
                raise ValueError(f"{label} is required")
        if self.provider == "ollama" and not _SHA256_PATTERN.fullmatch(
            self.model_revision
        ):
            raise ValueError("Ollama model_revision must be a lowercase SHA-256 digest")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        if not 4_096 <= self.context_window_tokens <= 131_072:
            raise ValueError("context_window_tokens must be between 4096 and 131072")
        if not 1 <= self.max_output_tokens <= 8_192:
            raise ValueError("max_output_tokens must be between 1 and 8192")
        if self.max_output_tokens >= self.context_window_tokens:
            raise ValueError(
                "max_output_tokens must be smaller than the context window"
            )
        if not 1.0 <= self.timeout_seconds <= 600.0:
            raise ValueError("timeout_seconds must be between 1 and 600")

    def to_dict(self) -> dict[str, Any]:
        """Return the credential-free public profile."""
        return {
            "profile_id": self.profile_id,
            "provider": self.provider,
            "model": self.model,
            "model_revision": self.model_revision,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "context_window_tokens": self.context_window_tokens,
            "max_output_tokens": self.max_output_tokens,
            "timeout_seconds": self.timeout_seconds,
            "thinking": self.thinking,
        }


@dataclass(frozen=True)
class AgentProgram:
    """Immutable public identity for one versioned agent model program.

    Attributes:
        program_id: Stable human-readable program identity.
        role: Exclusive agent role implemented by the program.
        version: Semantic program version.
        model_profile_id: Default admitted model profile.
        system_instruction: Role instruction treated as trusted program text.
        output_contracts: Strict public model names emitted by the program.
        tool_policy_version: Version of deterministic role/tool policy.
        max_schema_repairs: Maximum validation-feedback repairs per call.
    """

    program_id: str
    role: AgentRole
    version: str
    model_profile_id: str
    system_instruction: str
    output_contracts: tuple[str, ...]
    tool_policy_version: str
    max_schema_repairs: int = 1

    def __post_init__(self) -> None:
        """Validate versioned identity and repair policy."""
        for value, label in (
            (self.program_id, "program_id"),
            (self.version, "version"),
            (self.model_profile_id, "model_profile_id"),
            (self.system_instruction, "system_instruction"),
            (self.tool_policy_version, "tool_policy_version"),
        ):
            if not str(value).strip():
                raise ValueError(f"{label} is required")
        if not self.output_contracts:
            raise ValueError("output_contracts are required")
        if not 0 <= self.max_schema_repairs <= 1:
            raise ValueError("max_schema_repairs must be zero or one")

    @property
    def program_digest(self) -> str:
        """Return the content digest used to detect program drift."""
        return json_payload_hash(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        """Return a stable public program manifest.

        Args:
            include_digest: Whether to include the derived content digest.

        Returns:
            JSON-native program manifest without credentials or prompts from a
            user session.
        """
        payload = {
            "program_id": self.program_id,
            "role": self.role.value,
            "version": self.version,
            "model_profile_id": self.model_profile_id,
            "system_instruction": self.system_instruction,
            "output_contracts": list(self.output_contracts),
            "tool_policy_version": self.tool_policy_version,
            "max_schema_repairs": self.max_schema_repairs,
        }
        if include_digest:
            payload["program_digest"] = self.program_digest
        return payload


class ModelProfileRegistry:
    """Immutable lookup of admitted model profiles."""

    def __init__(self, profiles: Iterable[ModelProfile]) -> None:
        """Create a unique profile registry.

        Args:
            profiles: Admitted model profiles.
        """
        values = tuple(profiles)
        indexed = {profile.profile_id: profile for profile in values}
        if not indexed:
            raise ValueError("at least one model profile is required")
        if len(indexed) != len(values):
            raise ValueError("model profile IDs must be unique")
        self._profiles = indexed

    def get(self, profile_id: str) -> ModelProfile:
        """Resolve one exact admitted model profile."""
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise KeyError(f"unknown model profile: {profile_id}") from exc

    def public_manifest(self) -> dict[str, Any]:
        """Return sorted credential-free profiles and registry identity."""
        profiles = [self._profiles[key].to_dict() for key in sorted(self._profiles)]
        return {
            "registry_id": json_payload_hash({"profiles": profiles}),
            "profiles": profiles,
        }


class AgentProgramRegistry:
    """Immutable role and identity lookup for admitted agent programs."""

    def __init__(self, programs: Iterable[AgentProgram]) -> None:
        """Create a registry with one program per first-slice role."""
        values = tuple(programs)
        by_id = {program.program_id: program for program in values}
        by_role = {program.role: program for program in values}
        if len(by_id) != len(values):
            raise ValueError("agent program IDs must be unique")
        if len(by_role) != len(values):
            raise ValueError("only one program per role is allowed")
        missing = set(AgentRole) - set(by_role)
        if missing:
            raise ValueError(
                "agent programs are missing roles: "
                + ", ".join(sorted(item.value for item in missing))
            )
        self._by_id = by_id
        self._by_role = by_role

    def get(self, program_id: str) -> AgentProgram:
        """Resolve one exact admitted program identity."""
        try:
            return self._by_id[program_id]
        except KeyError as exc:
            raise KeyError(f"unknown agent program: {program_id}") from exc

    def for_role(self, role: AgentRole) -> AgentProgram:
        """Resolve the admitted program for one role."""
        return self._by_role[role]

    def public_manifest(self) -> dict[str, Any]:
        """Return sorted program manifests and their catalogue identity."""
        programs = [self._by_id[key].to_dict() for key in sorted(self._by_id)]
        return {
            "registry_id": json_payload_hash({"programs": programs}),
            "programs": programs,
        }


def development_model_profiles() -> ModelProfileRegistry:
    """Return the active model profile registry for bounded evaluation."""
    return ModelProfileRegistry(
        (
            ModelProfile(
                profile_id=DEVELOPMENT_MODEL_PROFILE_ID,
                provider="ollama",
                model="lfm2.5:8b",
                model_revision=OLLAMA_LFM25_8B_DIGEST,
                base_url="http://127.0.0.1:11434",
                temperature=0.0,
                context_window_tokens=8_192,
                max_output_tokens=2_048,
                timeout_seconds=120.0,
                thinking=False,
            ),
        )
    )


def profile_environment(profile: ModelProfile) -> Mapping[str, str]:
    """Translate one profile into the existing provider-neutral client env.

    Args:
        profile: Credential-free model profile.

    Returns:
        Environment mapping understood by ``RuntimeConfiguredLlmClient``.
    """
    return {
        "TRADER_AGENTS_LLM_PROVIDER": profile.provider,
        "TRADER_AGENTS_LLM_MODEL": profile.model,
        "TRADER_AGENTS_LLM_MODEL_REVISION": profile.model_revision,
        "TRADER_AGENTS_LLM_BASE_URL": profile.base_url,
        "TRADER_AGENTS_LLM_TIMEOUT_SECONDS": str(profile.timeout_seconds),
    }
