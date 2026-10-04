"""Alignment of independent API requirements with producer migration information.

Subject: Console producer/consumer schema declarations.
Level: Cross-package boundary contract.
Collaborators: Real static declarations and pure API compatibility assessment.
Guarantees: The impact map matches API requirements without a runtime dependency.
Non-goals: Executing SQL migrations or verifying Superset saved assets.
"""

from trader.event_store.console_contract_status import CONSUMERS
from trader.event_store.console_read_contract import CONSOLE_READ_COLUMNS, CONSOLE_READ_CONTRACT_COLUMNS
from trader_console_api.repositories.schema_compatibility import (
    EXPECTED_CONTRACT_COLUMNS, SUPPORTED_CONTRACT_VERSION, assess_schema_compatibility,
)


def test_api_catalog_matches_its_declared_migration_requirement():
    """CI rejects a consumer version or relation change omitted from the impact map."""
    consumer = next(item for item in CONSUMERS if item.name == "console-api")
    assert consumer.required_version == SUPPORTED_CONTRACT_VERSION
    assert EXPECTED_CONTRACT_COLUMNS == {
        "contract_versions": CONSOLE_READ_CONTRACT_COLUMNS,
        **{name: CONSOLE_READ_COLUMNS[name] for name in consumer.relations},
    }


def test_producer_impact_map_does_not_register_superset_as_a_core_consumer():
    """External database clients own their relation manifests outside Trader core."""
    assert all("superset" not in item.name.lower() for item in CONSUMERS)


def test_api_startup_requirements_include_the_resources_it_serves():
    """The API contract map admits the complete catalog required by its resource routes."""
    for version, columns in ((1, EXPECTED_CONTRACT_COLUMNS),
                             (2, {**EXPECTED_CONTRACT_COLUMNS, **CONSOLE_READ_COLUMNS})):
        inspection = assess_schema_compatibility(
            version_row=(version, 1),
            catalog_rows=[(name, column) for name, relation in columns.items() for column in relation],
        )
        assert inspection.ready
