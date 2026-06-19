# Python Code Quality Guide

This guide is the contributor standard for Python across `src/trader`, `src/trader_standard`,
`src/trader_research`, scripts, examples, and tests. It is intentionally practical: code should be easy to read,
easy to test, and useful to operate when something goes wrong.

This is review guidance, not a new automated gate. The existing baseline remains Python 3.12, `uv`, `ruff`, partial
`mypy`, `pytest`, and Google-style docstrings.

## Principles

- Prefer code that exposes its shape quickly: small functions, explicit names, early validation, and narrow
  responsibilities.
- Put domain decisions at boundaries. Normalize config, request payloads, database rows, and external API responses
  before passing them deeper into the system.
- Keep core logic deterministic when possible. Time, network, broker clients, databases, and files should be passed in
  or wrapped behind narrow interfaces.
- Make failures actionable. Raise clear exceptions at validation boundaries, preserve context, and avoid broad silent
  catches.
- Log operational facts, not implementation noise. Include stable identifiers such as `run_id`, `cycle_id`,
  `client_order_id`, symbol, timeframe, source, and count when they help correlate events.
- Keep comments and docstrings factual. Explain contracts, invariants, intent, and non-obvious tradeoffs; do not
  narrate code that is already obvious.

## Comments And Docstrings

Use comments for the part a reader cannot infer locally. A useful comment usually answers one of these questions:

- Why is this branch necessary?
- What invariant must remain true?
- What external behavior, schema, or provider quirk is being protected?
- What is deliberately not handled here?

Avoid comments that translate syntax into English.

Bad:

```python
# Loop through symbols.
for symbol in symbols:
    fetch_bars(symbol)
```

Better:

```python
# Preserve config order so warning output matches the operator's requested universe.
for symbol in symbols:
    fetch_bars(symbol)
```

Use Google-style docstrings for new and updated production Python modules, public classes, and public functions. A
public docstring should explain the behavior a caller relies on: accepted inputs, normalization, side effects,
persistence or network writes, ordering/idempotency guarantees, and important failure modes. A one-line label such as
`"""Build broker."""` or `"""Initialize the instance."""` is usually worse than no docstring because it suggests the
contract has been documented when it has not.

For dataclasses and public classes, include `Attributes:` when fields are part of the public contract. For functions
and methods, include `Args:`, `Returns:`, and `Raises:` only when they clarify real contracts or failure modes.

```python
@dataclass(frozen=True)
class BarQuery:
    """Validated request shape for bounded bar-data reads.

    Attributes:
        symbols: Canonical symbols to query, in requested order.
        start: Inclusive UTC window start.
        end: Inclusive UTC window end.
    """

    symbols: tuple[str, ...]
    start: datetime
    end: datetime
```

Short private helpers can have no docstring when their name and body are clearer than a sentence. If a helper protects
a non-obvious invariant, document that invariant instead of documenting every parameter.

## Mental Parseability

Readable Python is structured so a reviewer can hold one level of behavior in their head at a time.

- Keep orchestration functions focused on ordering steps; move validation, translation, and persistence details into
  named helpers.
- Prefer explicit intermediate names for domain concepts over clever expressions.
- Validate early, then let the rest of the function operate on normalized values.
- Return typed value objects or plain data with stable keys; avoid passing partially-normalized dictionaries through
  multiple layers.
- Use `Any` only at untrusted boundaries or where a third-party API forces it. Convert to typed shapes as soon as
  practical.

Before:

```python
def run(config_data: Mapping[str, Any]) -> None:
    symbols = [str(item).upper() for item in config_data.get("symbols", []) if item]
    if not symbols:
        raise ValueError("symbols required")
    for symbol in symbols:
        rows = client.get(symbol, config_data.get("timeframe", "1Min"))
        store.write([normalize(row, symbol) for row in rows])
```

After:

```python
def run(config_data: Mapping[str, Any], *, client: BarClient, store: BarStore) -> None:
    request = _bar_request_from_config(config_data)
    bars = _fetch_normalized_bars(client, request)
    store.write(bars)
```

The second version makes the orchestration visible and gives tests stable seams without hiding the domain behavior.

## Testability

Design production code so tests can prove behavior without real brokers, network calls, wall-clock time, or external
state unless the test is explicitly an integration test.

- Keep pure calculations separate from adapters and persistence.
- Inject clients, clocks, event stores, and paths instead of constructing them deep in business logic.
- Use fakes for local contract tests; reserve mocks for verifying collaboration that has no better observable output.
- Keep unit tests deterministic and fast. Use Postgres-marked tests for behavior DuckDB or fakes cannot prove.
- Test contracts and edge cases: empty symbol lists, invalid timeframes, missing config, stale market data, duplicate
  events, idempotent writes, and provider failures.

Less testable:

```python
def load_latest_price(symbol: str) -> float:
    client = AlpacaClient.from_env()
    return float(client.latest_trade(symbol).price)
```

More testable:

```python
class PriceClient(Protocol):
    def latest_price(self, symbol: str) -> float:
        """Return the latest known price for one canonical symbol."""


def load_latest_price(symbol: str, *, client: PriceClient) -> float:
    return client.latest_price(symbol.upper())
```

The production entrypoint can still build the real client. Core behavior should accept the dependency it needs.

## Observability

Logs and persisted events should explain what happened, which run it happened in, and what an operator can do next.

- Use module loggers: `logger = logging.getLogger(__name__)`.
- Include correlation fields for runtime paths: `run_id`, `cycle_id`, `experiment_id`, `symbol`, `timeframe`, source,
  count, and relevant order IDs.
- Prefer concise event-style messages over prose paragraphs.
- Use `warning` for degraded behavior that continues, `error` for known failures that stop a path, and `exception`
  when stack context is needed.
- Never log secrets, raw credentials, tokens, or full unredacted config payloads.
- Keep event-store writes and logs consistent. If a cycle is marked failed, halted, skipped, or complete, the logs
  should contain the same identifiers and reason.

Good:

```python
logger.info(
    "Market data fetched symbol=%s timeframe=%s count=%s run_id=%s cycle_id=%s",
    symbol,
    timeframe,
    len(events),
    run_id,
    cycle_id,
)
```

Avoid:

```python
logger.info("Done")
logger.exception("Failed: %s", exc)
```

The first message cannot be correlated. The second duplicates exception text while dropping the operational context.

## Python Idioms

Use idioms that reduce ambiguity without making the code ceremonial.

- Use `@dataclass(frozen=True)` for immutable value objects and request/result shapes.
- Use `Protocol` for behavior supplied by callers, especially clients, stores, clocks, and strategy/risk interfaces.
- Accept `Mapping` and `Sequence` at boundaries; use `dict`, `list`, and `tuple` internally when mutation or ordering
  matters.
- Prefer `pathlib.Path` for filesystem paths.
- Prefer timezone-aware `datetime` values; normalize to UTC at boundaries.
- Prefer explicit `ValueError`, domain exceptions, or typed validation errors over generic `Exception`.
- Use comprehensions for simple transformations; use named loops when there is branching, validation, logging, or
  accumulated state.

Boundary shape:

```python
def normalize_symbols(value: Sequence[object]) -> tuple[str, ...]:
    symbols = tuple(str(item).upper() for item in value if str(item).strip())
    if not symbols:
        raise ValueError("At least one symbol is required")
    return symbols
```

## Package Discipline

Directory structure is part of readability. A flat package is fine while files share one clear responsibility, but it
becomes hard to parse when many modules at the same level serve different audiences or lifecycle stages.

- Create subpackages when a directory has several distinct goals, such as adapters, domain models, query helpers,
  runtime orchestration, CLI entrypoints, or test support.
- Keep package boundaries aligned with ownership and dependency direction. Domain code should not depend on CLI,
  provider, or persistence details unless that package explicitly owns integration.
- Prefer names that describe responsibility, not implementation history: `market_data/queries.py` is better than
  `market_data/new_helpers.py`.
- Keep `__init__.py` files small. Re-export stable public contracts only when it improves caller ergonomics.
- Avoid "misc", "common", and "utils" packages for unrelated behavior. If a helper needs a vague package name, it
  probably belongs closer to the feature that uses it.
- When a single module grows large because it contains multiple responsibilities, split by behavior before splitting
  by arbitrary class or function count.

Before:

```text
src/trader/
  broker.py
  broker_queries.py
  broker_recovery.py
  broker_sync.py
  market_data.py
  market_data_backfill.py
  market_data_queries.py
  market_data_replay.py
```

Better when responsibilities keep expanding:

```text
src/trader/
  broker/
    adapters.py
    recovery.py
    sync.py
  market_data/
    domain.py
    backfill.py
    queries.py
    replay.py
```

Do not reorganize packages casually. Move files when the new boundary makes future code easier to place, lowers import
confusion, and can be covered by tests or import checks.

## Error Handling

Errors should either be handled locally with a clear fallback or propagated with enough context for the caller.

- Validate public inputs before doing side effects.
- Catch specific exceptions when the code has a specific recovery path.
- When catching broad exceptions at an entrypoint, log context and return or raise a clear failure status.
- Do not swallow exceptions to keep a loop moving unless the skipped item is logged with identifiers and reason.
- Do not convert typed exceptions into strings too early; preserve structured fields where possible.

Weak:

```python
try:
    broker.submit(order)
except Exception:
    pass
```

Better:

```python
try:
    broker.submit(order)
except BrokerUnavailableError as exc:
    logger.warning(
        "Order submit skipped reason=broker_unavailable symbol=%s client_order_id=%s run_id=%s",
        order.symbol,
        order.client_order_id,
        run_id,
    )
    raise OrderSubmissionError(order.client_order_id) from exc
```

## PR Review Checklist

- Comments explain intent, invariants, contracts, or tradeoffs instead of restating syntax.
- Public modules, classes, and functions have contract-focused Google-style docstrings when they clarify usage.
- Orchestration, validation, translation, and persistence are separated enough to read and test independently.
- Core logic can be tested with deterministic inputs and injected fakes.
- Unit tests cover the main contract and at least one meaningful edge or failure case.
- Integration tests are used only where external stores, schemas, or provider boundaries need proof.
- Logs include useful correlation identifiers and avoid secrets or noisy implementation details.
- Exceptions are specific, contextual, and not silently swallowed.
- Boundary data is normalized into typed shapes before deeper use.
- Package directories group related responsibilities; large flat directories are split when modules have different
  goals or dependency directions.
- Changes pass the existing local baseline when code changes are included:

```bash
uv run ruff check src tests examples run_*.py external_strategy_demo.py
uv run mypy
uv run pytest
```
