# Testing (Stage 0)

## Standards

- Use `uv` to manage dependencies and run test commands.
- Use `pytest` for unit and integration tests.
- Unit tests must be fast and deterministic.
- Integration tests should isolate external services (mock Alpaca, Postgres).

## Expectations

- All new features include tests.
- Tests must document edge cases and failure modes.
- CI runs `uv run pytest` on every change.

## Running Tests

```bash
uv run pytest
```

Tests use DuckDB utilities under `tests/support` for speed and isolation. Runtime code is Postgres
only, so add Postgres integration coverage when needed (via a local Docker instance).
