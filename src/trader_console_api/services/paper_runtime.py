"""Application service for the read-only paper operations projection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from ..contracts import (
    ConsoleScope,
    PaperDataFreshness,
    PaperFill,
    PaperFills,
    PaperFreshnessItem,
    PaperHaltState,
    PaperIncident,
    PaperOpenOrder,
    PaperOrders,
    PaperPortfolio,
    PaperPosition,
    PaperReconciliation,
    PaperRiskOutcomes,
    PaperRuntimeHealth,
    PaperRuntimeOperations,
    PaperRuntimeSession,
    RuntimeEvidence,
    RuntimeEvidenceStatus,
)
from ..repositories.database import ConsoleDatabaseUnavailable
from ..repositories.paper_runtime import PaperRuntimeRepository

PaperRuntimeDatabaseUnavailable = ConsoleDatabaseUnavailable
_OPEN_ORDER_STATUSES = {"submitted", "accepted", "partially_filled", "error"}


class PaperRuntimeService:
    """Normalize published runtime rows without inferring broker truth."""

    def __init__(self, repository: PaperRuntimeRepository, scope: ConsoleScope, *, stale_after_seconds: int = 300) -> None:
        """Bind the read adapter to one server-owned scope."""
        self._repository = repository
        self._scope = scope
        self._stale_after_seconds = stale_after_seconds

    async def operations(self, *, now: datetime | None = None) -> PaperRuntimeOperations:
        """Return the complete read-only paper operations projection."""
        generated_at = _utc(now or datetime.now(timezone.utc))
        if self._scope.environment.value != "paper":
            return _out_of_scope(self._scope, generated_at)
        raw = await self._repository.snapshot(stale_after_seconds=self._stale_after_seconds)
        session_row = raw.get("session")
        session = _session(session_row)
        freshness = _freshness(raw.get("freshness", ()), generated_at, self._stale_after_seconds, session_row)
        portfolio = _portfolio(raw.get("positions", ()))
        orders = _orders(raw.get("orders", ()), generated_at, self._stale_after_seconds)
        fills = _fills(raw.get("fills", ()))
        risk = _risk(raw.get("risk", ()))
        health, incidents = _health(session, freshness, orders, generated_at)
        return PaperRuntimeOperations(
            scope_id=self._scope.scope_id,
            generated_at=generated_at,
            broker_account_binding=self._scope.broker_account_binding,
            broker_account_display_label=self._scope.broker_account_display_label,
            broker_identity_verified=False,
            session=session,
            health=health,
            data_freshness=freshness,
            portfolio=portfolio,
            open_orders=orders,
            fills=fills,
            risk=risk,
            reconciliation=PaperReconciliation(
                status="unavailable",
                message="No published reconciliation-attempt projection is available in this Console contract.",
                evidence=RuntimeEvidence(
                    status="unavailable", source="console_read.reconciliation", reason="projection_not_published"
                ),
            ),
            halt=PaperHaltState(
                evidence=RuntimeEvidence(
                    status="unavailable", source="console_read.halt", reason="projection_not_published"
                )
            ),
            incidents=incidents,
        )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _out_of_scope(scope: ConsoleScope, generated_at: datetime) -> PaperRuntimeOperations:
    """Return a truthful empty projection for backtest/demo scopes."""
    evidence = _status("out_of_scope", "console.scope", reason="paper_runtime_requires_paper_scope")
    return PaperRuntimeOperations(
        scope_id=scope.scope_id,
        generated_at=generated_at,
        broker_account_binding=scope.broker_account_binding,
        broker_account_display_label=scope.broker_account_display_label,
        session=PaperRuntimeSession(evidence=evidence),
        health=PaperRuntimeHealth(status="unavailable", checked_at=generated_at, evidence=evidence),
        data_freshness=PaperDataFreshness(status="out_of_scope", checked_at=generated_at, evidence=evidence),
        portfolio=PaperPortfolio(evidence=evidence),
        open_orders=PaperOrders(evidence=evidence),
        fills=PaperFills(evidence=evidence),
        risk=PaperRiskOutcomes(evidence=evidence),
        reconciliation=PaperReconciliation(status="unavailable", evidence=evidence),
        halt=PaperHaltState(evidence=evidence),
    )


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if value is None:
        return None
    try:
        return _utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _symbols(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value if item is not None)


def _status(status: str, source: str, *, observed_at: datetime | None = None, reason: str | None = None) -> RuntimeEvidence:
    return RuntimeEvidence(status=status, source=source, observed_at=observed_at, reason=reason)  # type: ignore[arg-type]


def _session(row: dict[str, Any] | None) -> PaperRuntimeSession:
    if not row:
        return PaperRuntimeSession(evidence=_status("unavailable", "console_read.sessions", reason="no_session"))
    observed = _dt(row.get("started_at"))
    return PaperRuntimeSession(
        session_id=row.get("session_id"),
        strategy_id=row.get("strategy_id"),
        status=row.get("status"),
        mode=row.get("mode"),
        symbols=_symbols(row.get("symbols")),
        timeframe=row.get("timeframe"),
        started_at=observed,
        finished_at=_dt(row.get("finished_at")),
        error_message=row.get("error_message"),
        evidence=_status("available", "console_read.sessions", observed_at=observed),
    )


def _freshness(rows: Any, now: datetime, stale_after: int, session: dict[str, Any] | None) -> PaperDataFreshness:
    session_symbols = set(_symbols(session.get("symbols"))) if session else set()
    session_timeframe = session.get("timeframe") if session else None
    selected = [
        row for row in rows
        if (not session_symbols or str(row.get("symbol")) in session_symbols)
        and (not session_timeframe or row.get("timeframe") == session_timeframe)
    ]
    items: list[PaperFreshnessItem] = []
    stale_count = 0
    for row in selected:
        latest = _dt(row.get("latest_ts"))
        age = (now - latest).total_seconds() if latest else None
        stale = age is None or age > stale_after
        stale_count += int(stale)
        items.append(PaperFreshnessItem(asset_class=row["asset_class"], symbol=str(row["symbol"]), timeframe=str(row["timeframe"]), latest_ts=latest, age_seconds=age, stale=stale))
    missing_count = len(session_symbols - {item.symbol for item in items}) if session_symbols else 0
    status: RuntimeEvidenceStatus = "unavailable" if not rows else "stale" if stale_count or missing_count else "available"
    return PaperDataFreshness(
        status=status,
        items=tuple(items),
        stale_count=stale_count,
        missing_count=missing_count,
        checked_at=now,
        evidence=_status(status, "console_read.stock_bars+crypto_bars", observed_at=max((item.latest_ts for item in items if item.latest_ts), default=None), reason="missing_or_stale_stream" if status == "stale" else None),
    )


def _portfolio(rows: Any) -> PaperPortfolio:
    positions = tuple(PaperPosition(symbol=str(row["symbol"]), qty=float(row.get("qty") or 0), avg_price=row.get("avg_price"), asof_ts=_dt(row.get("asof_ts"))) for row in rows)
    asof = max((position.asof_ts for position in positions if position.asof_ts), default=None)
    cash = float(rows[0].get("cash_balance")) if rows and rows[0].get("cash_balance") is not None else None
    status: RuntimeEvidenceStatus = "available" if rows else "unavailable"
    return PaperPortfolio(cash=cash, asof_ts=asof, positions=positions, evidence=_status(status, "console_read.positions", observed_at=asof, reason="no_position_snapshot" if not rows else None))


def _orders(rows: Any, now: datetime, stale_after: int) -> PaperOrders:
    items: list[PaperOpenOrder] = []
    stale_count = 0
    for row in rows:
        if str(row.get("status", "")).lower() not in _OPEN_ORDER_STATUSES:
            continue
        created = _dt(row.get("created_at"))
        if created and (now - created).total_seconds() > stale_after:
            stale_count += 1
        items.append(PaperOpenOrder(client_order_id=str(row["client_order_id"]), broker_order_id=row.get("broker_order_id"), symbol=row.get("symbol"), side=row.get("side"), qty=row.get("qty"), order_type=row.get("order_type"), status=str(row["status"]), created_at=created, rejection_reason=row.get("rejection_reason")))
    status: RuntimeEvidenceStatus = "stale" if stale_count else "available"
    return PaperOrders(items=tuple(items), stale_count=stale_count, evidence=_status(status, "console_read.orders", reason="stale_open_order" if stale_count else None))


def _fills(rows: Any) -> PaperFills:
    items = tuple(PaperFill(client_order_id=row.get("client_order_id"), fill_ts=_dt(row.get("fill_ts")), fill_qty=row.get("fill_qty"), fill_price=row.get("fill_price"), fee_amount=row.get("fee_amount"), slippage_amount=row.get("slippage_amount")) for row in rows)
    return PaperFills(items=items, evidence=_status("available" if items else "partial", "console_read.fills", reason="no_fills_in_bounded_window" if not items else None))


def _risk(rows: Any) -> PaperRiskOutcomes:
    counts = {str(row.get("outcome")): int(row.get("count") or 0) for row in rows}
    total = sum(counts.values())
    return PaperRiskOutcomes(evaluated_count=total, approved_count=counts.get("approved", 0), transformed_count=counts.get("transformed", 0), rejected_count=counts.get("rejected", 0), blocked_count=counts.get("blocked", 0), evidence=_status("available" if rows else "unavailable", "console_read.risk_decisions", reason="no_session_risk_evidence" if not rows else None))


def _health(session: PaperRuntimeSession, freshness: PaperDataFreshness, orders: PaperOrders, now: datetime) -> tuple[PaperRuntimeHealth, tuple[PaperIncident, ...]]:
    reasons: list[str] = []
    incidents: list[PaperIncident] = []
    if session.session_id is None:
        reasons.append("no_session")
        incidents.append(PaperIncident(code="no_session", severity="error", message="No paper trading session is published.", observed_at=now))
    if str(session.status).lower() == "failed":
        reasons.append("session_failed")
        incidents.append(PaperIncident(code="session_failed", severity="error", message=session.error_message or "The latest paper session failed.", observed_at=session.finished_at))
    if freshness.status == "unavailable":
        reasons.append("data_unavailable")
    elif freshness.status == "stale":
        reasons.append("data_stale")
        incidents.append(PaperIncident(code="data_stale", severity="error", message="One or more paper data streams are stale or missing.", observed_at=now))
    if orders.stale_count:
        reasons.append("stale_open_orders")
        incidents.append(PaperIncident(code="stale_open_orders", severity="warning", message="An open order exceeds the freshness threshold.", observed_at=now))
    status: Literal["healthy", "degraded", "unhealthy", "unavailable"] = (
        "unavailable" if not session.session_id and freshness.status == "unavailable"
        else "unhealthy" if "session_failed" in reasons or freshness.status == "stale"
        else "degraded" if reasons else "healthy"
    )
    evidence_status: RuntimeEvidenceStatus = "unavailable" if status == "unavailable" else "stale" if status == "unhealthy" else "partial" if status == "degraded" else "available"
    return PaperRuntimeHealth(status=status, reasons=tuple(reasons), checked_at=now, evidence=_status(evidence_status, "console_read.sessions+stock_bars+crypto_bars+orders", observed_at=now)), tuple(incidents)
