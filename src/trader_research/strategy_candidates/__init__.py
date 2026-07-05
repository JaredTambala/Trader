"""Strategy candidate catalog, source-generation, and validation services."""

from .services import (
    METHOD_PACKAGE_MANIFEST,
    RESEARCH_CREATE_STRATEGY_CANDIDATE,
    RESEARCH_LIST_STRATEGY_TEMPLATES,
    STRATEGY_RUNTIME_CONTRACT,
    SUPPORTED_STRATEGY_FAMILIES,
    StrategyTemplate,
    StrategyTemplateParameter,
    create_strategy_candidate,
    get_strategy_template,
    list_strategy_templates,
    normalize_strategy_family,
    strategy_candidate_path,
    strategy_candidate_source_path,
)
from .validation import (
    RESEARCH_VALIDATE_STRATEGY_CANDIDATE,
    strategy_candidate_validation_report_path,
    validate_strategy_candidate,
)

__all__ = [
    "METHOD_PACKAGE_MANIFEST",
    "RESEARCH_CREATE_STRATEGY_CANDIDATE",
    "RESEARCH_LIST_STRATEGY_TEMPLATES",
    "RESEARCH_VALIDATE_STRATEGY_CANDIDATE",
    "STRATEGY_RUNTIME_CONTRACT",
    "SUPPORTED_STRATEGY_FAMILIES",
    "StrategyTemplate",
    "StrategyTemplateParameter",
    "create_strategy_candidate",
    "get_strategy_template",
    "list_strategy_templates",
    "normalize_strategy_family",
    "strategy_candidate_path",
    "strategy_candidate_source_path",
    "strategy_candidate_validation_report_path",
    "validate_strategy_candidate",
]
