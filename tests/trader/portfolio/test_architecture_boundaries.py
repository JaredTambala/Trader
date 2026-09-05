"""Architecture tests for core portfolio boundaries.

Subject: Portfolio public exports, pure calculations, and explicit snapshot persistence.
Level: Core package architecture contract.
Collaborators: Real source files and public portfolio types; no database or broker.
Guarantees: Portfolio values remain stable and side effects stay behind explicit persistence.
Non-goals: Portfolio accounting outcomes, Postgres adapters, and runtime cycle behavior.
"""

from pathlib import Path

import trader
from trader.portfolio import Portfolio, PortfolioSnapshot, Position


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_trader_root_portfolio_exports_remain_stable() -> None:
    """Keep root portfolio exports stable after internal module splits."""
    assert trader.Portfolio is Portfolio
    assert trader.PortfolioSnapshot is PortfolioSnapshot
    assert trader.Position is Position


def test_runtime_code_uses_explicit_portfolio_snapshot_persistence() -> None:
    """Keep portfolio snapshot writes at an explicit persistence boundary."""
    allowed = {PROJECT_ROOT / 'src/trader/portfolio/snapshots.py'}
    offenders: list[str] = []
    for path in (PROJECT_ROOT / 'src/trader').rglob('*.py'):
        if path in allowed:
            continue
        text = path.read_text(encoding='utf-8')
        if 'snapshot.persist(event_store)' in text or 'snapshot.persist(runtime.event_store)' in text:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))
    assert offenders == []


def test_portfolio_pure_modules_do_not_use_runtime_side_effects() -> None:
    """Keep portfolio calculations free of clocks, logging, and I/O."""
    pure_modules = [PROJECT_ROOT / 'src/trader/portfolio/models.py', PROJECT_ROOT / 'src/trader/portfolio/order_inputs.py', PROJECT_ROOT / 'src/trader/portfolio/order_math.py', PROJECT_ROOT / 'src/trader/portfolio/reconstruction.py', PROJECT_ROOT / 'src/trader/portfolio/transitions.py']
    forbidden_snippets = ('import logging', 'datetime.now', 'os.environ', 'record_event(', '.cursor(', 'connection(', '.open(')
    offenders: list[str] = []
    for path in pure_modules:
        text = path.read_text(encoding='utf-8')
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f'{path.relative_to(PROJECT_ROOT)} contains {snippet!r}')
    assert offenders == []
