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
        "Quantitative Methods Agent",
        "ML Agent",
        "Hypothesis Agent",
        "Evaluation Agent",
        "Adversarial Agent",
    }


def test_agent_lookup_accepts_key_or_display_name() -> None:
    assert get_agent_definition("data_agent").display_name == "Data Agent"
    assert get_agent_definition("Data Agent").key == "data_agent"
    assert get_agent_definition("Math Coder Agent").display_name == "Quantitative Methods Agent"
    assert get_agent_definition("quant_methods_agent").display_name == "Quantitative Methods Agent"


def test_quantitative_methods_tool_owner_and_identity_use_method_contract_tools() -> None:
    identity = build_agent_identity("Quantitative Methods Agent")

    assert identity.agent_key == "quant_methods_agent"
    assert identity.display_name == "Quantitative Methods Agent"
    assert "knowledge_search_methods" in identity.tool_allowlist
    assert "knowledge_get_evidence_chunks" in identity.tool_allowlist
    assert "knowledge_discover_methodology_candidates" in identity.tool_allowlist
    assert "knowledge_extract_methodology_fields" in identity.tool_allowlist
    assert "knowledge_validate_methodology_candidate" in identity.tool_allowlist
    assert "knowledge_create_rich_method_card_draft" in identity.tool_allowlist
    assert "knowledge_update_method_card_status" in identity.tool_allowlist
    assert "knowledge_validate_citations" in identity.tool_allowlist
    assert "math_list_method_contracts" in identity.tool_allowlist
    assert "math_validate_method_contract" in identity.tool_allowlist
    assert "math_run_signal_diagnostics" in identity.tool_allowlist
    assert "math_run_multiple_testing_report" in identity.tool_allowlist
    assert "math_generate_cpp_kernel" in identity.tool_allowlist
    assert "math_compile_kernel" in identity.tool_allowlist
    assert "math_package_method_artifact" in identity.tool_allowlist
    assert agent_owner_for_tool("knowledge_retrieve_evidence") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("knowledge_get_evidence_chunks") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("knowledge_discover_methodology_candidates") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("knowledge_extract_methodology_fields") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("knowledge_validate_methodology_candidate") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("knowledge_create_rich_method_card_draft") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("knowledge_update_method_card_status") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("math_list_method_contracts") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("math_run_signal_diagnostics") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("math_run_multiple_testing_report") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("math_generate_cpp_kernel") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("math_compile_kernel") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("math_package_method_artifact") == "Quantitative Methods Agent"
    assert agent_owner_for_tool("math_list_indicator_contracts") == "Quantitative Methods Agent"


def test_quant_research_supervisor_owns_strategy_candidate_creation() -> None:
    identity = build_agent_identity("Quant Research Supervisor Agent")

    assert "research_list_strategy_templates" in identity.tool_allowlist
    assert "research_create_strategy_candidate" in identity.tool_allowlist
    assert "research_validate_strategy_candidate" in identity.tool_allowlist
    assert "research_run_backtest" in identity.tool_allowlist
    assert "research_get_backtest_results" in identity.tool_allowlist
    assert "research_compare_backtest_results" in identity.tool_allowlist
    assert "research_list_risk_manager_templates" in identity.tool_allowlist
    assert "research_create_risk_manager_candidate" in identity.tool_allowlist
    assert "research_validate_risk_manager_candidate" in identity.tool_allowlist
    assert "research_create_strategy_risk_stack" in identity.tool_allowlist
    assert "research_validate_strategy_risk_stack" in identity.tool_allowlist
    assert "strategy_implementation.py" in identity.output_artifacts
    assert "strategy_candidate_manifest.json" in identity.output_artifacts
    assert "strategy_candidate_validation_report.json" in identity.output_artifacts
    assert "risk_manager_implementation.py" in identity.output_artifacts
    assert "risk_manager_candidate_manifest.json" in identity.output_artifacts
    assert "risk_manager_candidate_validation_report.json" in identity.output_artifacts
    assert "strategy_risk_stack_manifest.json" in identity.output_artifacts
    assert "strategy_risk_stack_validation_report.json" in identity.output_artifacts
    assert "portfolio_backtest_run_ref.json" in identity.output_artifacts
    assert "backtest_run_ref.json" in identity.output_artifacts
    assert agent_owner_for_tool("research_create_strategy_candidate") == "Quant Research Supervisor Agent"
    assert agent_owner_for_tool("research_validate_strategy_candidate") == "Quant Research Supervisor Agent"
    assert agent_owner_for_tool("research_run_backtest") == "Quant Research Supervisor Agent"
    assert agent_owner_for_tool("research_get_backtest_results") == "Quant Research Supervisor Agent"
    assert agent_owner_for_tool("research_compare_backtest_results") == "Quant Research Supervisor Agent"
    assert agent_owner_for_tool("research_list_risk_manager_templates") == "Quant Research Supervisor Agent"
    assert agent_owner_for_tool("research_create_risk_manager_candidate") == "Quant Research Supervisor Agent"
    assert agent_owner_for_tool("research_validate_risk_manager_candidate") == "Quant Research Supervisor Agent"
    assert agent_owner_for_tool("research_create_strategy_risk_stack") == "Quant Research Supervisor Agent"
    assert agent_owner_for_tool("research_validate_strategy_risk_stack") == "Quant Research Supervisor Agent"


def test_evaluation_agent_owns_performance_report_tool() -> None:
    identity = build_agent_identity("Evaluation Agent")

    assert "evaluation_generate_performance_report" in identity.tool_allowlist
    assert "evaluation_generate_report" in identity.tool_allowlist
    assert "evaluation_report.json" in identity.output_artifacts
    assert agent_owner_for_tool("evaluation_generate_performance_report") == "Evaluation Agent"
    assert agent_owner_for_tool("evaluation_generate_report") == "Evaluation Agent"
