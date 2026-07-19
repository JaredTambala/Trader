from __future__ import annotations

from pathlib import Path


BOUNDARY_ROOTS = (
    Path("src/trader_research"),
    Path("src/trader_mcp"),
)
APPROVED_SQL_ROOT = Path("src/trader_research/infrastructure/postgres")
FORBIDDEN_SNIPPETS = (
    "import psycopg",
    "from psycopg",
    "stock_bar_events",
    "crypto_bar_events",
)


def test_research_and_mcp_layers_do_not_embed_sql_access() -> None:
    offenders: list[str] = []
    for root in BOUNDARY_ROOTS:
        for path in root.rglob("*.py"):
            if path.is_relative_to(APPROVED_SQL_ROOT):
                continue
            text = path.read_text(encoding="utf-8")
            for snippet in FORBIDDEN_SNIPPETS:
                if snippet in text:
                    offenders.append(f"{path}: contains {snippet!r}")

    assert offenders == []
