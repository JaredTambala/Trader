# Local Console demo

This fixture supplies the first Console journey: configured synthetic context and real API/database-schema status.
It contains **no trading rows**. Fixture identity is `console-demo`; its schema comes from the checked-out producer
code and its API contract from `contracts/trader-console/openapi.json`. Record the Git revision when demonstrating it.
No broker, LLM, research service or trading runtime is started.

## Start

Requirements: Docker Compose, Python 3.12 with `uv`, and the frontend's pinned Node/npm toolchain. Run these commands
from the repository root. The Compose project, database and volume are separate from `docker-compose.postgres.yml`.

<!-- verified: integration:console tests/cross_package/workflows/test_console_demo_postgres.py -->
```bash
docker compose -f examples/console_demo/compose.yml up -d --wait
uv run python -m examples.console_demo bootstrap
uv run python -m examples.console_demo api
```

The last command runs the API in the foreground on `127.0.0.1:8001`. In another terminal, start the
[frontend](../../apps/trader-console/README.md#start-the-screen) and open `http://127.0.0.1:3000`.
Bootstrap is repeatable: it installs the core schema, research artifact projection, Console read contract, and explicit
Console command tables without inserting/truncating trading data. It still does not start a worker or mutate a broker.
The API command never bootstraps or repairs a schema.

The database binds only to `127.0.0.1:55432`, database `trader_console_demo`, user `console_demo`, password
`console_demo_local`. These are public local-fixture credentials, not production credentials. Helpers hard-code the
loopback host and demo identity, verify the connected database/user before changes, and ignore `PG_*` and
`TRADER_CONSOLE_DATABASE_URL`. No generic DSN option is accepted. A non-default `--database-port` is available for
isolated tests; it must match `CONSOLE_DEMO_DATABASE_PORT` supplied to Compose.

If 55432 is occupied or reserved by Docker Desktop, leave the existing service alone and select a free loopback
port, for example 25432. Use the same override for **every** Compose command and pass it to every demo helper:

<!-- verified: integration:console tests/cross_package/workflows/test_console_demo_postgres.py -->
```bash
CONSOLE_DEMO_DATABASE_PORT=25432 docker compose -f examples/console_demo/compose.yml up -d --wait
uv run python -m examples.console_demo bootstrap --database-port 25432
uv run python -m examples.console_demo api --database-port 25432
```

For the exercises below, likewise add `--database-port 25432` to `break-schema` and `restore-schema`, and prefix
Compose stop/start/down commands with `CONSOLE_DEMO_DATABASE_PORT=25432`. The API/frontend ports remain 8001/3000.

Expected API responses for this fixture:

| Endpoint | Expected response |
| --- | --- |
| `/api/context` | 200; `scope_id: console-demo`, `display_name: Local Console demo`, `environment: synthetic_demo`, `broker_account_display_label: null`, `broker_account_binding: not_applicable`. |
| `/health/live` | 200; `status: alive`, `service: trader-console-api`, independently of runtime database availability. |
| `/health/ready` (healthy) | 200; `status: ready`, `scope_id: console-demo`, `contract_version: 5`, `issues: []`. |
| `/health/ready` (database stopped) | 503; `status: unavailable`, `contract_version: null`, `issues: [database_unavailable]`. |
| `/health/ready` (metadata removed) | 503; `status: unavailable`, `contract_version: null`, `issues: [schema_metadata_missing]`. |

The compatibility version is metadata, not a relation name or fixture data version. Later stories add their own
deterministic trading data and expected outcomes.

## Exercise failure and recovery

Keep the API/frontend running; use Refresh/Retry after each step.

| Exercise | Expected screen |
| --- | --- |
| Healthy | Synthetic demo; brokerage account not applicable; API available; database compatible. |
| Database stopped | Configured context stays visible; API available; database unavailable with a reason. |
| Metadata removed after startup | API available; database unavailable with missing-schema guidance. |
| API stopped, or startup refused | API unavailable; no invented context on a fresh page. |
| Database/metadata restored | Retry returns to compatible; no fabricated trading-health claim. |

<!-- verified: integration:console tests/cross_package/workflows/test_console_demo_postgres.py -->
```bash
docker compose -f examples/console_demo/compose.yml stop postgres
docker compose -f examples/console_demo/compose.yml up -d --wait
uv run python -m examples.console_demo break-schema
uv run python -m examples.console_demo restore-schema
```

Run the steps individually to observe each state. `break-schema` removes only the demo's `trader_console`
compatibility metadata row; `restore-schema` reinstalls it through the canonical producer installer. Recorded source
data is untouched. If the API starts while metadata is absent, startup fails; restore it and restart the API.

## Stop and verify

Stop both foreground processes with Ctrl-C. Stop the demo database without deleting its retained volume:

<!-- verified: integration:console tests/cross_package/workflows/test_console_demo_postgres.py -->
```bash
docker compose -f examples/console_demo/compose.yml down
CONSOLE_DEMO_TESTS=1 uv run pytest tests/cross_package/workflows/test_console_demo.py tests/cross_package/workflows/test_console_demo_postgres.py -q
```

The tests create a unique Compose project and temporary volume on a free loopback port, then remove **only their own**
resources. They never connect to the manually running demo or a `PG_TEST_*` database. This explicit test-owned fixture
is gated by `CONSOLE_DEMO_TESTS=1` and `pytest.mark.postgres`; ordinary offline runs cannot provision Docker resources.
On WSL with Docker Desktop, the workflow resolves `docker.exe` and passes the temporary port through a short-lived
Compose env file so the Python process and Windows-published PostgreSQL port agree. Full browser verification is
documented in the app README. No remote deployment or trading qualification is implied.

## First-journey qualification

The qualification combines the fixture/API lifecycle check above with the app's real browser workflow, generated
contract checks, focused API/UI tests and repository boundary/documentation checks. The browser checks desktop/mobile
context, keyboard Refresh/Retry, real database/schema failures, recovery and initial API unavailability. Component
tests separately cover loading, retained last-known context, unknown issue codes, cancellation and timeout.

Record the full Git revision, whether the working tree is dirty, toolchain versions and exact checks/results in the
Notion work item. An uncommitted demonstration is evidence for that working tree, not a claim about the base commit
alone. Qualification of this connection screen does not qualify trading operations, production IAM or future stories.

## Execution-to-review qualification

The producer-backed Console qualification owns a fresh Compose database and starts the API, a separate worker process,
and the frontend independently. It saves one exact scope, authors and submits a definition, runs the maintained
catalogue strategy through `BacktestRunner`, replays the command idempotency key, and reopens the persisted result in
the review page. The run carries its saved-scope fingerprint, provider policy, benchmark and assumptions into
`console_read`; the test also checks fills, risk evidence, warnings, comparison state, canonical Evaluation evidence,
and a human reject decision.

<!-- verified: integration:console tests/cross_package/workflows/test_console_execution_to_review.py tests/cross_package/workflows/test_console_execution_to_review_browser.py -->
```bash
CONSOLE_EXECUTION_TESTS=1 CONSOLE_EXECUTION_BROWSER_TESTS=1 \
  uv run pytest tests/cross_package/workflows/test_console_execution_to_review.py \
  tests/cross_package/workflows/test_console_execution_to_review_browser.py -q
```

The fixture is deterministic and local. Focused worker tests cover failed and ambiguous outcomes; replay-bar identity
and broader outage campaigns remain separate qualification work.
