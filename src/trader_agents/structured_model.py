"""Strict bounded model invocation for public agent control decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import time
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .llm_client import (
    LlmClient,
    LlmJsonCompletion,
    LlmJsonRequest,
    LlmMessage,
    LlmTokenUsage,
)
from .policy import BudgetLedger
from .profiles import AgentProgram, ModelProfile
from .tracing import (
    NoOpTraceSink,
    TraceCorrelation,
    TraceSink,
    correlated_attributes,
)


OutputT = TypeVar("OutputT", bound=BaseModel)
_MAX_PUBLIC_CONTEXT_BYTES = 96_000


class StructuredOutputError(RuntimeError):
    """Raised when a model cannot satisfy its strict public output contract."""

    def __init__(
        self,
        message: str,
        *,
        validation_errors: list[dict[str, Any]],
    ) -> None:
        """Create an actionable error without retaining raw model output."""
        super().__init__(message)
        self.validation_errors = validation_errors


@dataclass(frozen=True)
class ModelInvocationResult(Generic[OutputT]):
    """Validated public output and bounded invocation measurements."""

    output: OutputT
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    schema_repairs: int


@dataclass(frozen=True)
class StructuredModelRunner:
    """Invoke one versioned model program with strict schema validation.

    Attributes:
        client: Provider-neutral structured JSON model client.
        trace_sink: Optional redacted observability sink.
    """

    client: LlmClient
    trace_sink: TraceSink = NoOpTraceSink()

    async def invoke(
        self,
        *,
        program: AgentProgram,
        profile: ModelProfile,
        output_type: type[OutputT],
        instruction: str,
        public_context: Mapping[str, Any],
        ledger: BudgetLedger,
        correlation: TraceCorrelation,
    ) -> ModelInvocationResult[OutputT]:
        """Return one validated public model output with one bounded repair.

        Args:
            program: Exact admitted role program.
            profile: Exact admitted provider/model profile.
            output_type: Strict Pydantic public output contract.
            instruction: Task-specific trusted program instruction.
            public_context: Bounded JSON-native session/evidence projection.
            ledger: Session resource ledger updated after every provider call.
            correlation: Stable redacted trace identities.

        Returns:
            Validated output and aggregate usage for this invocation.

        Raises:
            ValueError: If program/profile/output identity or context is invalid.
            StructuredOutputError: If the model fails strict validation after
                the allowed repair.
        """
        self._validate_invocation(program, profile, output_type, instruction)
        context_json = _bounded_context_json(public_context)
        schema = output_type.model_json_schema()
        schema_json = json.dumps(schema, sort_keys=True, separators=(",", ":"))
        base_messages = (
            LlmMessage(role="system", content=program.system_instruction),
            LlmMessage(
                role="user",
                content=(
                    f"{instruction.strip()}\n\nPublic context:\n{context_json}"
                    f"\n\nReturn only JSON matching this schema:\n{schema_json}"
                ),
            ),
        )
        total_input_tokens = 0
        total_output_tokens = 0
        total_duration_ms = 0
        last_errors: list[dict[str, Any]] = []

        for repair in range(program.max_schema_repairs + 1):
            ledger.ensure_model_call_available()
            messages: tuple[LlmMessage, ...] = base_messages
            if repair:
                messages = (
                    *base_messages,
                    LlmMessage(
                        role="user",
                        content=(
                            "The previous public JSON failed validation. Correct "
                            "only the structure and return the complete object. "
                            "Do not add authority or evidence. Validation errors: "
                            + json.dumps(last_errors, sort_keys=True)[:8_000]
                        ),
                    ),
                )
            request = LlmJsonRequest(
                messages=messages,
                response_schema=schema,
                model=profile.model,
                temperature=profile.temperature,
                max_tokens=profile.max_output_tokens,
                thinking=profile.thinking,
            )
            started = time.perf_counter()
            with self.trace_sink.span(
                f"agent.model.{program.role.value}",
                span_type="LLM",
                attributes=correlated_attributes(
                    correlation,
                    **{
                        "trader.output_contract": output_type.__name__,
                        "trader.schema_repair": repair,
                    },
                ),
            ):
                completion = await _complete_with_usage(self.client, request)
            duration_ms = max(0, round((time.perf_counter() - started) * 1_000))
            ledger.record_model_call(
                input_tokens=completion.usage.input_tokens,
                output_tokens=completion.usage.output_tokens,
                duration_ms=duration_ms,
            )
            total_input_tokens += completion.usage.input_tokens
            total_output_tokens += completion.usage.output_tokens
            total_duration_ms += duration_ms
            try:
                output = output_type.model_validate(completion.payload)
            except ValidationError as exc:
                last_errors = _public_validation_errors(exc)
                if repair >= program.max_schema_repairs:
                    raise StructuredOutputError(
                        f"{program.program_id} failed {output_type.__name__} validation",
                        validation_errors=last_errors,
                    ) from exc
                continue
            return ModelInvocationResult(
                output=output,
                provider=completion.provider,
                model=completion.model,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                duration_ms=total_duration_ms,
                schema_repairs=repair,
            )
        raise AssertionError("structured model loop terminated unexpectedly")

    @staticmethod
    def _validate_invocation(
        program: AgentProgram,
        profile: ModelProfile,
        output_type: type[BaseModel],
        instruction: str,
    ) -> None:
        """Require exact program/profile/output identity before provider use."""
        if program.model_profile_id != profile.profile_id:
            raise ValueError("agent program and model profile do not match")
        if output_type.__name__ not in program.output_contracts:
            raise ValueError(
                f"{output_type.__name__} is not admitted by {program.program_id}"
            )
        if not instruction.strip():
            raise ValueError("model invocation instruction is required")


async def _complete_with_usage(
    client: LlmClient,
    request: LlmJsonRequest,
) -> LlmJsonCompletion:
    """Use provider usage metadata when available, otherwise report zero."""
    usage_method = getattr(client, "complete_json_with_usage", None)
    if callable(usage_method):
        completion = await usage_method(request)
        if not isinstance(completion, LlmJsonCompletion):
            raise TypeError("complete_json_with_usage returned an invalid value")
        return completion
    payload = await client.complete_json(request)
    return LlmJsonCompletion(
        payload=payload,
        usage=LlmTokenUsage(),
        provider="unknown",
        model=request.model or "unknown",
    )


def _bounded_context_json(public_context: Mapping[str, Any]) -> str:
    """Serialize public context and reject non-JSON or unbounded values."""
    try:
        encoded = json.dumps(
            dict(public_context),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("public model context must be JSON-native") from exc
    if len(encoded) > _MAX_PUBLIC_CONTEXT_BYTES:
        raise ValueError("public model context exceeds the 96000-byte limit")
    return encoded.decode("utf-8")


def _public_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    """Return bounded validation locations/messages without raw input values."""
    return [
        {
            "type": str(item.get("type") or "validation_error"),
            "location": [str(part) for part in item.get("loc", ())],
            "message": str(item.get("msg") or "invalid value")[:500],
        }
        for item in exc.errors(include_input=False, include_url=False)[:32]
    ]
