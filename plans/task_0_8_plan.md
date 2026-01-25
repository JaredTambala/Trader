# Incremental Delivery Plan for Task 0.8 – AlpacaPaperBroker Adapter

## Overview
The goal of **Task 0.8** is to implement a concrete `AlpacaPaperBroker` that uses the official `alpaca-py` SDK to place real paper trades while preserving the idempotent, auditable order lifecycle defined for Stage 0.  The work is split into small, testable increments that can be built, verified, and merged independently.

## Incremental Chunks

| Chunk | Description | Files Affected | Acceptance Criteria |
|------|-------------|----------------|----------------------|
| **0️⃣ Prep** | Review existing broker abstractions and Alpaca SDK usage. Identify any missing imports or helper functions. | `src/trader/broker.py`, `src/trader/alpaca_market_data.py` | A short summary (in comments) of the current `Broker` contract and Alpaca client methods is added. No code changes yet. |
| **1️⃣ Config** | Add loading of Alpaca credentials (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL`) to the central config module. Provide defaults for local development. | `src/trader/config.py` | `Config.alpaca_api_key`, `Config.alpaca_secret_key`, `Config.alpaca_base_url` properties exist and are populated from `os.getenv`. |
| **2️⃣ Class Skeleton** | Create `AlpacaPaperBroker` class inheriting from `Broker`. Initialise the `alpaca-py` client in `__init__`. | `src/trader/broker.py` | Class compiles; unit test can instantiate it without contacting the network. |
| **3️⃣ Status Mapping** | Define a mapping dict from Alpaca order status strings to the canonical state machine (`created`, `validated`, `submitted`, `accepted`, `partially_filled`, `filled`, `rejected`, `canceled`, `expired`, `error`). Add a helper method `_map_status`. | `src/trader/broker.py` | Mapping covers all Alpaca statuses; `_map_status` returns a valid canonical state for any known status. |
| **4️⃣ Positions API** | Implement `get_positions()` that calls `client.get_all_positions()` and returns a list of simplified position dicts matching the internal model. | `src/trader/broker.py` | Returns a list of dicts with keys `symbol`, `qty`, `avg_entry_price`, `side`. Unit test with mocked client verifies shape. |
| **5️⃣ Order ID Helper** | Ensure deterministic `client_order_id` generation is used. Add a small wrapper in `AlpacaPaperBroker.place_orders` that calls `deterministic_client_order_id` when the payload lacks it. | `src/trader/broker.py`, `src/trader/identifiers.py` | Orders passed to Alpaca always contain a deterministic `client_order_id`. |
| **6️⃣ Idempotency Check** | Before submitting, query the event store (`EventStore`) for existing `client_order_id` rows with status in `{submitted, accepted, partially_filled, filled}`. Skip submission if found; otherwise proceed. | `src/trader/broker.py`, `src/trader/data.py` | No duplicate Alpaca orders are created on retry; covered by integration test. |
| **7️⃣ Place Orders** | Implement `place_orders(orders)`:
  * Validate payloads (symbol, side, qty).
  * Perform idempotency check (Chunk 6).
  * Call `client.submit_order(...)` with deterministic `client_order_id`.
  * Record a `submitted` event with the returned `broker_order_id`.
  * Return a list of broker response dicts. | `src/trader/broker.py` | Successful submission creates a `submitted` row in `order_events`; mock test confirms correct fields. |
| **8️⃣ Order Retrieval** | Implement `get_order_by_id(broker_order_id)` that fetches a single order via `client.get_order(broker_order_id)` and maps it to the internal representation. | `src/trader/broker.py` | Returns dict with at least `client_order_id`, `status`, `filled_qty`, `filled_avg_price`. |
| **9️⃣ List Orders** | Implement `list_orders(since_ts)` using Alpaca's `list_orders` endpoint with a `submitted_at` filter. Convert each order to internal dict and map status via Chunk 3. | `src/trader/broker.py` | Returns a list of orders newer than `since_ts`; used by reconciliation step. |
| **🔟 Optional Account** | Add `get_account()` that returns basic account info (cash, buying power) via `client.get_account()`. | `src/trader/broker.py` | Method exists and returns a dict; not required for core functionality. |
| **1️⃣1️⃣ Retry Logic** | Wrap all external Alpaca calls in a retry decorator (max 3 attempts, exponential back‑off). Catch network‑related exceptions (`httpx.RequestError`, rate‑limit errors). | `src/trader/broker.py` | Transient failures are retried; after max attempts an exception propagates. |
| **1️⃣2️⃣ Error Handling** | If an order submission raises an unexpected exception or returns an ambiguous state, write an `order_event` with `status='error'` and let the reconciliation step (Task 0.10) handle it later. | `src/trader/broker.py`, `src/trader/cycle.py` | `order_events` contain an `error` row for failed submissions; reconciliation can update it. |
| **1️⃣3️⃣ Tests** | Add integration tests (`tests/test_alpaca_broker.py`) that mock the Alpaca client:
  * Verify idempotent resubmission prevention.
  * Simulate ambiguous submission → `error` → reconciliation.
  * Test status mapping for each Alpaca status value.
 | `tests/test_alpaca_broker.py` | All tests pass with `uv run pytest`. Coverage ≥ 90 % for the new broker code. |
| **1️⃣4️⃣ Docs** | Update `docs/execution.md`:
  * Add a table mapping Alpaca statuses to canonical states.
  * Document the idempotency guarantees and reconciliation flow.
  * Show example configuration snippet for Alpaca credentials.
 | `docs/execution.md` | Documentation builds without errors; new sections are present. |
| **1️⃣5️⃣ Export** | Expose `AlpacaPaperBroker` in the module's `__all__` and update the broker factory in `src/trader/broker.py` so `BROKER=alpaca` creates an instance. | `src/trader/broker.py` | Running the app with `BROKER=alpaca` uses the new class (verified by a smoke test). |
| **1️⃣6️⃣ Full Suite** | Run the complete test suite (`uv run pytest`). Fix any regressions introduced by the new code. | Entire repo | All tests pass; CI would succeed. |

## Milestone Timeline (suggested)
1. **Prep → Config → Class Skeleton** (Days 1‑2)
2. **Status Mapping → Positions API** (Day 3)
3. **Idempotency Check → Place Orders** (Days 4‑5)
4. **Order Retrieval & List Orders** (Day 6)
5. **Retry & Error Handling** (Day 7)
6. **Tests & Docs** (Days 8‑9)
7. **Export & Full Suite** (Day 10)

Each chunk can be developed in its own feature branch, reviewed, and merged independently, ensuring a continuously releasable code base.

---

*The plan lives in `plans/task_0_8_plan.md` for easy reference by downstream modes.*

