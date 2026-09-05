"""Architecture contract for research SQL access isolation.

Subject: The persistence boundary shared by deterministic research and MCP adapters.
Level: Cross-package architecture contract.
Collaborators: Real research and MCP source trees inspected as text; no database connection.
Guarantees: SQL and psycopg access remain confined to approved research infrastructure.
Non-goals: SQL statement correctness, Postgres availability, and persistence behavior.
"""

from pathlib import Path


BOUNDARY_ROOTS = (Path('src/trader_research'), Path('src/trader_mcp'))


APPROVED_SQL_ROOT = Path('src/trader_research/infrastructure/postgres')


FORBIDDEN_SNIPPETS = ('import psycopg', 'from psycopg', 'stock_bar_events', 'crypto_bar_events')


def test_research_and_mcp_layers_do_not_embed_sql_access() -> None:
    """Confine SQL and driver access to the approved research persistence boundary."""
    offenders: list[str] = []
    for root in BOUNDARY_ROOTS:
        for path in root.rglob('*.py'):
            if path.is_relative_to(APPROVED_SQL_ROOT):
                continue
            text = path.read_text(encoding='utf-8')
            for snippet in FORBIDDEN_SNIPPETS:
                if snippet in text:
                    offenders.append(f'{path}: contains {snippet!r}')
    assert offenders == []
