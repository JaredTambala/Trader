"""Contracts for neutral maintained implementation discovery."""

from __future__ import annotations

import importlib

from trader_research.experiments import (
    list_risk_manager_templates,
    list_strategy_templates,
)


def test_strategy_catalog_exposes_runtime_metadata_without_candidate_coupling() -> None:
    envelope = list_strategy_templates(families=["pairs-mean-reversion"])

    assert envelope.ok is True
    assert envelope.operation == "research_list_strategy_templates"
    assert envelope.data["template_count"] == 1
    template = envelope.data["templates"][0]
    assert template["template_id"] == "pairs_mean_reversion"
    assert template["implementation_kind"] == "strategy"
    assert template["maintained_entrypoint"].startswith("trader_standard.strategies:")
    assert template["portfolio_mode"] == "pairs"
    assert not {
        "required_artifact_types",
        "required_artifact_roles",
        "source_generator",
        "validation_requirements",
    }.intersection(template)


def test_risk_catalog_contains_only_real_maintained_entrypoints() -> None:
    envelope = list_risk_manager_templates()

    assert envelope.ok is True
    templates = envelope.data["templates"]
    assert envelope.data["template_count"] == 5
    assert all(item["implementation_kind"] == "risk_manager" for item in templates)
    assert all(
        item["maintained_entrypoint"].startswith("trader_standard.risk:")
        for item in templates
    )
    assert all("source_generator" not in item for item in templates)


def test_catalog_entrypoints_resolve_to_maintained_runtime_objects() -> None:
    templates = [
        *list_strategy_templates().data["templates"],
        *list_risk_manager_templates().data["templates"],
    ]

    for template in templates:
        module_name, object_name = template["maintained_entrypoint"].split(":", 1)
        assert hasattr(importlib.import_module(module_name), object_name)


def test_catalog_rejects_unknown_and_empty_filters() -> None:
    unknown = list_strategy_templates(families=["unknown"])
    empty = list_risk_manager_templates(families=[])

    assert unknown.ok is False
    assert unknown.errors[0]["code"] == "unsupported_strategy_template"
    assert empty.ok is False
    assert empty.errors[0]["code"] == "unsupported_risk_manager_template"
