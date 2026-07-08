"""Risk-manager template catalog and candidate source-generation services."""

from .services import (
    RESEARCH_CREATE_RISK_MANAGER_CANDIDATE,
    RESEARCH_LIST_RISK_MANAGER_TEMPLATES,
    RISK_MANAGER_RUNTIME_CONTRACT,
    SUPPORTED_RISK_MANAGER_FAMILIES,
    RiskManagerTemplate,
    RiskManagerTemplateParameter,
    create_risk_manager_candidate,
    get_risk_manager_template,
    list_risk_manager_templates,
    normalize_risk_manager_family,
    risk_manager_candidate_path,
    risk_manager_candidate_source_path,
)
from .validation import (
    RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE,
    risk_manager_candidate_validation_report_path,
    validate_risk_manager_candidate,
)

__all__ = [
    "RESEARCH_CREATE_RISK_MANAGER_CANDIDATE",
    "RESEARCH_LIST_RISK_MANAGER_TEMPLATES",
    "RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE",
    "RISK_MANAGER_RUNTIME_CONTRACT",
    "SUPPORTED_RISK_MANAGER_FAMILIES",
    "RiskManagerTemplate",
    "RiskManagerTemplateParameter",
    "create_risk_manager_candidate",
    "get_risk_manager_template",
    "list_risk_manager_templates",
    "normalize_risk_manager_family",
    "risk_manager_candidate_path",
    "risk_manager_candidate_source_path",
    "risk_manager_candidate_validation_report_path",
    "validate_risk_manager_candidate",
]
