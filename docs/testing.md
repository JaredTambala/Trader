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

Prefer in-memory fakes for unit tests and Postgres for integration coverage. Runtime code is Postgres
only, so add Postgres-backed validation when needed (via a local Docker instance).
