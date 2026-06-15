"""Broker-sourced portfolio state mappers plus offline ledger helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any

from src.trading.risk import PortfolioContext, PortfolioPosition


@dataclass(frozen=True)
class StockExecution:
    """Applied stock execution in the offline portfolio ledger."""

    ticker: str
    quantity: float
    fill_price: float
    trade_date: date
    strategy_id: str
    trade_identity: str
    executed_at: datetime
    net_cash_effect: float


@dataclass(frozen=True)
class StockPosition:
    """Open stock position mapped from either local ledger or broker positions."""

    ticker: str
    quantity: float
    average_cost: float
    market_price: float
    market_value: float
    trade_identity: str
    strategy_id: str | None
    opened_at: datetime
    updated_at: datetime
    direction: str = "long"


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Unified account snapshot from either estimated or broker-reported margin fields."""

    as_of: datetime
    cash_balance: float
    account_equity: float
    net_liquidation_value: float
    buying_power: float
    excess_liquidity: float
    stock_market_value: float
    option_market_value: float
    stock_margin_requirement: float
    option_margin_requirement: float
    total_margin_requirement: float
    initial_margin_requirement: float
    maintenance_margin_requirement: float
    margin_model_profile: str
    margin_model_version: str
    margin_requirement_source: str
    day_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OptionPosition:
    """Open option strategy state overlayed on top of the broker stock account."""

    ticker: str
    quantity: int
    market_value: float
    trade_identity: str
    strategy_id: str | None
    option_strategy_type: str
    opened_at: datetime
    updated_at: datetime
    expiry: date
    max_loss: float
    margin_requirement: float
    buying_power_effect: float
    assignment_notional: float
    direction: str = "long"


class PortfolioLedger:
    """Retained offline ledger for replay or local simulation modes."""

    def __init__(
        self,
        *,
        starting_cash_balance: float,
        margin_model_profile: str = "estimated_fidelity_like_conservative_v1",
        margin_model_version: str = "v1",
        margin_requirement_source: str = "estimated",
    ) -> None:
        self.cash_balance = float(starting_cash_balance)
        self.margin_model_profile = margin_model_profile
        self.margin_model_version = margin_model_version
        self.margin_requirement_source = margin_requirement_source
        self.positions: dict[str, StockPosition] = {}

    def record_stock_execution(
        self,
        *,
        ticker: str,
        quantity: float,
        fill_price: float,
        trade_date: date,
        strategy_id: str,
        trade_identity: str,
        executed_at: datetime | None = None,
    ) -> StockExecution:
        executed_at = executed_at or datetime.combine(trade_date, time(13, 30), tzinfo=timezone.utc)
        net_cash_effect = -float(quantity) * float(fill_price)
        self.cash_balance += net_cash_effect
        current = self.positions.get(ticker)
        if current is None:
            opened_at = executed_at
            average_cost = float(fill_price)
            new_quantity = float(quantity)
        else:
            opened_at = current.opened_at
            new_quantity = current.quantity + float(quantity)
            average_cost = (
                ((current.quantity * current.average_cost) + (float(quantity) * float(fill_price))) / new_quantity
                if new_quantity > 0
                else 0.0
            )
        self.positions[ticker] = StockPosition(
            ticker=ticker,
            quantity=new_quantity,
            average_cost=average_cost,
            market_price=float(fill_price),
            market_value=new_quantity * float(fill_price),
            trade_identity=trade_identity,
            strategy_id=strategy_id,
            opened_at=opened_at,
            updated_at=executed_at,
            direction="long",
        )
        return StockExecution(
            ticker=ticker,
            quantity=float(quantity),
            fill_price=float(fill_price),
            trade_date=trade_date,
            strategy_id=strategy_id,
            trade_identity=trade_identity,
            executed_at=executed_at,
            net_cash_effect=net_cash_effect,
        )

    def build_snapshot(self, *, as_of: datetime) -> PortfolioSnapshot:
        stock_market_value = sum(position.market_value for position in self.positions.values())
        initial_margin_requirement = sum(_initial_margin_requirement(position) for position in self.positions.values())
        maintenance_margin_requirement = sum(_maintenance_margin_requirement(position) for position in self.positions.values())
        account_equity = self.cash_balance + stock_market_value
        buying_power = max(0.0, account_equity - initial_margin_requirement)
        excess_liquidity = max(0.0, account_equity - maintenance_margin_requirement)
        return PortfolioSnapshot(
            as_of=as_of,
            cash_balance=self.cash_balance,
            account_equity=account_equity,
            net_liquidation_value=account_equity,
            buying_power=buying_power,
            excess_liquidity=excess_liquidity,
            stock_market_value=stock_market_value,
            option_market_value=0.0,
            stock_margin_requirement=initial_margin_requirement,
            option_margin_requirement=0.0,
            total_margin_requirement=initial_margin_requirement,
            initial_margin_requirement=initial_margin_requirement,
            maintenance_margin_requirement=maintenance_margin_requirement,
            margin_model_profile=self.margin_model_profile,
            margin_model_version=self.margin_model_version,
            margin_requirement_source=self.margin_requirement_source,
            day_pnl=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            metadata_json={},
        )

    def build_portfolio_context(
        self,
        *,
        as_of: datetime,
        approved_core_tickers: tuple[str, ...] = (),
    ) -> PortfolioContext:
        return build_portfolio_context(
            snapshot=self.build_snapshot(as_of=as_of),
            positions=tuple(sorted(self.positions.values(), key=lambda item: item.ticker)),
            approved_core_tickers=approved_core_tickers,
        )


def build_portfolio_snapshot_from_account(account_payload: dict[str, Any], *, as_of: datetime) -> PortfolioSnapshot:
    account_equity = _to_float(account_payload.get("equity")) or 0.0
    last_equity = _to_float(account_payload.get("last_equity")) or account_equity
    initial_margin = _to_float(account_payload.get("initial_margin")) or 0.0
    maintenance_margin = _to_float(account_payload.get("maintenance_margin")) or 0.0
    stock_market_value = _to_float(account_payload.get("long_market_value")) or 0.0
    option_market_value = _to_float(account_payload.get("options_market_value")) or 0.0
    return PortfolioSnapshot(
        as_of=as_of,
        cash_balance=_to_float(account_payload.get("cash")) or 0.0,
        account_equity=account_equity,
        net_liquidation_value=_to_float(account_payload.get("portfolio_value")) or account_equity,
        buying_power=_to_float(account_payload.get("buying_power")) or 0.0,
        excess_liquidity=max(0.0, account_equity - maintenance_margin),
        stock_market_value=stock_market_value,
        option_market_value=option_market_value,
        stock_margin_requirement=initial_margin,
        option_margin_requirement=0.0,
        total_margin_requirement=initial_margin,
        initial_margin_requirement=initial_margin,
        maintenance_margin_requirement=maintenance_margin,
        margin_model_profile="alpaca_paper_account",
        margin_model_version="broker",
        margin_requirement_source="broker_reported",
        day_pnl=round(account_equity - last_equity, 6),
        realized_pnl=_to_float(account_payload.get("realized_pl")) or 0.0,
        unrealized_pnl=_to_float(account_payload.get("unrealized_pl")) or 0.0,
        metadata_json={},
    )


def apply_option_overlay_to_snapshot(
    snapshot: PortfolioSnapshot,
    *,
    option_positions: tuple[OptionPosition, ...] = (),
) -> PortfolioSnapshot:
    if not option_positions:
        return snapshot
    option_market_value = sum(float(position.market_value) for position in option_positions)
    option_margin_requirement = sum(float(position.margin_requirement) for position in option_positions)
    option_buying_power_effect = sum(float(position.buying_power_effect) for position in option_positions)
    maintenance_margin_requirement = snapshot.maintenance_margin_requirement + option_margin_requirement
    initial_margin_requirement = snapshot.initial_margin_requirement + option_margin_requirement
    return PortfolioSnapshot(
        as_of=snapshot.as_of,
        cash_balance=snapshot.cash_balance,
        account_equity=snapshot.account_equity,
        net_liquidation_value=snapshot.net_liquidation_value,
        buying_power=max(0.0, snapshot.buying_power - option_buying_power_effect),
        excess_liquidity=max(0.0, snapshot.account_equity - maintenance_margin_requirement),
        stock_market_value=snapshot.stock_market_value,
        option_market_value=snapshot.option_market_value + option_market_value,
        stock_margin_requirement=snapshot.stock_margin_requirement,
        option_margin_requirement=snapshot.option_margin_requirement + option_margin_requirement,
        total_margin_requirement=snapshot.total_margin_requirement + option_margin_requirement,
        initial_margin_requirement=initial_margin_requirement,
        maintenance_margin_requirement=maintenance_margin_requirement,
        margin_model_profile=snapshot.margin_model_profile,
        margin_model_version=snapshot.margin_model_version,
        margin_requirement_source="broker_plus_local_option_overlay",
        day_pnl=snapshot.day_pnl,
        realized_pnl=snapshot.realized_pnl,
        unrealized_pnl=snapshot.unrealized_pnl,
        metadata_json={
            **dict(snapshot.metadata_json),
            "stock_margin_requirement_source": "broker_reported",
            "option_overlay_source": "local_simulation",
            "option_overlay_position_count": len(option_positions),
        },
    )


def build_positions_from_broker(
    *,
    broker_positions: list[dict[str, Any]],
    as_of: datetime,
    local_position_metadata: dict[str, dict[str, Any]] | None = None,
) -> tuple[StockPosition, ...]:
    metadata = {ticker.upper(): values for ticker, values in (local_position_metadata or {}).items()}
    positions: list[StockPosition] = []
    for payload in broker_positions:
        ticker = str(payload.get("symbol", "")).upper()
        if not ticker:
            continue
        position_metadata = metadata.get(ticker, {})
        positions.append(
            StockPosition(
                ticker=ticker,
                quantity=_to_float(payload.get("qty")) or 0.0,
                average_cost=_to_float(payload.get("avg_entry_price")) or 0.0,
                market_price=_to_float(payload.get("current_price")) or 0.0,
                market_value=_to_float(payload.get("market_value")) or 0.0,
                trade_identity=str(position_metadata.get("trade_identity", "tactical_stock_trade")),
                strategy_id=_string_or_none(position_metadata.get("strategy_id")),
                opened_at=as_of,
                updated_at=as_of,
                direction=str(payload.get("side", "long")).lower() or "long",
            )
        )
    return tuple(sorted(positions, key=lambda item: item.ticker))


def build_portfolio_context(
    *,
    snapshot: PortfolioSnapshot,
    positions: tuple[StockPosition, ...],
    option_positions: tuple[OptionPosition, ...] = (),
    approved_core_tickers: tuple[str, ...] = (),
) -> PortfolioContext:
    stock_positions = tuple(
        PortfolioPosition(
            ticker=position.ticker,
            quantity=position.quantity,
            market_value=position.market_value,
            notional_exposure=position.market_value,
            trade_identity=position.trade_identity,
            direction=position.direction,
            sector=None,
            strategy_id=position.strategy_id,
            intended_horizon=None,
            beta_bucket=None,
            volatility_bucket=None,
            liquidity_bucket=None,
            event_type=None,
            macro_sensitivity=None,
            margin_requirement=_initial_margin_requirement(position),
        )
        for position in positions
    )
    option_portfolio_positions = tuple(
        PortfolioPosition(
            ticker=position.ticker,
            quantity=float(position.quantity),
            market_value=position.market_value,
            notional_exposure=position.market_value,
            trade_identity=position.trade_identity,
            direction=position.direction,
            sector=None,
            strategy_id=position.strategy_id,
            intended_horizon=None,
            beta_bucket=None,
            volatility_bucket=None,
            liquidity_bucket=None,
            event_type="earnings_through_expiry",
            macro_sensitivity=None,
            margin_requirement=position.margin_requirement,
            option_margin_requirement=position.margin_requirement,
            assignment_notional=position.assignment_notional,
        )
        for position in option_positions
    )
    return PortfolioContext(
        as_of=snapshot.as_of,
        account_equity=snapshot.account_equity,
        cash_balance=snapshot.cash_balance,
        buying_power=snapshot.buying_power,
        excess_liquidity=snapshot.excess_liquidity,
        positions=stock_positions + option_portfolio_positions,
        open_strategy_exposure={},
        current_factor_exposure=(),
        stock_margin_requirement=snapshot.stock_margin_requirement,
        option_margin_requirement=snapshot.option_margin_requirement,
        total_margin_requirement=snapshot.total_margin_requirement,
        initial_margin_requirement=snapshot.initial_margin_requirement,
        maintenance_margin_requirement=snapshot.maintenance_margin_requirement,
        approved_core_tickers=approved_core_tickers,
        margin_model_profile=snapshot.margin_model_profile,
        margin_model_version=snapshot.margin_model_version,
        margin_requirement_source=snapshot.margin_requirement_source,
        broker_reported_margin_requirement=snapshot.total_margin_requirement,
    )


def _initial_margin_requirement(position: StockPosition) -> float:
    if _requires_full_margin(position):
        return position.market_value
    return position.market_value * 0.50


def _maintenance_margin_requirement(position: StockPosition) -> float:
    if _requires_full_margin(position):
        return position.market_value
    return position.market_value * 0.30


def _requires_full_margin(position: StockPosition) -> bool:
    return position.market_price < 5.0


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)
