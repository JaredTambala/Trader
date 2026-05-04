"""Broker interface for order execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import import_module
import logging
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, cast, runtime_checkable

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

_ClientFactory = Any
_EnumFactory = Any
_RequestFactory = Any


def _coerce_float(value: object | None, *, default: float = 0.0) -> float:
    """Best-effort float coercion for loosely typed order payloads."""
    if value is None:
        return default
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return default


class Broker(ABC):
    """Submits orders to a trading venue or paper broker.

    Broker responses should use canonical fields when available:
    client_order_id, status, broker_order_id, symbol, asset_class, side, qty,
    order_type, created_at, fill_qty, fill_price, fill_ts, and rejection_reason.
    """

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


@runtime_checkable
class AccountBroker(Protocol):
    """Optional broker capability for remote account and position refreshes."""

    def get_account(self) -> Mapping[str, object]:
        """Return account fields such as cash, buying_power, and equity."""

    def get_positions(self) -> Sequence[Mapping[str, object]]:
        """Return normalized or broker-native open positions."""


@runtime_checkable
class OrderLookupBroker(Protocol):
    """Optional broker capability for remote order reads."""

    def list_orders(self, since_ts: datetime | None = None) -> Sequence[Mapping[str, object]]:
        """Return broker orders, optionally bounded by timestamp."""

    def get_order_by_id(self, broker_order_id: str) -> Mapping[str, object]:
        """Return one broker order by broker ID."""


@runtime_checkable
class OrderCancelBroker(Protocol):
    """Optional broker capability for order cancellation."""

    def cancel_order(self, broker_order_id: str) -> None:
        """Cancel one broker-side order."""


@runtime_checkable
class OrderReconcileBroker(Protocol):
    """Optional broker capability for append-only local reconciliation."""

    def reconcile_orders(self, since_ts: datetime | None = None) -> Sequence[Mapping[str, object]]:
        """Append local order/fill events that reflect broker state."""


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
        slippage_bps: float = 0.0,
        fee_fixed_per_order: float = 0.0,
        fee_bps: float = 0.0,
        fee_minimum: float = 0.0,
        sleep_on_fill_delay: bool = True,
        rng_seed: int | None = None,
    ) -> None:
        """Initialize the instance."""
        self._logger = logging.getLogger(__name__)
        self._reject_probability = max(0.0, min(float(reject_probability), 1.0))
        self._fill_delay_ms_mean = max(0.0, float(fill_delay_ms_mean))
        self._fill_delay_ms_stddev = max(0.0, float(fill_delay_ms_stddev))
        self._fill_qty_fraction_mean = max(0.0, float(fill_qty_fraction_mean))
        self._fill_qty_fraction_stddev = max(0.0, float(fill_qty_fraction_stddev))
        self._slippage_bps = max(0.0, float(slippage_bps))
        self._fee_fixed_per_order = max(0.0, float(fee_fixed_per_order))
        self._fee_bps = max(0.0, float(fee_bps))
        self._fee_minimum = max(0.0, float(fee_minimum))
        self._sleep_on_fill_delay = bool(sleep_on_fill_delay)
        self._rng = random.Random(rng_seed)

    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Submit orders to the broker backend."""
        responses: list[Mapping[str, object]] = []
        timestamp = datetime.now(timezone.utc)
        for order in orders:
            symbol = str(order.get("symbol", "")).strip().upper()
            side = str(order.get("side", "")).lower().strip()
            qty = _coerce_float(order.get("qty", 0.0))
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
            if delay_ms and self._sleep_on_fill_delay:
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
            raw_fill_price = _coerce_float(price, default=0.0) if price is not None else None
            base_fill_ts = order.get("created_at")
            if not isinstance(base_fill_ts, datetime):
                base_fill_ts = timestamp
            fill_ts = base_fill_ts + timedelta(milliseconds=delay_ms, microseconds=3)
            fill_price = raw_fill_price
            slippage_amount = 0.0
            fee_amount = 0.0
            if raw_fill_price is None:
                self._logger.warning("Missing price for order; fill skipped symbol=%s", symbol)
            else:
                if side == "buy":
                    fill_price = raw_fill_price * (1.0 + (self._slippage_bps / 10_000.0))
                else:
                    fill_price = raw_fill_price * (1.0 - (self._slippage_bps / 10_000.0))
                slippage_amount = abs(fill_price - raw_fill_price) * fill_qty
                fee_amount = self._compute_fee_amount(fill_qty, fill_price)
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
                    "fill_ts": fill_ts,
                    "fill_qty": fill_qty if fill_price is not None else None,
                    "raw_fill_price": raw_fill_price,
                    "fill_price": fill_price,
                    "slippage_amount": slippage_amount,
                    "fee_amount": fee_amount,
                }
            )
        return responses

    def _compute_fee_amount(self, fill_qty: float, fill_price: float) -> float:
        """Compute deterministic fees for a single fill."""
        bps_fee = abs(fill_qty * fill_price) * (self._fee_bps / 10_000.0)
        fee = self._fee_fixed_per_order + bps_fee
        if fee <= 0.0 and self._fee_minimum <= 0.0:
            return 0.0
        return max(self._fee_minimum, fee)


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
        """Fetch open positions from Alpaca."""
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
        """Submit orders to Alpaca with idempotency checks."""
        responses: list[Mapping[str, object]] = []
        for order in orders:
            enriched = self._ensure_client_order_id(order)
            client_order_id = str(enriched["client_order_id"])
            existing = self._find_existing_order(client_order_id)
            if existing is not None and existing.get("status") in _ALREADY_SUBMITTED_STATUSES:
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
        orders = cast(Sequence[object], self._with_retries(getter, **kwargs))
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
                            "fill_qty": _coerce_float(fill_qty),
                            "raw_fill_price": _coerce_float(fill_price),
                            "fill_price": _coerce_float(fill_price),
                            "slippage_amount": None,
                            "fee_amount": None,
                        },
                    )
        return updates

    def _with_retries(
        self,
        func: Callable[..., object],
        *args: object,
        **kwargs: object,
    ) -> object:
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
        qty = _coerce_float(order.get("qty", 0.0))
        client_order_id = deterministic_client_order_id(cycle_id, symbol, side, qty)
        return {**order, "client_order_id": client_order_id}

    def _build_order_request(self, order: Mapping[str, object]) -> object:
        """Build an Alpaca order request payload."""
        symbol = str(order.get("symbol", "")).strip().upper()
        side = str(order.get("side", "")).lower().strip()
        qty = _coerce_float(order.get("qty", 0.0))
        tif = str(order.get("time_in_force", "day")).lower()
        asset_class = str(order.get("asset_class", "")).lower()
        if asset_class in {"crypto", "cryptocurrency"} and "/" in symbol:
            # Alpaca trading endpoints commonly use "BTCUSD" while market data uses "BTC/USD".
            symbol = symbol.replace("/", "")
        if asset_class in {"crypto", "cryptocurrency"} and tif in {"day", "daytime"}:
            tif = "gtc"
        order_type = str(order.get("order_type", "market")).lower()
        client_order_id = str(order.get("client_order_id", ""))
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
            side_enum = order_side.BUY if side == "buy" else order_side.SELL
            if tif in {"day", "daytime"}:
                tif_enum = time_in_force.DAY
            elif tif in {"ioc", "immediate_or_cancel"} and hasattr(time_in_force, "IOC"):
                tif_enum = time_in_force.IOC
            else:
                tif_enum = time_in_force.GTC
            if order_type == "limit":
                limit_price = _coerce_float(order.get("limit_price") or order.get("price"))
                return limit_order_request(
                    symbol=symbol,
                    qty=qty,
                    side=side_enum,
                    time_in_force=tif_enum,
                    limit_price=limit_price,
                    client_order_id=client_order_id,
                )
            return market_order_request(
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
            "qty": _coerce_float(qty_raw, default=0.0) if qty_raw is not None else None,
            "order_type": order_type,
            "created_at": created_at,
            "fill_qty": _coerce_float(filled_qty, default=0.0) if filled_qty is not None else None,
            "fill_price": (
                _coerce_float(filled_avg_price, default=0.0)
                if filled_avg_price is not None
                else None
            ),
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
