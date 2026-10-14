"""Fresh-process MCP, Console and canonical reader for the UJ-09 campaign.

All entry points require the campaign's explicit disposable database. The
authentication provider is test-only composition, not a deployment authenticator.
"""

from __future__ import annotations

import json
import importlib
import os
from pathlib import Path
import re
import sys

from fastapi import Request
from pydantic import SecretStr
import psycopg

from trader_console_api import create_app
from trader_console_api.configuration import ConsoleApiSettings
from trader_console_api.contracts import BrokerAccountBinding, ConsoleEnvironment, ConsoleScope, TraderPrincipal
from trader_research.foundation import json_payload_hash
from trader_research.governance import NextResearchDecision
from trader_research.governance.blocked_decisions import validate_blocked_evidence
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.cross_package.qualification.support.uj08_campaign import REPO_ROOT, verify_chain


def source_modules() -> dict[str, str]:
    """Reject processes importing another checkout instead of the tested sources."""
    names = ("trader_console_api.application", "trader_research.governance.next_decisions",
             "trader_research.governance.blocked_decisions", "trader_mcp.runtime.server")
    paths = {name: str(Path(importlib.import_module(name).__file__).resolve()) for name in names}
    assert all(Path(path).is_relative_to(REPO_ROOT / "src") for path in paths.values()), paths
    return paths


def campaign_dsn() -> str:
    """Reject anything except this campaign's randomly named disposable database."""
    source_modules()
    dsn = os.environ["UJ09_DSN"]
    settings = psycopg.conninfo.conninfo_to_dict(dsn)
    if not re.fullmatch(r"trader_uj09_[0-9a-f]{32}_test", settings.get("dbname", "")):
        raise ValueError("UJ-09 requires its own disposable campaign database")
    if settings.get("options"):
        raise ValueError("UJ-09 owns public tables in a separate database")
    return dsn


class CampaignAuthentication:
    """Bind this loopback-only test process to one explicit principal."""

    async def authenticate(self, request: Request) -> TraderPrincipal:
        """Resolve the process-owned identity, never a browser-supplied identity."""
        del request
        return TraderPrincipal(principal_id=os.environ["UJ09_PRINCIPAL"])


def api() -> None:
    """Serve production routers and repositories over the test database."""
    import uvicorn

    settings = ConsoleApiSettings(
        database_url=SecretStr(campaign_dsn()),
        scope=ConsoleScope(
            scope_id="uj09-qualification",
            display_name="Governed experiment qualification",
            environment=ConsoleEnvironment.SYNTHETIC_DEMO,
            broker_account_binding=BrokerAccountBinding.NOT_APPLICABLE,
        ),
    )
    uvicorn.run(create_app(settings, authentication_provider=CampaignAuthentication()),
                host="127.0.0.1", port=int(os.environ["UJ09_API_PORT"]))


def mcp() -> None:
    """Expose real production registrations to the governed experiment producer."""
    from trader.event_store import PostgresEventStore
    from trader_mcp.catalogue.policy import load_local_environment
    from trader_mcp.runtime.server import create_server
    from trader_research.infrastructure.postgres import PostgresResearchJobStore

    events = PostgresEventStore(dsn=campaign_dsn())
    artifacts = PostgresResearchArtifactStore(dsn=campaign_dsn())
    try:
        jobs = PostgresResearchJobStore(artifacts.connection())
        server = create_server(
            load_local_environment("env.template"),
            event_store_provider=lambda: events,
            research_artifact_store_provider=lambda: artifacts,
            research_job_store_provider=lambda: jobs,
        )
        server.run(transport="stdio")
    finally:
        artifacts.close()
        events.close()


def verify() -> None:
    """Reload exact immutable decisions and their complete producer evidence chain."""
    dsn = campaign_dsn()
    chain = verify_chain(dsn, os.environ["UJ09_JOB_ID"], os.environ["UJ09_OUTCOME_ID"])
    store = PostgresResearchArtifactStore(dsn=dsn, ensure_schema=False)
    try:
        decisions = []
        for artifact_id in json.loads(os.environ["UJ09_DECISION_IDS"]):
            record = store.load_artifact_record("research_next_decision", artifact_id)
            payload = dict(record.payload)
            validate_blocked_evidence(NextResearchDecision.from_dict(payload), store.load_artifact_record)
            for reference in (
                payload["source_run_ref"], payload["data_ref"],
                *payload["implementation_refs"], payload["blocked_evidence"]["outcome_ref"],
            ):
                canonical = store.load_artifact_record(reference["artifact_type"], reference["artifact_id"])
                assert canonical.uri == reference["uri"]
                assert canonical.domain_owner == reference["domain_owner"]
                assert json_payload_hash(canonical.payload) == reference["metadata"]["payload_sha256"]
            assert payload["blocked_evidence"]["blockers"] == chain["terminal"]["blockers"]
            assert payload["blocked_evidence"]["scientific_review_status"] == "not_assessed"
            decisions.append(payload)
        print(json.dumps({"canonical_evidence": chain, "decisions": decisions, "loaded_modules": source_modules()}, sort_keys=True))
    finally:
        store.close()


if __name__ == "__main__":
    {"api": api, "mcp": mcp, "verify": verify}[sys.argv[1]]()
