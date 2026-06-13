from __future__ import annotations

import trader_agents
import trader_mcp
import trader_research
from trader_agents import build_agent_identity
from trader_research.agents import AGENT_DEFINITIONS, agent_owner_for_tool, get_agent_definition


def test_new_research_packages_import_cleanly() -> None:
    assert trader_research is not None
    assert trader_mcp is not None
    assert trader_agents is not None


def test_data_inventory_tool_is_owned_by_data_agent() -> None:
    assert agent_owner_for_tool("data_discover_symbols") == "Data Agent"
    assert agent_owner_for_tool("data_get_inventory") == "Data Agent"
    assert agent_owner_for_tool("data_summarize_quality") == "Data Agent"
    assert agent_owner_for_tool("data_ensure_loaded") == "Data Agent"


def test_data_agent_identity_has_only_initial_data_allowlist() -> None:
    identity = build_agent_identity("Data Agent")

    assert identity.agent_key == "data_agent"
    assert identity.display_name == "Data Agent"
    assert set(identity.tool_allowlist) == {
        "mcp_health",
        "mcp_get_config",
        "data_discover_symbols",
        "data_get_inventory",
        "data_summarize_quality",
        "data_ensure_loaded",
    }
    assert "symbol_discovery_report.json" in identity.output_artifacts
    assert "dataset_manifest.json" in identity.output_artifacts
    assert "data_quality_report.json" in identity.output_artifacts


def test_data_agent_identity_excludes_supervisor_and_broker_mutating_tools() -> None:
    identity = build_agent_identity("data_agent")

    forbidden_tools = {
        "research_run_backtest",
        "research_generate_recommendation",
        "place_order",
        "cancel_order",
        "start_trading",
        "clear_halt",
    }

    assert forbidden_tools.isdisjoint(identity.tool_allowlist)


def test_agent_registry_keys_and_display_names_are_unique() -> None:
    keys = [agent.key for agent in AGENT_DEFINITIONS]
    display_names = [agent.display_name for agent in AGENT_DEFINITIONS]

    assert len(keys) == len(set(keys)) == 7
    assert len(display_names) == len(set(display_names)) == 7
    assert set(display_names) == {
        "Quant Research Supervisor Agent",
        "Data Agent",
        "Math Coder Agent",
        "ML Agent",
        "Hypothesis Agent",
        "Evaluation Agent",
        "Adversarial Agent",
    }


def test_agent_lookup_accepts_key_or_display_name() -> None:
    assert get_agent_definition("data_agent").display_name == "Data Agent"
    assert get_agent_definition("Data Agent").key == "data_agent"
