from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import anyio

from tests.support.duckdb_store import DuckDBEventStore
from tests.test_research_backtests import _config
from trader_mcp.constants import (
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
    EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL,
    KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
    KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT_TOOL,
    KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
    KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
    KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
    KNOWLEDGE_INGEST_DOCUMENTS_TOOL,
    KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
    KNOWLEDGE_REGISTER_SOURCE_TOOL,
    KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
    RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL,
    RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
    RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL,
    RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL,
    RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL,
    RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
    RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.artifact_store import InMemoryResearchArtifactStore
from trader_research.domain import (
    EVALUATION_REPORT,
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    METHODOLOGY_EVIDENCE_PACKET,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
    PORTFOLIO_BACKTEST_RUN_REF,
    RISK_MANAGER_CANDIDATE,
    STRATEGY_CANDIDATE,
    STRATEGY_RISK_STACK,
)
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.store import JsonKnowledgeStore


PAIR_SYMBOLS = ("PAIR_A", "PAIR_B")
PAIR_START = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)
PAIR_END = datetime(2026, 3, 2, 14, 35, tzinfo=timezone.utc)


def test_mcp_rich_methodology_pairs_chain_runs_to_portfolio_evaluation(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    source_dir = artifact_root / "knowledge_sources"
    source_dir.mkdir(parents=True)
    book_pdf = source_dir / "algorithmic_trading_pairs.pdf"
    internal_note_pdf = source_dir / "operator_pairs_note.pdf"
    _write_text_pdf(book_pdf, _pairs_methodology_lines())
    _write_text_pdf(internal_note_pdf, _pairs_methodology_lines())

    event_store = DuckDBEventStore(str(tmp_path / "pairs_events.duckdb"))
    _load_pairs_bars(event_store)
    knowledge_store = JsonKnowledgeStore(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    environment = replace(
        load_local_environment("env.template"),
        artifact_root=artifact_root,
        allow_backtests=True,
    )
    server = create_server(
        environment,
        event_store_provider=lambda: event_store,
        knowledge_embedding_provider=DeterministicEmbeddingProvider(),
        knowledge_store_provider=lambda: knowledge_store,
        research_artifact_store_provider=lambda: artifact_store,
        backtest_config_provider=lambda: _pairs_config(tmp_path),
    )

    async def _run() -> None:
        registered = await server.call_tool(
            KNOWLEDGE_REGISTER_SOURCE_TOOL,
            {
                "path": str(book_pdf),
                "title": "Algorithmic Trading And Quantitative Strategies",
                "source_type": "method_textbook",
                "canonical_citation": "Algorithmic Trading And Quantitative Strategies, chapter fixture",
                "topics": ["pairs trading", "cointegration"],
                "method_families": ["statistical_arbitrage"],
            },
        )
        source_id = registered.structuredContent["data"]["knowledge_source_manifest"]["source_id"]
        ingested = await server.call_tool(KNOWLEDGE_INGEST_DOCUMENTS_TOOL, {"source_ids": [source_id]})
        discovered = await server.call_tool(
            KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
            {
                "source_ids": [source_id],
                "method_families": ["statistical_arbitrage"],
                "neighbor_radius": 1,
                "max_candidates": 2,
            },
        )
        candidate_ref = discovered.structuredContent["artifacts"]["methodology_candidates"][0]
        assembled = await server.call_tool(
            KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
            {"methodology_candidate_uri": candidate_ref["uri"], "readiness_goal": "strategy_template"},
        )
        evidence_packet_ref = assembled.structuredContent["artifacts"]["methodology_evidence_packet"]
        extracted = await server.call_tool(
            KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
            {"evidence_packet_uri": evidence_packet_ref["uri"]},
        )
        extracted_candidate = extracted.structuredContent["data"]["methodology_candidate"]
        extraction_ref = extracted.structuredContent["artifacts"]["methodology_field_extraction_report"]
        validated = await server.call_tool(
            KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
            {"extraction_report_uri": extraction_ref["uri"]},
        )
        validation_ref = validated.structuredContent["artifacts"]["methodology_candidate_validation_report"]
        unsupported_override_draft = await server.call_tool(
            KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT_TOOL,
            {
                "methodology_candidate_validation_uri": validation_ref["uri"],
                "method_id": "pairs_mean_reversion",
                "title": "Pairs Mean Reversion",
                "family": "statistical_arbitrage",
            },
        )
        rich_draft = await server.call_tool(
            KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT_TOOL,
            {
                "methodology_candidate_validation_uri": validation_ref["uri"],
                "family": "statistical_arbitrage",
            },
        )
        rich_draft_payload = rich_draft.structuredContent["data"]["method_card_draft"]
        rich_draft_id = rich_draft_payload["method_card_id"]
        draft_strategy = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
            {
                "template_family": "pairs_mean_reversion",
                "method_package_refs": [],
                "rich_method_card_id": rich_draft_id,
            },
        )
        evidence_ref = extracted_candidate["extension_fields"]["statistical_arbitrage"]["spread_definition"][
            "evidence_refs"
        ][0]
        shallow_draft = await server.call_tool(
            KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
            {
                "method_id": "pairs_mean_reversion",
                "title": "Thin Pairs Method Card",
                "family": "statistical_arbitrage",
                "assumptions": ["spread relationship can mean revert after validation"],
                "inputs": ["paired price series"],
                "outputs": ["spread signal"],
                "failure_modes": ["structural break"],
                "evidence_refs": [evidence_ref],
            },
        )
        shallow_published = await server.call_tool(
            KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
            {
                "draft_method_card_id": shallow_draft.structuredContent["data"]["method_card_draft"]["method_card_id"],
                "approved_method_card_id": "method_card_thin_pairs_mcp_v1",
                "approved_by": "test",
                "approval_note": "approved shallow card for fail-closed assertion",
                "approve": True,
            },
        )
        shallow_strategy = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
            {
                "template_family": "pairs_mean_reversion",
                "method_package_refs": [],
                "rich_method_card_id": "method_card_thin_pairs_mcp_v1",
            },
        )
        missing_evidence_strategy = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
            {
                "template_family": "pairs_mean_reversion",
                "method_package_refs": [],
                "rich_method_card": _missing_field_evidence_rich_card(),
            },
        )
        unsupported_family_strategy = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
            {
                "template_family": "pairs_mean_reversion",
                "method_package_refs": [],
                "rich_method_card": _options_rich_card(),
            },
        )
        internal_note_validation = await _internal_note_validation_blocker(server, internal_note_pdf)

        published = await server.call_tool(
            KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
            {
                "draft_method_card_id": rich_draft_id,
                "approved_method_card_id": "method_card_pairs_mean_reversion_book_v1",
                "approved_by": "test",
                "approval_note": "source-backed pairs methodology reviewed",
                "approve": True,
            },
        )
        strategy = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
            {
                "template_family": "pairs_mean_reversion",
                "method_package_refs": [],
                "rich_method_card_id": "method_card_pairs_mean_reversion_book_v1",
                "parameters": {"lookback_period": 3, "entry_zscore": 1.0, "exit_zscore": 1.0, "max_pairs": 1},
                "sizing": {"target_qty_when_long": 1.0, "max_position_qty": 5.0},
            },
        )
        strategy_manifest = strategy.structuredContent["data"]["strategy_candidate_manifest"]
        strategy_validation = await server.call_tool(
            RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
            {"strategy_candidate_manifest": strategy_manifest},
        )
        strategy_report = strategy_validation.structuredContent["data"]["strategy_candidate_validation_report"]
        risk = await server.call_tool(
            RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL,
            {
                "template_family": "gross_exposure_cap",
                "parameters": {"max_gross_exposure": 1_000_000.0},
            },
        )
        risk_manifest = risk.structuredContent["data"]["risk_manager_candidate_manifest"]
        risk_validation = await server.call_tool(
            RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL,
            {"risk_manager_candidate_manifest": risk_manifest},
        )
        risk_report = risk_validation.structuredContent["data"]["risk_manager_candidate_validation_report"]
        stack = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL,
            {
                "strategy_candidate_validation_report": strategy_report,
                "risk_manager_validation_refs": [{"risk_manager_candidate_validation_report": risk_report}],
            },
        )
        stack_manifest = stack.structuredContent["data"]["strategy_risk_stack_manifest"]
        stack_validation = await server.call_tool(
            RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL,
            {"strategy_risk_stack_manifest": stack_manifest},
        )
        stack_report = stack_validation.structuredContent["data"]["strategy_risk_stack_validation_report"]
        inventory = await server.call_tool(DATA_GET_INVENTORY_TOOL, _data_args())
        quality = await server.call_tool(DATA_SUMMARIZE_QUALITY_TOOL, _data_args())
        portfolio = await server.call_tool(
            RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL,
            {
                "strategy_risk_stack_validation_report": stack_report,
                "dataset_manifest": inventory.structuredContent["data"]["dataset_manifest"],
                "data_quality_report": quality.structuredContent["data"]["data_quality_report"],
                "max_runs": 8,
            },
        )
        performance = await server.call_tool(
            EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL,
            {
                "portfolio_backtest_run_ref": portfolio.structuredContent["data"]["portfolio_backtest_run_ref"],
                "data_quality_report": quality.structuredContent["data"]["data_quality_report"],
            },
        )

        for result in (
            registered,
            ingested,
            discovered,
            extracted,
            validated,
            rich_draft,
            shallow_draft,
            shallow_published,
            published,
            strategy,
            strategy_validation,
            risk,
            risk_validation,
            stack,
            stack_validation,
            inventory,
            quality,
            portfolio,
            performance,
        ):
            assert result.isError is False, result.structuredContent

        assert ingested.structuredContent["data"]["knowledge_ingestion_report"]["chunks_created"] >= 1
        assert assembled.structuredContent["data"]["methodology_evidence_packet"]["artifact_type"] == (
            METHODOLOGY_EVIDENCE_PACKET
        )
        assert extracted_candidate["extension_fields"]["statistical_arbitrage"]["cointegration_test"][
            "evidence_refs"
        ]
        assert validated.structuredContent["data"]["methodology_candidate_validation_report"]["status"] == "passed"
        assert rich_draft_payload["card_format"] == "rich_method_card"
        assert published.structuredContent["data"]["method_card"]["source_methodology_candidate_id"] == (
            extracted_candidate["methodology_candidate_id"]
        )

        assert draft_strategy.isError is True
        assert "rich method card must be approved" in "\n".join(draft_strategy.structuredContent["data"]["blockers"])
        assert shallow_strategy.isError is True
        assert "unknown rich method_card_id" in "\n".join(shallow_strategy.structuredContent["data"]["blockers"])
        assert missing_evidence_strategy.isError is True
        assert "requires evidence_refs" in "\n".join(missing_evidence_strategy.structuredContent["data"]["blockers"])
        assert unsupported_family_strategy.isError is True
        assert "family must be statistical_arbitrage" in "\n".join(
            unsupported_family_strategy.structuredContent["data"]["blockers"]
        )
        assert unsupported_override_draft.isError is True
        assert "title must be supported" in "\n".join(
            error["message"] for error in unsupported_override_draft.structuredContent["errors"]
        )
        assert internal_note_validation.isError is True
        assert internal_note_validation.structuredContent["data"]["methodology_candidate_validation_report"][
            "status"
        ] == "blocked"
        assert "internal_note evidence" in "\n".join(
            internal_note_validation.structuredContent["data"]["methodology_candidate_validation_report"]["blockers"]
        )

        assert strategy_manifest["template_family"] == "pairs_mean_reversion"
        assert strategy_manifest["methodology_refs"][0]["artifact_id"] == "method_card_pairs_mean_reversion_book_v1"
        assert strategy_report["status"] == "passed"
        run_ref = portfolio.structuredContent["data"]["portfolio_backtest_run_ref"]
        assert run_ref["artifact_type"] == PORTFOLIO_BACKTEST_RUN_REF
        assert run_ref["data_scope"]["symbols"] == list(PAIR_SYMBOLS)
        assert portfolio.structuredContent["data"]["symbol_metrics"]["PAIR_A"]["trade_count"] > 0
        assert portfolio.structuredContent["data"]["symbol_metrics"]["PAIR_B"]["trade_count"] > 0
        assert portfolio.structuredContent["data"]["risk_decisions"]["manager_count"] == 1
        report = performance.structuredContent["data"]["evaluation_report"]
        assert report["status"] == "passed"
        assert report["backtest_kind"] == "portfolio"
        assert report["trade_stats"]["trade_count"] > 0
        artifact_types = {record.artifact_type for record in artifact_store.list_artifacts()}
        assert {
            METHODOLOGY_CANDIDATE,
            METHODOLOGY_EVIDENCE_PACKET,
            METHODOLOGY_FIELD_EXTRACTION_REPORT,
            METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
            STRATEGY_CANDIDATE,
            RISK_MANAGER_CANDIDATE,
            STRATEGY_RISK_STACK,
            PORTFOLIO_BACKTEST_RUN_REF,
            EVALUATION_REPORT,
        } <= artifact_types

    anyio.run(_run)


async def _internal_note_validation_blocker(server: Any, source_path: Path) -> Any:
    registered = await server.call_tool(
        KNOWLEDGE_REGISTER_SOURCE_TOOL,
        {
            "path": str(source_path),
            "title": "Operator Pairs Note",
            "source_type": "internal_note",
            "topics": ["pairs trading"],
            "method_families": ["statistical_arbitrage"],
        },
    )
    source_id = registered.structuredContent["data"]["knowledge_source_manifest"]["source_id"]
    await server.call_tool(KNOWLEDGE_INGEST_DOCUMENTS_TOOL, {"source_ids": [source_id]})
    discovered = await server.call_tool(
        KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
        {"source_ids": [source_id], "method_families": ["statistical_arbitrage"], "max_candidates": 1},
    )
    candidate_ref = discovered.structuredContent["artifacts"]["methodology_candidates"][0]
    assembled = await server.call_tool(
        KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
        {"methodology_candidate_uri": candidate_ref["uri"], "readiness_goal": "strategy_template"},
    )
    evidence_packet_ref = assembled.structuredContent["artifacts"]["methodology_evidence_packet"]
    extracted = await server.call_tool(
        KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
        {"evidence_packet_uri": evidence_packet_ref["uri"]},
    )
    candidate = extracted.structuredContent["data"]["methodology_candidate"]
    candidate["lineage"] = {
        **dict(candidate.get("lineage") or {}),
        "discovery": {
            **dict((candidate.get("lineage") or {}).get("discovery") or {}),
            "source_types": ["method_textbook"],
        },
    }
    return await server.call_tool(
        KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
        {"methodology_candidate": candidate},
    )


def _pairs_methodology_lines() -> tuple[str, ...]:
    return (
        "Chapter 7 Pairs Trading And Cointegration",
        "Pairs trading forms a spread between two related assets using aligned price series.",
        "The method estimates a hedge ratio with regression and tests the residual spread for cointegration and stationarity.",
        "The spread signal enters when the z-score crosses a threshold and exits when it mean reverts toward zero.",
        "The main failure mode is a structural break in the relationship between the pair legs.",
    )


def _load_pairs_bars(store: DuckDBEventStore) -> None:
    closes_by_symbol = {
        "PAIR_A": (100.0, 100.0, 100.0, 104.0, 100.0, 100.0),
        "PAIR_B": (100.0, 100.0, 100.0, 100.0, 100.0, 100.0),
    }
    for symbol, closes in closes_by_symbol.items():
        for index, close in enumerate(closes):
            ts = PAIR_START + timedelta(minutes=index)
            store.record_event(
                "stock_bar_events",
                {
                    "symbol": symbol,
                    "timeframe": "1Min",
                    "ts": ts,
                    "ingested_at": ts,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": 100.0 + index,
                    "trade_count": 1.0,
                    "vwap": close,
                    "source": "rich_pairs_fixture",
                },
            )


def _pairs_config(root: Path):
    return replace(
        _config(root),
        market_data_symbols=PAIR_SYMBOLS,
        db_path=str(root / "pairs_events.duckdb"),
    )


def _data_args() -> dict[str, Any]:
    return {
        "symbols": list(PAIR_SYMBOLS),
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": PAIR_START.isoformat().replace("+00:00", "Z"),
        "end": PAIR_END.isoformat().replace("+00:00", "Z"),
    }


def _missing_field_evidence_rich_card() -> dict[str, Any]:
    card = _base_rich_card("statistical_arbitrage")
    card["core_fields"] = {
        "data_requirements": {
            "required_inputs": {"value": ["price series"], "evidence_refs": [_fake_ref()]},
        },
        "signal_decision_logic": {
            "entry_rules": {"value": "enter on spread z-score divergence", "evidence_refs": [_fake_ref()]},
            "exit_rules": {"value": "exit when spread mean reverts", "evidence_refs": [_fake_ref()]},
        },
    }
    card["extension_fields"] = {
        "statistical_arbitrage": {
            "spread_definition": {"value": "spread between two assets", "evidence_refs": []},
            "hedge_ratio_method": {"value": "regression hedge ratio", "evidence_refs": [_fake_ref()]},
        }
    }
    return card


def _options_rich_card() -> dict[str, Any]:
    card = _base_rich_card("options_derivatives")
    card["method_card_id"] = "method_card_options_straddle_inline"
    card["method_id"] = "long_straddle"
    card["title"] = "Long Straddle"
    card["extension_fields"] = {
        "options_derivatives": {
            "instrument_type": {"value": "options", "evidence_refs": [_fake_ref()]},
            "legs": {"value": ["long call", "long put"], "evidence_refs": [_fake_ref()]},
            "strike_selection": {"value": "same strike", "evidence_refs": [_fake_ref()]},
        }
    }
    return card


def _base_rich_card(family: str) -> dict[str, Any]:
    return {
        "artifact_type": "method_card",
        "card_format": "rich_method_card",
        "method_card_id": "method_card_inline_rich",
        "method_card_set_id": "method_card_set_inline_rich_test",
        "revision_number": 1,
        "method_id": "pairs_mean_reversion",
        "title": "Inline Rich Card",
        "family": family,
        "status": "approved",
        "assumptions": ["source-backed method assumption"],
        "inputs": ["source-backed input"],
        "outputs": ["source-backed output"],
        "failure_modes": ["source-backed failure mode"],
        "evidence_refs": [_fake_ref()],
        "core_fields": {},
        "extension_fields": {},
    }


def _fake_ref() -> dict[str, Any]:
    return {
        "source_id": "knowledge_source_fake",
        "chunk_id": "knowledge_chunk_fake",
        "locator": {"page": 1, "heading": "Fixture"},
        "claim": "fixture evidence",
    }


def _write_text_pdf(path: Path, lines: Sequence[str]) -> None:
    content_lines = ["BT", "/F1 10 Tf", "50 760 Td"]
    for index, line in enumerate(lines):
        if index:
            content_lines.append("0 -14 Td")
        content_lines.append(f"({_pdf_escape(line)}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload += f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref = len(payload)
    payload += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    for offset in offsets:
        payload += f"{offset:010d} 00000 n \n".encode("ascii")
    payload += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode(
        "ascii"
    )
    path.write_bytes(bytes(payload))


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
