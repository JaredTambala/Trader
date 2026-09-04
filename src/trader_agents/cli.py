"""Command-line entry point for first-slice agentic research sessions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import anyio

from trader_research.foundation import stable_research_id
from trader_research.governance import ResearchSession

from .contracts import OperatorCancellation, OperatorResponse
from .inputs import (
    composite_data_scope_from_session,
    strategy_build_contract_from_session,
    validate_runtime_pins,
)
from .observability_console import AgentConsoleConfig, agent_console_config
from .profiles import development_model_profiles
from .programs import first_slice_programs
from .catalogue import first_slice_tool_catalogue
from .runtime import runtime_from_environment, runtime_manifest


def main() -> None:
    """Parse CLI arguments, execute one operation, and print public JSON."""
    parser = _parser()
    args = parser.parse_args()
    try:
        console_config = agent_console_config(
            level_override=args.log_level,
            format_override=args.log_format,
        )
        if args.command == "manifest":
            _print_json(runtime_manifest())
            return
        session = _load_session(args.session)
        if args.command == "validate-session":
            _validate_session(session)
            _print_json(
                {
                    "ok": True,
                    "session_id": session.session_id,
                    "session_digest": session.session_digest,
                }
            )
            return
        outcome = anyio.run(_run_command, args, session, console_config)
        _print_json(outcome.model_dump(mode="json"))
    except (OSError, RuntimeError, ValueError) as exc:
        _print_json(
            {
                "ok": False,
                "error": {
                    "code": "agent_cli_failed",
                    "message": str(exc),
                },
            },
            stream=sys.stderr,
        )
        raise SystemExit(2) from None


async def _run_command(
    args: argparse.Namespace,
    session: ResearchSession,
    console_config: AgentConsoleConfig,
) -> Any:
    """Open runtime resources and execute the selected lifecycle operation."""
    async with runtime_from_environment(
        setup_checkpoint_schema=bool(args.setup_checkpoint_schema),
        console_config=console_config,
    ) as runtime:
        if args.command == "run":
            return await runtime.start(session)
        if args.command == "resume":
            return await runtime.resume(
                session,
                OperatorResponse(
                    approved=args.approved == "true",
                    answer=args.answer,
                    operator_id=args.operator_id,
                ),
            )
        if args.command == "cancel":
            return await runtime.cancel(
                session,
                OperatorCancellation(
                    operator_id=args.operator_id,
                    reason=args.reason,
                ),
            )
        if args.command == "inspect":
            return _PublicMapping(await runtime.inspect(session))
    raise ValueError(f"unsupported command: {args.command}")


class _PublicMapping:
    """Small adapter giving inspected mappings the CLI output interface."""

    def __init__(self, payload: dict[str, Any]) -> None:
        """Retain the already-redacted operator projection."""
        self._payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        """Return the JSON-native public projection."""
        if mode != "json":
            raise ValueError("CLI public mappings support only JSON mode")
        return dict(self._payload)


def _parser() -> argparse.ArgumentParser:
    """Build the documented non-interactive command grammar."""
    parser = argparse.ArgumentParser(
        prog="trader-agent",
        description="Run the first-slice Trader research-agent system.",
    )
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=("DEBUG", "INFO"),
        default=None,
        help="stderr event threshold; overrides TRADER_AGENTS_LOG_LEVEL",
    )
    parser.add_argument(
        "--log-format",
        type=str.lower,
        choices=("human", "json"),
        default=None,
        help="stderr event format; overrides TRADER_AGENTS_LOG_FORMAT",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "manifest",
        help="print exact model, program, and MCP catalogue identities",
    )
    validate = subparsers.add_parser(
        "validate-session",
        help="validate a session file without starting external resources",
    )
    validate.add_argument("--session", type=Path, required=True)
    for name, help_text in (
        ("run", "start or recover a research session"),
        ("inspect", "print redacted checkpoint state"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--session", type=Path, required=True)
        command.add_argument(
            "--setup-checkpoint-schema",
            action="store_true",
            help="run idempotent LangGraph Postgres schema setup",
        )
    resume = subparsers.add_parser(
        "resume",
        help="resume an operator-interrupted research session",
    )
    resume.add_argument("--session", type=Path, required=True)
    resume.add_argument("--approved", choices=("true", "false"), required=True)
    resume.add_argument("--answer", required=True)
    resume.add_argument("--operator-id", required=True)
    resume.add_argument("--setup-checkpoint-schema", action="store_true")
    cancel = subparsers.add_parser(
        "cancel",
        help="cancel a checkpointed research session",
    )
    cancel.add_argument("--session", type=Path, required=True)
    cancel.add_argument("--reason", required=True)
    cancel.add_argument("--operator-id", required=True)
    cancel.add_argument("--setup-checkpoint-schema", action="store_true")
    return parser


def _load_session(path: Path) -> ResearchSession:
    """Load one strict canonical session JSON document."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"session file is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("session file must contain one JSON object")
    return ResearchSession.from_dict(payload)


def _validate_session(session: ResearchSession) -> None:
    """Validate runtime pins plus first-slice Data/build entry contracts."""
    catalogue = first_slice_tool_catalogue()
    validate_runtime_pins(
        session,
        model_profiles=development_model_profiles(),
        agent_programs=first_slice_programs(),
        tool_catalogue=catalogue,
    )
    composite_data_scope_from_session(session)
    strategy_branch = stable_research_id(
        "agent_branch",
        {"session_id": session.session_id, "task_id": "strategy"},
    )
    strategy_build_contract_from_session(session, branch_id=strategy_branch)


def _print_json(payload: Any, *, stream: Any = sys.stdout) -> None:
    """Print stable human-readable JSON without permissive coercion."""
    print(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        file=stream,
    )


if __name__ == "__main__":
    main()
