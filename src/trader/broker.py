"""Broker interface for order execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

try:  # pragma: no cover - optional alpaca dependency
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
except Exception:  # pragma: no cover - alpaca not installed in test env
    TradingClient = None
    OrderSide = None
    TimeInForce = None
    MarketOrderRequest = None
    LimitOrderRequest = None

from .data import EventStore
from .identifiers import deterministic_client_order_id
from .symbols import canonicalize_symbol, normalize_asset_class

_ALPACA_STATUS_MAP = {
    "new": "submitted",
    "pending_new": "submitted",
    "accepted": "accepted",
    "accepted_for_bidding": "accepted",
    "partially_filled": "partially_filled",
    "filled": "filled",
    "done_for_day": "filled",
    "canceled": "canceled",
    "pending_cancel": "canceled",
    "expired": "expired",
    "rejected": "rejected",
    "replaced": "submitted",
    "pending_replace": "submitted",
    "held": "error",
    "suspended": "error",
    "stopped": "error",
}
_ALREADY_SUBMITTED_STATUSES = {"submitted", "accepted", "partially_filled", "filled"}
_OPEN_ORDER_STATUSES = {"submitted", "accepted", "partially_filled", "error"}


class Broker(ABC):
    """Submits orders to a trading venue or paper broker."""

    @abstractmethod
    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Submit orders and return broker responses.

        Args:
            orders: Iterable of order payloads ready for execution.

        Returns:
            Sequence of broker response payloads.

        Raises:
            Exception: Implementations raise if submission fails or is rejected.
        """


class NoOpBroker(Broker):
    """Broker that accepts orders without executing them."""

    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Accept orders without executing them.

        Args:
            orders: Iterable of order payloads.

        Returns:
            An empty list, since no orders are actually submitted.

        Raises:
            None.
        """
        return []


class InternalPaperBroker(Broker):
    """Paper broker that can simulate fills, latency, and rejection."""

    def __init__(
        self,
        *,
        reject_probability: float = 0.0,
        fill_delay_ms_mean: float = 0.0,
        fill_delay_ms_stddev: float = 0.0,
        fill_qty_fraction_mean: float = 1.0,
        fill_qty_fraction_stddev: float = 0.0,
        rng_seed: int | None = None,
    ) -> None:
        """Initialize the instance."""
        self._logger = logging.getLogger(__name__)
        self._reject_probability = max(0.0, min(float(reject_probability), 1.0))
        self._fill_delay_ms_mean = max(0.0, float(fill_delay_ms_mean))
        self._fill_delay_ms_stddev = max(0.0, float(fill_delay_ms_stddev))
        self._fill_qty_fraction_mean = max(0.0, float(fill_qty_fraction_mean))
        self._fill_qty_fraction_stddev = max(0.0, float(fill_qty_fraction_stddev))
        self._rng = random.Random(rng_seed)

    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Submit orders to the broker backend."""
        responses: list[Mapping[str, object]] = []
        timestamp = datetime.now(timezone.utc)
        for order in orders:
            symbol = str(order.get("symbol", "")).strip().upper()
            side = str(order.get("side", "")).lower().strip()
            qty = float(order.get("qty", 0.0) or 0.0)
            run_id = order.get("run_id")
            cycle_id = order.get("cycle_id")
            price = order.get("price")
            if not symbol or side not in {"buy", "sell"} or qty <= 0:
                self._logger.warning("Skipping invalid order payload=%s", order)
                continue
            if cycle_id is None:
                raise ValueError("cycle_id is required for internal broker orders")
            if self._reject_probability > 0 and self._rng.random() < self._reject_probability:
                responses.append(
                    {
                        "order_event_id": f"order_evt_{uuid.uuid4().hex}",
                        "client_order_id": order.get("client_order_id"),
                        "run_id": run_id,
                        "cycle_id": cycle_id,
                        "symbol": symbol,
                        "status": "rejected",
                        "broker_order_id": None,
                        "order_type": str(order.get("order_type", "market")),
                        "qty": qty,
                        "fill_ts": timestamp,
                        "fill_qty": None,
                        "fill_price": None,
                        "rejection_reason": "internal_reject_probability",
                    }
                )
                continue
            delay_ms = 0.0
            if self._fill_delay_ms_mean or self._fill_delay_ms_stddev:
                delay_ms = max(
                    0.0,
                    self._rng.gauss(self._fill_delay_ms_mean, self._fill_delay_ms_stddev),
                )
            if delay_ms:
                time.sleep(delay_ms / 1000.0)
            client_order_id = order.get("client_order_id") or deterministic_client_order_id(
                str(cycle_id),
                symbol,
                side,
                qty,
            )
            fill_fraction = 1.0
            if self._fill_qty_fraction_mean or self._fill_qty_fraction_stddev:
                fill_fraction = max(
                    0.0,
                    self._rng.gauss(self._fill_qty_fraction_mean, self._fill_qty_fraction_stddev),
                )
            fill_qty = qty * fill_fraction
            status = "filled" if price is not None else "error"
            if price is not None and 0 < fill_qty < qty:
                status = "partially_filled"
            created_at = order.get("created_at") or timestamp
            fill_price = float(price) if price is not None else None
            if fill_price is None:
                self._logger.warning("Missing price for order; fill skipped symbol=%s", symbol)
            responses.append(
                {
                    "order_event_id": f"order_evt_{uuid.uuid4().hex}",
                    "client_order_id": client_order_id,
                    "run_id": run_id,
                    "cycle_id": cycle_id,
                    "symbol": symbol,
                    "status": status,
                    "broker_order_id": None,
                    "order_type": str(order.get("order_type", "market")),
                    "qty": qty,
                    "fill_ts": created_at,
                    "fill_qty": fill_qty if fill_price is not None else None,
                    "fill_price": fill_price,
                }
            )
        return responses


class AlpacaPaperBroker(Broker):
    """Alpaca paper broker adapter using alpaca-py."""

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
        """Initialize the broker."""
        if client is None:
            if TradingClient is None:
                raise ImportError("alpaca-py is required to use AlpacaPaperBroker")
            try:
                self._client = TradingClient(
                    api_key,
                    secret_key,
                    paper=True,
                    base_url=base_url,
                )
            except TypeError:
                self._client = TradingClient(
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
        """Fetch open positions from Alpaca."""
        positions = self._with_retries(self._client.get_all_positions)
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
        """Submit orders to Alpaca with idempotency checks."""
        responses: list[Mapping[str, object]] = []
        for order in orders:
            enriched = self._ensure_client_order_id(order)
            client_order_id = str(enriched["client_order_id"])
            existing = self._find_existing_order(client_order_id)
            if existing is not None and existing.get("status") in _ALREADY_SUBMITTED_STATUSES:
                reconciled = self._reconcile_existing_order(client_order_id, existing.get("broker_order_id"))
                if reconciled is not None:
                    reconciled_status = str(reconciled.get("status", "")).lower()
                    self._logger.info(
                        "Reconciled existing Alpaca order client_order_id=%s status=%s",
                        client_order_id,
                        reconciled_status,
                    )
                    if reconciled_status in _OPEN_ORDER_STATUSES:
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
                    {
                        "client_order_id": client_order_id,
                        "status": "error",
                        "broker_order_id": None,
                        "rejection_reason": str(exc),
                    }
                )
        return responses

    def get_order_by_id(self, broker_order_id: str) -> Mapping[str, object]:
        """Fetch a single order by broker ID."""
        getter = getattr(self._client, "get_order_by_id", None) or getattr(self._client, "get_order", None)
        if getter is None:
            raise AttributeError("Trading client does not support get_order_by_id")
        response = self._with_retries(getter, broker_order_id)
        return self._normalize_order_response(response, {})

    def list_orders(self, since_ts: datetime | None = None) -> Sequence[Mapping[str, object]]:
        """List orders submitted since a timestamp."""
        getter = getattr(self._client, "get_orders", None) or getattr(self._client, "list_orders", None)
        if getter is None:
            raise AttributeError("Trading client does not support list_orders/get_orders")
        kwargs: dict[str, object] = {}
        if since_ts is not None:
            kwargs["after"] = since_ts
        orders = self._with_retries(getter, **kwargs)
        results: list[Mapping[str, object]] = []
        for order in orders or []:
            results.append(self._normalize_order_response(order, {}))
        return results

    def get_account(self) -> Mapping[str, object]:
        """Fetch basic account info."""
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
        """Cancel a single broker order by id."""
        canceler = getattr(self._client, "cancel_order_by_id", None)
        if canceler is None:
            raise AttributeError("Trading client does not support cancel_order_by_id")
        self._with_retries(canceler, broker_order_id)

    def reconcile_orders(self, since_ts: datetime | None = None) -> Sequence[Mapping[str, object]]:
        """Reconcile open orders and persist status transitions."""
        if not self._event_store:
            return []
        latest_events = self._load_latest_order_events()
        open_events = [event for event in latest_events if event["status"] in _OPEN_ORDER_STATUSES]
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
            client_order_id = event["client_order_id"]
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
                payload = {
                    "order_event_id": f"order_evt_{uuid.uuid4().hex}",
                    "client_order_id": client_order_id,
                    "run_id": event.get("run_id"),
                    "session_id": event.get("session_id") or event.get("run_id"),
                    "cycle_id": event.get("cycle_id"),
                    "symbol": event.get("symbol"),
                    "side": event.get("side"),
                    "qty": event.get("qty"),
                    "order_type": event.get("order_type", "market"),
                    "status": "canceled",
                    "broker_order_id": event.get("broker_order_id"),
                    "rejection_reason": "reconciled_missing",
                    "created_at": datetime.now(timezone.utc),
                }
                self._event_store.record_event("order_events", payload)
                updates.append(payload)
                continue
            status = str(broker_order.get("status", ""))
            if not status or status == event["status"]:
                continue
            payload = {
                "order_event_id": f"order_evt_{uuid.uuid4().hex}",
                "client_order_id": client_order_id,
                "run_id": event.get("run_id"),
                "session_id": event.get("session_id") or event.get("run_id"),
                "cycle_id": event.get("cycle_id"),
                "symbol": event.get("symbol"),
                "side": event.get("side"),
                "qty": event.get("qty"),
                "order_type": event.get("order_type", "market"),
                "status": status,
                "broker_order_id": broker_order.get("broker_order_id") or event.get("broker_order_id"),
                "rejection_reason": broker_order.get("rejection_reason"),
                "created_at": broker_order.get("fill_ts") or datetime.now(timezone.utc),
            }
            self._event_store.record_event("order_events", payload)
            updates.append(payload)
            if status in {"filled", "partially_filled"}:
                fill_qty = broker_order.get("fill_qty")
                fill_price = broker_order.get("fill_price")
                if fill_qty is not None and fill_price is not None:
                    self._event_store.record_event(
                        "fill_events",
                        {
                            "client_order_id": client_order_id,
                            "run_id": event.get("run_id"),
                            "session_id": event.get("session_id") or event.get("run_id"),
                            "cycle_id": event.get("cycle_id"),
                            "fill_ts": broker_order.get("fill_ts") or datetime.now(timezone.utc),
                            "fill_qty": float(fill_qty),
                            "fill_price": float(fill_price),
                        },
                    )
        return updates

    def _with_retries(self, func, *args, **kwargs):  # type: ignore[no-untyped-def]
        """Retry helper for Alpaca API calls."""
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
        """Ensure deterministic client order id."""
        if order.get("client_order_id"):
            return order
        cycle_id = str(order.get("cycle_id", ""))
        symbol = str(order.get("symbol", "")).strip().upper()
        side = str(order.get("side", "")).lower().strip()
        qty = float(order.get("qty", 0.0) or 0.0)
        client_order_id = deterministic_client_order_id(cycle_id, symbol, side, qty)
        return {**order, "client_order_id": client_order_id}

    def _build_order_request(self, order: Mapping[str, object]) -> object:
        """Build an Alpaca order request payload."""
        symbol = str(order.get("symbol", "")).strip().upper()
        side = str(order.get("side", "")).lower().strip()
        qty = float(order.get("qty", 0.0) or 0.0)
        tif = str(order.get("time_in_force", "day")).lower()
        asset_class = str(order.get("asset_class", "")).lower()
        if asset_class in {"crypto", "cryptocurrency"} and "/" in symbol:
            # Alpaca trading endpoints commonly use "BTCUSD" while market data uses "BTC/USD".
            symbol = symbol.replace("/", "")
        if asset_class in {"crypto", "cryptocurrency"} and tif in {"day", "daytime"}:
            tif = "gtc"
        order_type = str(order.get("order_type", "market")).lower()
        client_order_id = str(order.get("client_order_id", ""))
        if MarketOrderRequest and LimitOrderRequest and OrderSide and TimeInForce:
            side_enum = OrderSide.BUY if side == "buy" else OrderSide.SELL
            if tif in {"day", "daytime"}:
                tif_enum = TimeInForce.DAY
            elif tif in {"ioc", "immediate_or_cancel"} and hasattr(TimeInForce, "IOC"):
                tif_enum = TimeInForce.IOC
            else:
                tif_enum = TimeInForce.GTC
            if order_type == "limit":
                limit_price = float(order.get("limit_price") or order.get("price") or 0.0)
                return LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=side_enum,
                    time_in_force=tif_enum,
                    limit_price=limit_price,
                    client_order_id=client_order_id,
                )
            return MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side_enum,
                time_in_force=tif_enum,
                client_order_id=client_order_id,
            )
        return {
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "time_in_force": tif,
            "type": order_type,
            "client_order_id": client_order_id,
            "limit_price": order.get("limit_price") or order.get("price"),
        }

    def _normalize_order_response(
        self,
        response: object,
        order: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Normalize Alpaca order response into internal fields."""
        status_raw = self._coerce_value(response, "status")
        status = self._map_status(str(status_raw) if status_raw is not None else "")
        broker_order_id = self._coerce_value(response, "id") or self._coerce_value(response, "order_id")
        filled_qty = self._coerce_value(response, "filled_qty")
        filled_avg_price = self._coerce_value(response, "filled_avg_price")
        rejection_reason = (
            self._coerce_value(response, "rejection_reason")
            or self._coerce_value(response, "reject_reason")
            or self._coerce_value(response, "rejected_reason")
        )
        raw_symbol = self._coerce_value(response, "symbol") or order.get("symbol")
        raw_asset_class = self._coerce_value(response, "asset_class") or order.get("asset_class")
        asset_class = normalize_asset_class(str(raw_asset_class) if raw_asset_class is not None else "")
        symbol = canonicalize_symbol(str(raw_symbol) if raw_symbol is not None else "", asset_class=asset_class)
        side = self._coerce_enumish(self._coerce_value(response, "side") or order.get("side"))
        order_type = self._coerce_enumish(
            self._coerce_value(response, "order_type")
            or self._coerce_value(response, "type")
            or order.get("order_type")
        )
        qty_raw = self._coerce_value(response, "qty") or order.get("qty")
        response_client_id = self._coerce_value(response, "client_order_id")
        client_order_id = response_client_id or order.get("client_order_id")
        fill_ts = self._parse_timestamp(self._coerce_value(response, "filled_at") or self._coerce_value(response, "updated_at"))
        created_at = self._parse_timestamp(
            self._coerce_value(response, "submitted_at")
            or self._coerce_value(response, "created_at")
            or self._coerce_value(response, "updated_at")
            or order.get("created_at")
        )
        return {
            "client_order_id": client_order_id,
            "status": status,
            "broker_order_id": broker_order_id,
            "symbol": symbol,
            "asset_class": asset_class,
            "side": side,
            "qty": float(qty_raw) if qty_raw is not None else None,
            "order_type": order_type,
            "created_at": created_at,
            "fill_qty": float(filled_qty) if filled_qty is not None else None,
            "fill_price": float(filled_avg_price) if filled_avg_price is not None else None,
            "fill_ts": fill_ts,
            "rejection_reason": rejection_reason,
        }

    def _map_status(self, status: str) -> str:
        """Map Alpaca status strings to canonical values."""
        return _ALPACA_STATUS_MAP.get(status.lower(), "error") if status else "error"

    def _coerce_value(self, source: object, key: str) -> object | None:
        """Read a value from response objects or mappings."""
        if source is None:
            return None
        if isinstance(source, Mapping):
            return source.get(key)
        if hasattr(source, key):
            return getattr(source, key)
        return None

    def _coerce_enumish(self, value: object | None) -> str | None:
        """Convert Alpaca enum-like objects into lowercase strings."""
        if value is None:
            return None
        raw = getattr(value, "value", value)
        text = str(raw).strip()
        return text.lower() if text else None

    def _parse_timestamp(self, value: object | None) -> datetime | None:
        """Normalize response timestamps into timezone-aware datetimes."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def _find_existing_order(self, client_order_id: str) -> Mapping[str, object] | None:
        """Return the most recent order event for client_order_id."""
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
        """Fetch the latest broker status for an existing order."""
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
        """Load the latest order event per client_order_id."""
        connection = getattr(self._event_store, "connection", lambda: None)()
        if connection is None:
            return []
        query = (
            "SELECT client_order_id, run_id, cycle_id, symbol, side, qty, order_type, "
            "status, broker_order_id, created_at "
            "FROM order_events ORDER BY created_at DESC"
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
            client_order_id = row[0]
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
