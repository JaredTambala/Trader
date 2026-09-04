"""Fresh-process worker for one Agent qualification lifecycle attempt.

The module is a subprocess entry point owned by application-runtime recovery
tests; it emits bounded public state and never acts as a reusable product CLI.
"""

from __future__ import annotations

import argparse
from functools import partial
import json
import os
import sys
from typing import Any

import anyio

from tests.trader_agents.coordination.support.agentic_faults import (
    InjectedProcessFault,
    NO_FAULT,
    RECOVERY_FAULT_MODES,
    recovery_mcp_client_decorator,
)
from trader_agents.contracts.domain import OperatorCancellation
from trader_agents.application.runtime import runtime_from_environment
from trader_research.governance import ResearchSession


FAULT_EXIT_CODE = 86
FAULT_RESULT_PREFIX = "AGENTIC_WORKER_FAULT="
STATE_RESULT_PREFIX = "AGENTIC_WORKER_STATE="


async def _run(
    session: ResearchSession,
    *,
    fault_mode: str,
    setup_checkpoint_schema: bool,
    action: str,
) -> dict[str, Any]:
    """Start, recover, or cancel a session and return its public state."""
    async with runtime_from_environment(
        os.environ,
        setup_checkpoint_schema=setup_checkpoint_schema,
        mcp_client_decorator=recovery_mcp_client_decorator(fault_mode),
    ) as runtime:
        if action == "start":
            await runtime.start(session)
        elif action == "cancel":
            await runtime.cancel(
                session,
                OperatorCancellation(
                    operator_id=session.operator_id,
                    reason="Controlled fresh-process cancellation qualification.",
                ),
            )
        else:  # pragma: no cover - argparse rejects this first
            raise ValueError(f"unknown worker action: {action}")
        return dict(await runtime.inspect(session))


def main(argv: list[str] | None = None) -> int:
    """Read one strict session from stdin and execute a lifecycle attempt."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--fault-mode", choices=sorted(RECOVERY_FAULT_MODES))
    parser.add_argument("--action", choices=("start", "cancel"), default="start")
    parser.add_argument("--setup-checkpoint-schema", action="store_true")
    args = parser.parse_args(argv)
    raw = json.load(sys.stdin)
    if not isinstance(raw, dict) or set(raw) != {"session"}:
        raise ValueError("worker input must contain only session")
    session_payload = raw["session"]
    if not isinstance(session_payload, dict):
        raise ValueError("worker session must be a JSON object")
    session = ResearchSession.from_dict(session_payload)
    fault_mode = str(args.fault_mode or NO_FAULT)
    try:
        state = anyio.run(
            partial(
                _run,
                session,
                fault_mode=fault_mode,
                setup_checkpoint_schema=bool(args.setup_checkpoint_schema),
                action=str(args.action),
            )
        )
    except InjectedProcessFault as fault:
        print(
            FAULT_RESULT_PREFIX
            + json.dumps(
                {
                    "mode": fault.mode,
                    "role": fault.role.value,
                    "tool_name": fault.tool_name,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            flush=True,
        )
        return FAULT_EXIT_CODE
    print(
        STATE_RESULT_PREFIX + json.dumps(state, sort_keys=True, separators=(",", ":")),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
