"""Read-only maintained risk-manager template catalog."""

from .services import (
    RESEARCH_LIST_RISK_MANAGER_TEMPLATES,
    SUPPORTED_RISK_MANAGER_FAMILIES,
    RiskManagerTemplate,
    RiskManagerTemplateParameter,
    get_risk_manager_template,
    list_risk_manager_templates,
    normalize_risk_manager_family,
)

__all__ = [
    "RESEARCH_LIST_RISK_MANAGER_TEMPLATES",
    "SUPPORTED_RISK_MANAGER_FAMILIES",
    "RiskManagerTemplate",
    "RiskManagerTemplateParameter",
    "get_risk_manager_template",
    "list_risk_manager_templates",
    "normalize_risk_manager_family",
]
