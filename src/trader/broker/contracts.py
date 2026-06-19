"""Broker contracts and optional capability protocols."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable, Mapping, Protocol, Sequence, runtime_checkable


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
    """Broker capability for reading live account and position state.

    Runtime code checks this protocol before refreshing portfolio state from a
    broker. Implementations may return provider-native payloads, but callers
    expect stable account keys and position fields that can be normalized before
    persistence or safety validation.
    """

    def get_account(self) -> Mapping[str, object]:
        """Return the current broker account snapshot.

        Returns:
            Mapping with account-level values such as `cash`, `buying_power`,
            and `equity`. Values may be strings when supplied by a provider and
            should not include credentials or other secret material.
        """

    def get_positions(self) -> Sequence[Mapping[str, object]]:
        """Return the broker's current open positions.

        Returns:
            Position payloads containing at least enough symbol, quantity, asset
            class, and average-price data for runtime normalization. The method
            should not mutate local event-store state.
        """


@runtime_checkable
class OrderLookupBroker(Protocol):
    """Broker capability for reading order state from the venue.

    Startup recovery and reconciliation use this protocol when local append-only
    order events need to be compared with broker-side truth.
    """

    def list_orders(self, since_ts: datetime | None = None) -> Sequence[Mapping[str, object]]:
        """Return broker orders, optionally bounded by a lower timestamp.

        Args:
            since_ts: Earliest creation/update timestamp the caller cares about.
                Implementations may pass this through to the provider or filter
                locally when the provider lacks an exact option.

        Returns:
            Broker order payloads suitable for normalization into order events.
        """

    def get_order_by_id(self, broker_order_id: str) -> Mapping[str, object]:
        """Return a single broker order by its venue identifier.

        Args:
            broker_order_id: Provider-side order identifier, not the local
                deterministic `client_order_id`.

        Returns:
            Broker order payload suitable for reconciliation.
        """


@runtime_checkable
class OrderCancelBroker(Protocol):
    """Broker capability for sending explicit venue-side cancellation requests.

    Runtime safety and recovery code checks this protocol before attempting to
    mutate broker-side order state.
    """

    def cancel_order(self, broker_order_id: str) -> None:
        """Request cancellation of a single broker-side order.

        Args:
            broker_order_id: Provider-side order identifier to cancel.

        Raises:
            Exception: Implementations should surface provider errors so callers
                can log the failed safety action explicitly.
        """


@runtime_checkable
class OrderReconcileBroker(Protocol):
    """Broker capability for repairing append-only local history from venue state.

    Implementations compare broker-side order truth with local event history and
    append new lifecycle/fill events rather than rewriting existing rows.
    """

    def reconcile_orders(self, since_ts: datetime | None = None) -> Sequence[Mapping[str, object]]:
        """Append local order and fill events that reflect broker state.

        Args:
            since_ts: Optional lower bound for broker orders to inspect.

        Returns:
            Normalized broker responses that were reconciled. Implementations
            are expected to write append-only local events rather than update or
            delete prior lifecycle records.
        """
