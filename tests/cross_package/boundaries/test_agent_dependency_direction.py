"""Architecture contracts for Agent and MCP dependency direction.

Subject: Agent contracts, specialist loops, checkpoints, and MCP-facing control boundaries.
Level: Cross-package architecture contract.
Collaborators: Real Agent and MCP source paths plus AST import inspection; no model or MCP process.
Guarantees: Agent decisions stay above transport and domain services while MCP never depends outward on Agents.
Non-goals: Model quality, tool behavior, checkpoint recovery, and orchestration outcomes.
"""

from pathlib import Path

from tests.cross_package.boundaries.import_scanning import (
    imported_modules as _imported_modules,
)


def test_model_backed_specialists_do_not_import_transport_or_domain_services() -> None:
    """Keep specialist decisions above transport and deterministic domain services."""
    forbidden = ('trader', 'trader_mcp', 'trader_research.data', 'trader_research.experiments', 'trader_research.infrastructure', 'trader_research.knowledge', 'trader_research.methodology', 'trader_research.ml', 'trader_research.review')
    offenders: list[str] = []
    for path in Path('src/trader_agents/specialists').glob('*.py'):
        for imported in sorted(_imported_modules(path)):
            if imported in forbidden or imported.startswith(tuple((f'{prefix}.' for prefix in forbidden))):
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_data_specialist_uses_public_governance_store_and_mcp_boundaries() -> None:
    """Constrain the Data specialist to public governance and MCP boundaries."""
    forbidden = ('trader', 'trader_mcp.protocol.contracts', 'trader_mcp.runtime.server', 'trader_research.data', 'trader_research.infrastructure')
    offenders: list[str] = []
    for path in (Path('src/trader_agents/specialists/data_research.py'),):
        for imported in sorted(_imported_modules(path)):
            if imported in forbidden or imported.startswith(tuple((f'{prefix}.' for prefix in forbidden))):
                offenders.append(f'{path}: imports {imported}')
            if imported.startswith('trader_mcp.') and imported != 'trader_mcp.catalogue.definitions':
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_agent_mcp_layer_uses_only_public_mcp_contracts() -> None:
    """Keep Agent-side tool control above MCP transport and composition internals."""
    allowed_mcp_imports = {'trader_mcp.catalogue.definitions', 'trader_mcp.protocol.contracts'}
    offenders: list[str] = []
    for path in Path('src/trader_agents/mcp').glob('*.py'):
        for imported in sorted(_imported_modules(path)):
            if imported == 'trader_mcp' or imported.startswith('trader_mcp.'):
                if imported not in allowed_mcp_imports:
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_agent_domain_contracts_do_not_depend_on_runtime_or_transport() -> None:
    """Keep stable Agent domain values independent of execution mechanisms."""
    forbidden = ('langgraph', 'mcp', 'trader_agents.', 'trader_mcp')
    path = Path('src/trader_agents/contracts/domain.py')
    offenders = [f'{path}: imports {imported}' for imported in sorted(_imported_modules(path)) if imported.startswith(forbidden)]
    assert offenders == []


def test_trader_mcp_does_not_import_agent_package() -> None:
    """Keep MCP a transport adapter beneath every model-backed agent loop.

    An MCP import of ``trader_agents`` reverses the declared dependency direction
    and lets transport code construct model clients, prompts, or orchestration.
    Agent processes may call MCP tools; MCP implementations must not call back
    into the agent package.
    """
    offenders: list[str] = []
    for path in Path('src/trader_mcp').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported == 'trader_agents' or imported.startswith('trader_agents.'):
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_trader_agents_do_not_import_data_platform_or_mcp_server_boundaries() -> None:
    """Keep Agents above data persistence and MCP server implementation boundaries."""
    forbidden = {'trader.event_store', 'trader.market_data.queries', 'trader_research.data', 'trader_mcp.runtime.server'}
    offenders: list[str] = []
    for path in Path('src/trader_agents').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported in forbidden:
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_agent_decision_graphs_use_the_agent_mcp_boundary() -> None:
    """Prevent coordinator and specialists from importing MCP implementations directly."""
    roots = (Path('src/trader_agents/coordination'), Path('src/trader_agents/specialists'))
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob('*.py'):
            for imported in _imported_modules(path):
                if imported == 'trader_mcp' or imported.startswith('trader_mcp.'):
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_workflow_checkpointing_depends_only_on_governance_contracts() -> None:
    """Limit Agent checkpoints to stable governance contracts and foundation values."""
    allowed_research_imports = {'trader_research.foundation', 'trader_research.governance', 'trader_research.governance.handoffs'}
    offenders: list[str] = []
    for path in Path('src/trader_agents/checkpointing').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported in {'trader', 'trader_mcp'} or imported.startswith(('trader.', 'trader_mcp.')):
                offenders.append(f'{path}: imports {imported}')
            if imported.startswith('trader_research.') and imported not in allowed_research_imports:
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []
