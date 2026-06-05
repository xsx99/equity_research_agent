"""Risk assembly helpers for the live preopen runtime."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any


class _LiveRiskWorkflow:
    def __init__(
        self,
        *,
        repository: Any,
        source_repository: Any,
        config_resolver: Any,
        position_sizer: Any,
        risk_manager: Any,
    ) -> None:
        self.repository = repository
        self.source_repository = source_repository
        self.config_resolver = config_resolver
        self.position_sizer = position_sizer
        self.risk_manager = risk_manager

    def run(
        self,
        *,
        candidates: tuple[object, ...],
        classifications: tuple[object, ...],
        portfolio_context: object,
        decision_time: datetime,
    ) -> object:
        from types import SimpleNamespace

        signal_by_id = {
            snapshot.signal_snapshot_id: snapshot
            for snapshot in self.repository.load_signal_snapshots_for_decision(
                decision_time=decision_time,
                snapshot_type="pre_open",
            )
        }
        config = self.config_resolver.resolve(
            risk_appetite="balanced",
            portfolio_context=portfolio_context,
            macro_risk_budget_multiplier=1.0,
        )
        portfolio_snapshot = self.risk_manager.build_portfolio_risk_snapshot(portfolio_context, config)
        exposures = self.risk_manager.compute_factor_exposures(portfolio_context)
        self.repository.save_portfolio_risk_snapshot(portfolio_snapshot)
        self.repository.save_risk_factor_exposures(exposures)
        candidate_by_id = {candidate.candidate_score_id: candidate for candidate in candidates}
        decisions: list[object] = []
        for classification in classifications:
            candidate = candidate_by_id.get(classification.candidate_score_id)
            if candidate is None:
                continue
            snapshot = signal_by_id.get(candidate.signal_snapshot_id)
            request = _build_trade_risk_request(
                candidate=candidate,
                classification=classification,
                snapshot=snapshot,
                source_repository=self.source_repository,
                decision_time=decision_time,
            )
            sizing = self.position_sizer.size_position(request, portfolio_context, config)
            decision = self.risk_manager.evaluate(request, sizing, portfolio_context, config)
            decision = replace(
                decision,
                portfolio_risk_snapshot_id=portfolio_snapshot.portfolio_risk_snapshot_id,
            )
            self.repository.save_position_sizing_decision(sizing)
            self.repository.save_risk_decision(decision)
            decisions.append(decision)
        return SimpleNamespace(risk_decisions=tuple(decisions))


def _build_trade_risk_request(
    *,
    candidate: Any,
    classification: Any,
    snapshot: Any,
    source_repository: Any,
    decision_time: datetime,
) -> Any:
    from src.trading.risk.context import TradeRiskRequest

    technical = dict(getattr(snapshot, "signal_json", {}).get("technical", {}))
    source_freshness = dict(getattr(snapshot, "source_freshness_json", {}))
    price = _latest_price_from_sources(
        source_repository=source_repository,
        ticker=candidate.ticker,
        decision_time=decision_time,
    )
    atr_pct = float(technical.get("atr_pct") or 0.0)
    average_daily_dollar_volume = float(technical.get("dollar_volume") or 0.0)
    return TradeRiskRequest(
        candidate=candidate,
        classification=classification,
        instrument_type="watch" if classification.trade_identity == "watch_only" else "stock",
        target_weight=min(max(float(candidate.candidate_score) * 0.05, 0.0), 0.10),
        confidence=min(max(float(candidate.candidate_score), 0.0), 1.0),
        sector=None,
        beta_bucket=None,
        volatility_bucket="high" if atr_pct >= 0.05 else "medium",
        liquidity_bucket="thin"
        if average_daily_dollar_volume and average_daily_dollar_volume < 25_000_000
        else "liquid",
        event_type=None,
        macro_sensitivity=None,
        price=price,
        atr_pct=atr_pct,
        average_daily_dollar_volume=average_daily_dollar_volume,
        signal_freshness=source_freshness,
        estimated_margin_requirement=max(price, 1.0),
        estimated_buying_power_effect=max(price, 1.0),
        estimated_initial_margin_requirement=max(price, 1.0),
        estimated_maintenance_margin_requirement=max(price * 0.5, 1.0),
    )


def _latest_price_from_sources(*, source_repository: Any, ticker: str, decision_time: datetime) -> float:
    technical_rows = source_repository.latest_available_by_family(ticker, "technical", decision_time)
    if not technical_rows:
        return 1.0
    bars = list((technical_rows[-1].payload or {}).get("bars") or [])
    if not bars:
        return 1.0
    last_bar = bars[-1]
    close = last_bar.get("close")
    if isinstance(close, (int, float)) and close > 0:
        return float(close)
    return 1.0
