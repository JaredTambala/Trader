# Testing (Stage 0)

## Standards

- Use `uv` to manage dependencies and run test commands.
- Use `pytest` for unit and integration tests.
- Unit tests must be fast and deterministic.
- Integration tests should isolate external services (mock Alpaca, DuckDB).

## Expectations

- All new features include tests.
- Tests must document edge cases and failure modes.
- CI runs `uv run pytest` on every change.
