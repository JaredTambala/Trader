"""Alpaca broker adapter and legacy broker export surface."""

from __future__ import annotations

from importlib import import_module
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence, cast

try:  # pragma: no cover - optional alpaca dependency
    _TradingClient: Any = import_module("alpaca.trading.client").TradingClient
    _OrderSide: Any = import_module("alpaca.trading.enums").OrderSide
    _TimeInForce: Any = import_module("alpaca.trading.enums").TimeInForce
    _LimitOrderRequest: Any = import_module("alpaca.trading.requests").LimitOrderRequest
    _MarketOrderRequest: Any = import_module("alpaca.trading.requests").MarketOrderRequest
except Exception:  # pragma: no cover - alpaca not installed in test env
    _TradingClient = None
    _OrderSide = None
    _TimeInForce = None
    _MarketOrderRequest = None
    _LimitOrderRequest = None

from ..event_store import EventStore
from ..symbols import canonicalize_symbol, normalize_asset_class
from .alpaca_domain import (
    ALREADY_SUBMITTED_STATUSES,
    OPEN_ORDER_STATUSES,
    AlpacaOrderRequestFields,
    AlpacaReconciliationFillEvent,
    AlpacaReconciliationOrderEvent,
    AlpacaSubmissionErrorResponse,
    build_alpaca_reconciliation_fill_event,
    build_alpaca_reconciliation_order_event,
    build_alpaca_submission_error_response,
    ensure_alpaca_client_order_id,
    map_alpaca_status,
    normalize_alpaca_order_response,
    normalize_alpaca_order_request_fields,
)
from .contracts import (
    AccountBroker,
    Broker,
    OrderCancelBroker,
    OrderLookupBroker,
    OrderReconcileBroker,
)
from .helpers import coerce_float as _coerce_float
from .internal import InternalPaperBroker, NoOpBroker

_ClientFactory = Any
_EnumFactory = Any
_RequestFactory = Any


__all__ = [
    "AccountBroker",
    "AlpacaOrderRequestFields",
    "AlpacaReconciliationFillEvent",
    "AlpacaReconciliationOrderEvent",
    "AlpacaPaperBroker",
    "AlpacaSubmissionErrorResponse",
    "Broker",
    "InternalPaperBroker",
    "NoOpBroker",
    "OrderCancelBroker",
    "OrderLookupBroker",
    "OrderReconcileBroker",
    "ensure_alpaca_client_order_id",
]


class AlpacaPaperBroker(Broker):
    """Broker adapter for Alpaca paper trading.

    The adapter converts the project's canonical order payloads into alpaca-py
    requests, retries transient client failures, normalizes provider responses
    back into local order-event fields, and uses the event store to avoid
    duplicate submissions for already-open client order IDs.
    """

    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        base_url: str | None = None,
        event_store: EventStore | None = None,
        client: object | None = None,
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        """Create an Alpaca trading client or wrap an injected test client.

        Args:
            api_key: Alpaca API key used when constructing a real client.
            secret_key: Alpaca secret key used when constructing a real client.
            base_url: Optional paper-trading endpoint override.
            event_store: Optional local event store used for idempotency checks
                and reconciliation writes.
            client: Injected alpaca-py compatible client for tests.
            max_retries: Number of attempts for provider calls.
            retry_backoff_seconds: Base exponential backoff between attempts.

        Raises:
            ImportError: If alpaca-py is unavailable and no client is injected.
        """
        self._client: Any
        if client is None:
            trading_client: _ClientFactory = _TradingClient
            if trading_client is None:
                raise ImportError("alpaca-py is required to use AlpacaPaperBroker")
            try:
                self._client = trading_client(
                    api_key,
                    secret_key,
                    paper=True,
                    base_url=base_url,
                )
            except TypeError:
                self._client = trading_client(
                    api_key,
                    secret_key,
                    paper=True,
                )
                if base_url:
                    logging.getLogger(__name__).warning(
                        "TradingClient does not accept base_url; using default endpoint"
                    )
        else:
            self._client = client
        self._event_store = event_store
        self._logger = logging.getLogger(__name__)
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds

    def get_positions(self) -> Sequence[Mapping[str, object]]:
        """Fetch and normalize open positions from Alpaca.

        Returns:
            Position mappings with canonical symbol spelling, normalized asset
            class, signed quantity, average entry price, and side. Numeric
            values may still be provider-derived strings until downstream
            portfolio code coerces them.
        """
        positions = cast(Sequence[object], self._with_retries(self._client.get_all_positions))
        results: list[Mapping[str, object]] = []
        for position in positions or []:
            symbol = str(getattr(position, "symbol", "") or "").strip().upper()
            raw_asset_class = str(getattr(position, "asset_class", "") or "").strip()
            asset_class = normalize_asset_class(raw_asset_class)
            symbol = canonicalize_symbol(symbol, asset_class=asset_class)
            qty_raw = getattr(position, "qty", 0) or 0
            avg_entry_price = getattr(position, "avg_entry_price", None)
            side = getattr(position, "side", None)
            try:
                qty = float(qty_raw)
            except (TypeError, ValueError):
                qty = 0.0
            results.append(
                {
                    "symbol": symbol,
                    "asset_class": asset_class,
                    "qty": qty,
                    "avg_entry_price": float(avg_entry_price) if avg_entry_price is not None else None,
                    "side": str(side) if side is not None else ("long" if qty >= 0 else "short"),
                }
            )
        return results

    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Submit canonical order payloads while preserving idempotency.

        For each order the adapter ensures a deterministic `client_order_id`,
        checks the local event store for an existing open submission, attempts
        broker-side reconciliation when an order already exists, and submits a
        new Alpaca request only when no active broker order remains. Provider
        exceptions are converted into `error` responses so the cycle can persist
        an auditable terminal event instead of losing the attempted order.

        Args:
            orders: Risk-approved order payloads from the runtime cycle.

        Returns:
            Canonical broker response mappings, one per successfully submitted,
            reconciled, or failed order attempt.
        """
        responses: list[Mapping[str, object]] = []
        for order in orders:
            enriched = self._ensure_client_order_id(order)
            client_order_id = str(enriched["client_order_id"])
            existing = self._find_existing_order(client_order_id)
            if existing is not None and existing.get("status") in ALREADY_SUBMITTED_STATUSES:
                broker_order_id = existing.get("broker_order_id")
                reconciled = self._reconcile_existing_order(
                    client_order_id,
                    str(broker_order_id) if broker_order_id is not None else None,
                )
                if reconciled is not None:
                    reconciled_status = str(reconciled.get("status", "")).lower()
                    self._logger.info(
                        "Reconciled existing Alpaca order client_order_id=%s status=%s",
                        client_order_id,
                        reconciled_status,
                    )
                    if reconciled_status in OPEN_ORDER_STATUSES:
                        responses.append(reconciled)
                        continue  # keep waiting on the open order
                    # terminal state -> allow new submission
                else:
                    self._logger.info(
                        "No broker record for existing order client_order_id=%s; submitting new order",
                        client_order_id,
                    )
            try:
                order_request = self._build_order_request(enriched)
                response = self._with_retries(self._client.submit_order, order_data=order_request)
                responses.append(self._normalize_order_response(response, enriched))
            except Exception as exc:
                self._logger.exception("Alpaca order submission failed client_order_id=%s: %s", client_order_id, exc)
                responses.append(
                    build_alpaca_submission_error_response(
                        client_order_id=client_order_id,
                        error=exc,
                    ).to_record()
                )
        return responses

    def get_order_by_id(self, broker_order_id: str) -> Mapping[str, object]:
        """Fetch and normalize one broker order by its Alpaca identifier.

        Args:
            broker_order_id: Provider-side order ID returned by Alpaca.

        Returns:
            Canonical order response fields used by reconciliation and recovery.

        Raises:
            AttributeError: If the injected client lacks an order lookup method.
        """
        getter = getattr(self._client, "get_order_by_id", None) or getattr(self._client, "get_order", None)
        if getter is None:
            raise AttributeError("Trading client does not support get_order_by_id")
        response = self._with_retries(getter, broker_order_id)
        return self._normalize_order_response(response, {})

    def list_orders(self, since_ts: datetime | None = None) -> Sequence[Mapping[str, object]]:
        """List broker orders and normalize them for local reconciliation.

        Args:
            since_ts: Optional timestamp passed to Alpaca as the lower bound for
                returned orders when the client supports it.

        Returns:
            Canonical response mappings ordered as supplied by the provider.

        Raises:
            AttributeError: If the injected client cannot list orders.
        """
        getter = getattr(self._client, "get_orders", None) or getattr(self._client, "list_orders", None)
        if getter is None:
            raise AttributeError("Trading client does not support list_orders/get_orders")
        kwargs: dict[str, object] = {}
        if since_ts is not None:
            kwargs["after"] = since_ts
        orders = cast(Sequence[object], self._with_retries(getter, **kwargs))
        results: list[Mapping[str, object]] = []
        for order in orders or []:
            results.append(self._normalize_order_response(order, {}))
        return results

    def get_account(self) -> Mapping[str, object]:
        """Fetch account-level balances from the Alpaca client.

        Returns:
            Mapping with `cash`, `buying_power`, and `equity` fields. Values are
            passed through from alpaca-py because provider precision is normally
            string based.

        Raises:
            AttributeError: If the injected client lacks account support.
        """
        getter = getattr(self._client, "get_account", None)
        if getter is None:
            raise AttributeError("Trading client does not support get_account")
        account = self._with_retries(getter)
        return {
            "cash": getattr(account, "cash", None),
            "buying_power": getattr(account, "buying_power", None),
            "equity": getattr(account, "equity", None),
        }

    def cancel_order(self, broker_order_id: str) -> None:
        """Request cancellation of a single Alpaca order.

        Args:
            broker_order_id: Provider-side order ID to cancel.

        Raises:
            AttributeError: If the injected client lacks cancellation support.
            Exception: Provider errors after retries are surfaced to the caller.
        """
        canceler = getattr(self._client, "cancel_order_by_id", None)
        if canceler is None:
            raise AttributeError("Trading client does not support cancel_order_by_id")
        self._with_retries(canceler, broker_order_id)

    def reconcile_orders(self, since_ts: datetime | None = None) -> Sequence[Mapping[str, object]]:
        """Repair local open-order state from Alpaca and append new events.

        The method loads the latest local event per client order, asks Alpaca
        for current broker-side state, and writes only append-only order/fill
        events for status transitions. Local open orders missing from Alpaca are
        closed as `canceled` with a `reconciled_missing` reason so operators can
        see the reconciliation decision.

        Args:
            since_ts: Optional lower bound for broker orders inspected.

        Returns:
            The normalized status updates appended to the local event store. An
            empty list means there was no event store, no open local orders, or
            no broker-visible transition to persist.
        """
        if not self._event_store:
            return []
        latest_events = self._load_latest_order_events()
        open_events = [event for event in latest_events if event["status"] in OPEN_ORDER_STATUSES]
        if not open_events:
            return []
        try:
            broker_orders = self.list_orders(since_ts)
        except Exception as exc:  # pragma: no cover - relies on Alpaca
            self._logger.warning("Order reconciliation list_orders failed: %s", exc)
            broker_orders = []
        broker_by_client = {
            str(order.get("client_order_id")): order
            for order in broker_orders
            if order.get("client_order_id")
        }
        updates: list[Mapping[str, object]] = []
        for event in open_events:
            client_order_id = str(event["client_order_id"])
            broker_order = broker_by_client.get(client_order_id)
            if broker_order is None and event.get("broker_order_id"):
                try:
                    broker_order = self.get_order_by_id(str(event["broker_order_id"]))
                except Exception as exc:  # pragma: no cover - relies on Alpaca
                    self._logger.warning(
                        "Order reconciliation fetch failed client_order_id=%s: %s",
                        client_order_id,
                        exc,
                    )
                    broker_order = None
            if not broker_order:
                payload = build_alpaca_reconciliation_order_event(
                    event,
                    status="canceled",
                    order_event_id=f"order_evt_{uuid.uuid4().hex}",
                    created_at=datetime.now(timezone.utc),
                    broker_order_id=event.get("broker_order_id"),
                    rejection_reason="reconciled_missing",
                ).to_record()
                self._event_store.record_event("order_events", payload)
                updates.append(payload)
                continue
            status = str(broker_order.get("status", ""))
            if not status or status == event["status"]:
                continue
            payload = build_alpaca_reconciliation_order_event(
                event,
                status=status,
                order_event_id=f"order_evt_{uuid.uuid4().hex}",
                created_at=broker_order.get("fill_ts") or datetime.now(timezone.utc),
                broker_order_id=broker_order.get("broker_order_id") or event.get("broker_order_id"),
                rejection_reason=broker_order.get("rejection_reason"),
            ).to_record()
            self._event_store.record_event("order_events", payload)
            updates.append(payload)
            if status in {"filled", "partially_filled"}:
                fill_payload = build_alpaca_reconciliation_fill_event(
                    event,
                    broker_order,
                    fill_ts=broker_order.get("fill_ts") or datetime.now(timezone.utc),
                )
                if fill_payload is not None:
                    self._event_store.record_event("fill_events", fill_payload.to_record())
        return updates

    def _with_retries(
        self,
        func: Callable[..., object],
        *args: object,
        **kwargs: object,
    ) -> object:
        """Run an Alpaca client call with bounded exponential backoff.

        The helper retries only by re-invoking the supplied callable; it does not
        inspect exception types because alpaca-py has changed its exception
        hierarchy across versions. The last provider exception is re-raised so
        callers can record an explicit failure response.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - depends on network errors
                last_exc = exc
                if attempt == self._max_retries:
                    break
                time.sleep(self._retry_backoff_seconds * (2 ** (attempt - 1)))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Alpaca call failed without exception")

    def _ensure_client_order_id(self, order: Mapping[str, object]) -> Mapping[str, object]:
        """Return an order carrying the deterministic local client order ID.

        Existing IDs are preserved so externally supplied IDs remain stable. If
        absent, the ID is derived from cycle, symbol, side, and quantity to make
        retries idempotent across process restarts.
        """
        return ensure_alpaca_client_order_id(order)

    def _build_order_request(self, order: Mapping[str, object]) -> object:
        """Translate a canonical order mapping into an alpaca-py request.

        Crypto symbols are converted from market-data spelling (`BTC/USD`) to
        trading spelling (`BTCUSD`), unsupported crypto day orders are promoted
        to `gtc`, and a plain mapping fallback is returned when tests inject a
        lightweight client without alpaca-py request classes.
        """
        fields = normalize_alpaca_order_request_fields(order)
        market_order_request: _RequestFactory = _MarketOrderRequest
        limit_order_request: _RequestFactory = _LimitOrderRequest
        order_side: _EnumFactory = _OrderSide
        time_in_force: _EnumFactory = _TimeInForce
        if (
            market_order_request is not None
            and limit_order_request is not None
            and order_side is not None
            and time_in_force is not None
        ):
            side_enum = order_side.BUY if fields.side == "buy" else order_side.SELL
            if fields.time_in_force in {"day", "daytime"}:
                tif_enum = time_in_force.DAY
            elif fields.time_in_force in {"ioc", "immediate_or_cancel"} and hasattr(time_in_force, "IOC"):
                tif_enum = time_in_force.IOC
            else:
                tif_enum = time_in_force.GTC
            if fields.order_type == "limit":
                return limit_order_request(
                    symbol=fields.symbol,
                    qty=fields.qty,
                    side=side_enum,
                    time_in_force=tif_enum,
                    limit_price=_coerce_float(fields.limit_price),
                    client_order_id=fields.client_order_id,
                )
            return market_order_request(
                symbol=fields.symbol,
                qty=fields.qty,
                side=side_enum,
                time_in_force=tif_enum,
                client_order_id=fields.client_order_id,
            )
        return fields.to_fallback_mapping()

    def _normalize_order_response(
        self,
        response: object,
        order: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Convert an Alpaca response object or mapping into local order fields.

        The normalizer accepts both alpaca-py objects and dict-like test fakes,
        maps provider statuses into the project's canonical lifecycle states,
        canonicalizes symbol/asset-class spelling, and preserves fill quantity,
        price, timestamps, and rejection reason for persistence.
        """
        return normalize_alpaca_order_response(response, order)

    def _map_status(self, status: str) -> str:
        """Map provider status strings to the local order lifecycle vocabulary."""
        return map_alpaca_status(status)

    def _find_existing_order(self, client_order_id: str) -> Mapping[str, object] | None:
        """Return the latest local order event used for submit idempotency.

        Both DuckDB and Postgres-backed stores are supported by selecting the
        correct positional placeholder. Query failures are logged and treated as
        a miss so submission can continue with an explicit provider response.
        """
        if not self._event_store:
            return None
        connection = getattr(self._event_store, "connection", lambda: None)()
        if connection is None:
            return None
        module_name = connection.__class__.__module__
        placeholder = "?" if "duckdb" in module_name else "%s"
        query = (
            f"SELECT status, broker_order_id FROM order_events "
            f"WHERE client_order_id = {placeholder} "
            f"ORDER BY created_at DESC LIMIT 1"
        )
        try:
            if hasattr(connection, "cursor"):
                with connection.cursor() as cursor:
                    cursor.execute(query, [client_order_id])
                    row = cursor.fetchone()
            else:
                row = connection.execute(query, [client_order_id]).fetchone()
        except Exception as exc:
            self._logger.warning("Order lookup failed: %s", exc)
            return None
        if not row:
            return None
        return {
            "client_order_id": client_order_id,
            "status": row[0],
            "broker_order_id": row[1],
        }

    def _reconcile_existing_order(
        self,
        client_order_id: str,
        broker_order_id: str | None,
    ) -> Mapping[str, object] | None:
        """Fetch broker state for a locally known order before resubmitting."""
        try:
            if broker_order_id:
                return self.get_order_by_id(str(broker_order_id))
        except Exception as exc:  # pragma: no cover - relies on Alpaca
            self._logger.warning(
                "Order reconciliation failed client_order_id=%s: %s",
                client_order_id,
                exc,
            )
        return None

    def _load_latest_order_events(self) -> Sequence[Mapping[str, object]]:
        """Load one latest local lifecycle event per client order.

        The reconciliation path needs local open orders, not every historical
        event. Rows are sorted newest first and de-duplicated in Python so the
        same query works against the project's supported test and production
        connection types.
        """
        connection = getattr(self._event_store, "connection", lambda: None)()
        if connection is None:
            return []
        query = (
            "SELECT client_order_id, run_id, cycle_id, symbol, side, qty, order_type, "
            "status, broker_order_id, created_at "
            "FROM order_events ORDER BY created_at DESC, order_event_id DESC"
        )
        try:
            if hasattr(connection, "cursor"):
                with connection.cursor() as cursor:
                    cursor.execute(query)
                    rows = cursor.fetchall()
            else:
                rows = connection.execute(query).fetchall()
        except Exception as exc:
            self._logger.warning("Order reconciliation query failed: %s", exc)
            return []
        seen: set[str] = set()
        latest: list[Mapping[str, object]] = []
        for row in rows or []:
            client_order_id = str(row[0]) if row[0] is not None else ""
            if not client_order_id or client_order_id in seen:
                continue
            seen.add(client_order_id)
            latest.append(
                {
                    "client_order_id": client_order_id,
                    "run_id": row[1],
                    "cycle_id": row[2],
                    "symbol": row[3],
                    "side": row[4],
                    "qty": row[5],
                    "order_type": row[6],
                    "status": row[7],
                    "broker_order_id": row[8],
                    "created_at": row[9],
                }
            )
        return latest
