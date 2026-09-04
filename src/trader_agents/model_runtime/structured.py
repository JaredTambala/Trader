"""Strict bounded model invocation for public agent control decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import time
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from .client import (
    LlmClient,
    LlmJsonCompletion,
    LlmJsonRequest,
    LlmMessage,
    LlmTokenUsage,
)
from trader_agents.observability.emitter import AgentEventEmitter
from trader_agents.observability.events import (
    AgentErrorCategory,
    AgentEventError,
    AgentEventName,
)
from trader_agents.observability.projections import project_budget_usage
from trader_agents.mcp.policy import BudgetLedger
from .profiles import AgentProgram, ModelProfile
from trader_agents.observability.tracing import (
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
    call_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    schema_repairs: int


@dataclass(frozen=True)
class _ModelTraceIdentity:
    """Public identities joining one invocation, provider call, and validation."""

    role: str
    invocation_id: str
    call_id: str
    output_contract: str
    schema_repair: int

    def attributes(self) -> dict[str, str | int]:
        """Return the JSON-native public identity projection."""
        return {
            "trader.model_invocation_id": self.invocation_id,
            "trader.model_call_id": self.call_id,
            "trader.output_contract": self.output_contract,
            "trader.schema_repair": self.schema_repair,
        }


@dataclass(frozen=True)
class StructuredModelRunner:
    """Invoke one versioned model program with strict schema validation.

    Attributes:
        client: Provider-neutral structured JSON model client.
        trace_sink: Optional redacted observability sink.
        event_emitter: Process-scoped semantic event stream.
    """

    client: LlmClient
    trace_sink: TraceSink = NoOpTraceSink()
    event_emitter: AgentEventEmitter = field(default_factory=AgentEventEmitter)

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
        invocation_id = uuid4().hex

        for repair in range(program.max_schema_repairs + 1):
            ledger.ensure_model_call_available()
            trace_identity = _ModelTraceIdentity(
                role=program.role.value,
                invocation_id=invocation_id,
                call_id=uuid4().hex,
                output_contract=output_type.__name__,
                schema_repair=repair,
            )
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
                context_window_tokens=profile.context_window_tokens,
                max_tokens=profile.max_output_tokens,
                thinking=profile.thinking,
            )
            event_fields = {
                "role": program.role.value,
                "output_contract": output_type.__name__,
                "schema_repair": repair,
                "model_provider": profile.provider,
                "model_name": profile.model,
            }
            self.event_emitter.emit(
                name=AgentEventName.MODEL_CALL_STARTED,
                correlation=correlation,
                role=program.role.value,
                call_id=trace_identity.call_id,
                fields=event_fields,
            )
            started = time.perf_counter()
            try:
                with self.trace_sink.span(
                    f"agent.model.{program.role.value}",
                    span_type="LLM",
                    attributes=correlated_attributes(
                        correlation,
                        **trace_identity.attributes(),
                    ),
                ):
                    completion = await _complete_with_usage(self.client, request)
            except BaseException:
                duration_ms = _elapsed_milliseconds(started)
                _trace_model_result(
                    self.trace_sink,
                    correlation=correlation,
                    identity=trace_identity,
                    provider=profile.provider,
                    model=profile.model,
                    input_tokens=0,
                    output_tokens=0,
                    duration_ms=duration_ms,
                    result_ok=False,
                )
                try:
                    ledger.record_model_call(
                        input_tokens=0,
                        output_tokens=0,
                        duration_ms=duration_ms,
                    )
                except Exception:
                    # Preserve the provider or process failure that prevented a
                    # usable result; the public result span still accounts for
                    # the attempted call during qualification.
                    pass
                self.event_emitter.emit(
                    name=AgentEventName.MODEL_CALL_FAILED,
                    correlation=correlation,
                    role=program.role.value,
                    call_id=trace_identity.call_id,
                    fields={**event_fields, "duration_ms": duration_ms},
                    error=AgentEventError(
                        code="model_provider_failed",
                        category=AgentErrorCategory.MODEL_PROVIDER,
                        message="The configured model provider call failed.",
                    ),
                )
                raise
            duration_ms = _elapsed_milliseconds(started)
            _trace_model_result(
                self.trace_sink,
                correlation=correlation,
                identity=trace_identity,
                provider=completion.provider,
                model=completion.model,
                input_tokens=completion.usage.input_tokens,
                output_tokens=completion.usage.output_tokens,
                duration_ms=duration_ms,
                result_ok=True,
            )
            ledger.record_model_call(
                input_tokens=completion.usage.input_tokens,
                output_tokens=completion.usage.output_tokens,
                duration_ms=duration_ms,
            )
            total_input_tokens += completion.usage.input_tokens
            total_output_tokens += completion.usage.output_tokens
            total_duration_ms += duration_ms
            response_fields = {
                **event_fields,
                "input_tokens": completion.usage.input_tokens,
                "output_tokens": completion.usage.output_tokens,
                "duration_ms": duration_ms,
            }
            self.event_emitter.emit(
                name=AgentEventName.MODEL_RESPONSE_RECEIVED,
                correlation=correlation,
                role=program.role.value,
                call_id=trace_identity.call_id,
                fields=response_fields,
            )
            self.event_emitter.emit(
                name=AgentEventName.MODEL_CALL_COMPLETED,
                correlation=correlation,
                role=program.role.value,
                call_id=trace_identity.call_id,
                fields=response_fields,
            )
            self.event_emitter.emit(
                name=AgentEventName.BUDGET_UPDATED,
                correlation=correlation,
                role=program.role.value,
                call_id=trace_identity.call_id,
                fields=project_budget_usage(ledger.usage),
            )
            try:
                output = output_type.model_validate(completion.payload)
            except ValidationError as exc:
                last_errors = _public_validation_errors(exc)
                _trace_model_validation(
                    self.trace_sink,
                    correlation=correlation,
                    identity=trace_identity,
                    schema_valid=False,
                    validation_error_count=len(last_errors),
                )
                self.event_emitter.emit(
                    name=AgentEventName.MODEL_SCHEMA_REJECTED,
                    correlation=correlation,
                    role=program.role.value,
                    call_id=trace_identity.call_id,
                    fields={
                        "output_contract": output_type.__name__,
                        "schema_repair": repair,
                        "validation_error_count": len(last_errors),
                        "validation_error_locations": [
                            item["location"] for item in last_errors[:8]
                        ],
                    },
                    error=AgentEventError(
                        code="model_schema_invalid",
                        category=AgentErrorCategory.SCHEMA_VALIDATION,
                        message=(
                            "The model response did not match its public output schema."
                        ),
                        retryable=repair < program.max_schema_repairs,
                    ),
                )
                if repair >= program.max_schema_repairs:
                    raise StructuredOutputError(
                        f"{program.program_id} failed {output_type.__name__} validation",
                        validation_errors=last_errors,
                    ) from exc
                continue
            _trace_model_validation(
                self.trace_sink,
                correlation=correlation,
                identity=trace_identity,
                schema_valid=True,
                validation_error_count=0,
            )
            self.event_emitter.emit(
                name=AgentEventName.MODEL_SCHEMA_ACCEPTED,
                correlation=correlation,
                role=program.role.value,
                call_id=trace_identity.call_id,
                fields={
                    "output_contract": output_type.__name__,
                    "schema_repair": repair,
                },
            )
            return ModelInvocationResult(
                output=output,
                call_id=trace_identity.call_id,
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


def _trace_model_result(
    trace_sink: TraceSink,
    *,
    correlation: TraceCorrelation,
    identity: _ModelTraceIdentity,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int,
    result_ok: bool,
) -> None:
    """Emit bounded terminal accounting for one physical provider call."""
    with trace_sink.span(
        f"agent.model_result.{identity.role}",
        span_type="LLM",
        attributes=correlated_attributes(
            correlation,
            **{
                **identity.attributes(),
                "trader.model_provider": provider,
                "trader.model_name": model,
                "trader.input_tokens": input_tokens,
                "trader.output_tokens": output_tokens,
                "trader.duration_ms": duration_ms,
                "trader.result_ok": result_ok,
            },
        ),
    ):
        pass


def _trace_model_validation(
    trace_sink: TraceSink,
    *,
    correlation: TraceCorrelation,
    identity: _ModelTraceIdentity,
    schema_valid: bool,
    validation_error_count: int,
) -> None:
    """Emit the strict public-schema verdict for one completed response."""
    with trace_sink.span(
        f"agent.model_validation.{identity.role}",
        span_type="LLM",
        attributes=correlated_attributes(
            correlation,
            **{
                **identity.attributes(),
                "trader.schema_valid": schema_valid,
                "trader.validation_error_count": validation_error_count,
            },
        ),
    ):
        pass


def _elapsed_milliseconds(started: float) -> int:
    """Return a non-negative rounded duration from a monotonic start time."""
    return max(0, round((time.perf_counter() - started) * 1_000))


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
