#!/usr/bin/env python3
"""Run the live preopen pipeline with smoke-only overrides and submit one tiny paper order."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.prompt_registry import PromptRegistry
from src.core import config as app_config  # noqa: F401
from src.db.connection import SessionLocal
from src.db.models.trading import (
    ManualTickerRequest,
    PaperExecution,
    PaperOptionExecution,
    PaperOptionOrder,
    PaperOrder,
    TradingDecision,
)
from src.trading.runtime.preopen import LivePreopenRuntime, build_live_preopen_dependencies
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.workflows.strategy_scoring import StrategyPipelineResult
from src.trading.workflows.trading_decision import TradingDecisionPipeline


def run_smoke(
    *,
    ticker: str,
    instrument: str = "stock",
    execute_paper_orders: bool = True,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    now = as_of or datetime.now(timezone.utc)
    ticker = ticker.strip().upper()
    instrument = instrument.strip().lower()
    request_id = uuid.uuid4()
    reason = f"codex live preopen order smoke:{instrument}:{ticker}"

    with SessionLocal() as session:
        session.add(
            ManualTickerRequest(
                manual_ticker_request_id=request_id,
                ticker=ticker,
                reason=reason,
                mode="paper_trade_eligible",
                status="active",
                created_at=now,
                metadata_json={"smoke": True},
            )
        )
        session.commit()

        try:
            dependencies = build_live_preopen_dependencies(session)
            scoped_manual_requests = _ScopedManualRequestService(
                wrapped=dependencies.manual_request_loader,
                request_id=str(request_id),
            )
            dependencies.signal_pipeline.manual_request_service = scoped_manual_requests
            dependencies.strategy_pipeline.manual_request_service = scoped_manual_requests
            if dependencies.paper_execution_workflow is not None:
                dependencies.paper_execution_workflow.manual_request_service = scoped_manual_requests
            dependencies = replace(
                dependencies,
                manual_request_loader=scoped_manual_requests,
                strategy_pipeline=_SmokeStrategyPipeline(
                    wrapped=dependencies.strategy_pipeline,
                    target_ticker=ticker,
                    target_instrument=instrument,
                ),
                risk_workflow=_SmokeRiskWorkflow(
                    wrapped=dependencies.risk_workflow,
                    target_ticker=ticker,
                    target_instrument=instrument,
                ),
                trading_decision_pipeline=_build_smoke_trading_decision_pipeline(
                    repository=dependencies.trading_repository,
                    source_repository=getattr(dependencies.signal_pipeline, "source_repository", None),
                    manual_request_service=scoped_manual_requests,
                ),
            )
            result = LivePreopenRuntime(
                dependencies=dependencies,
                now=lambda: now,
                execute_paper_orders=execute_paper_orders,
                execute_paper_option_orders=execute_paper_orders and instrument == "option",
            ).run()
            session.commit()

            decision = (
                session.query(TradingDecision)
                .filter_by(manual_request_id=request_id)
                .order_by(TradingDecision.created_at.desc())
                .first()
            )
            order = None
            option_order = None
            execution = None
            option_execution = None
            if decision is not None:
                if decision.instrument_type == "option":
                    option_order = (
                        session.query(PaperOptionOrder)
                        .filter_by(trading_decision_id=decision.trading_decision_id)
                        .order_by(PaperOptionOrder.created_at.desc())
                        .first()
                    )
                    if option_order is not None:
                        option_execution = (
                            session.query(PaperOptionExecution)
                            .filter_by(paper_option_order_id=option_order.paper_option_order_id)
                            .order_by(PaperOptionExecution.executed_at.desc())
                            .first()
                        )
                else:
                    order = (
                        session.query(PaperOrder)
                        .filter_by(trading_decision_id=decision.trading_decision_id)
                        .order_by(PaperOrder.created_at.desc())
                        .first()
                    )
                    if order is not None:
                        execution = (
                            session.query(PaperExecution)
                            .filter_by(paper_order_id=order.paper_order_id)
                            .order_by(PaperExecution.executed_at.desc())
                            .first()
                        )
            status = _resolve_smoke_status(
                runtime=result,
                instrument=instrument,
                execute_paper_orders=execute_paper_orders,
                order=order,
                option_order=option_order,
            )
            return {
                "status": status,
                "ticker": ticker,
                "instrument": instrument,
                "as_of": now.isoformat(),
                "runtime": result,
                "decision": _decision_json(decision),
                "order": _paper_order_json(order),
                "option_order": _paper_option_order_json(option_order),
                "execution": _paper_execution_json(execution),
                "option_execution": _paper_option_execution_json(option_execution),
            }
        finally:
            session.rollback()
            row = session.query(ManualTickerRequest).filter_by(manual_ticker_request_id=request_id).one_or_none()
            if row is not None:
                row.status = "dismissed"
                row.dismissed_at = datetime.now(timezone.utc)
                session.commit()


class _SmokeStrategyPipeline:
    def __init__(self, *, wrapped: Any, target_ticker: str, target_instrument: str) -> None:
        self.wrapped = wrapped
        self.target_ticker = target_ticker
        self.target_instrument = target_instrument

    def run(self, *, snapshots: tuple[object, ...], decision_time: datetime) -> StrategyPipelineResult:
        result = self.wrapped.run(snapshots=snapshots, decision_time=decision_time)
        target_candidates = [
            candidate
            for candidate in result.candidates
            if candidate.ticker == self.target_ticker and candidate.direction == "bullish"
        ]
        if not target_candidates:
            return result
        base_candidate = max(target_candidates, key=lambda item: item.candidate_score)
        candidate = replace(
            base_candidate,
            strategy_id=f"lpsmoke_{base_candidate.decision_time.strftime('%H%M%S')}",
            strategy_definition_id="live-preopen-order-smoke-definition",
            action="enter_long",
            rejection_reason=None,
            candidate_status="actionable",
            strategy_source="smoke_override",
        )
        candidates = tuple(
            candidate if item.candidate_score_id == candidate.candidate_score_id else item
            for item in result.candidates
        )
        forced = TradeClassificationRecord(
            trade_classification_id=str(uuid.uuid4()),
            candidate_score_id=candidate.candidate_score_id,
            strategy_run_id=candidate.strategy_run_id,
            ticker=candidate.ticker,
            selected_strategy_id=candidate.strategy_id,
            selected_strategy_version=candidate.strategy_version,
            expression_bucket_id=(
                "defined_risk_directional_option"
                if self.target_instrument == "option"
                else "long_stock"
            ),
            expression_bucket_version="v1",
            trade_identity=(
                "tactical_option_trade"
                if self.target_instrument == "option"
                else "tactical_stock_trade"
            ),
            watch_type=None,
            direction=candidate.direction,
            intended_horizon=candidate.typical_horizon,
            exit_policy="strategy_invalidators_or_target_horizon",
            result_status="actionable_trade",
            classification_reason="smoke_force_actionable_trade_for_execution_path_verification",
            selected_strategy_context_json={
                "candidate_score_id": candidate.candidate_score_id,
                "candidate_score": candidate.candidate_score,
                "strategy_id": candidate.strategy_id,
                "strategy_version": candidate.strategy_version,
                "rejection_reason": candidate.rejection_reason,
                "selection_reason": candidate.selection_reason,
                "benchmark_context": candidate.benchmark_context,
                "smoke_override": True,
                "selected_expression_bucket_id": (
                    "defined_risk_directional_option"
                    if self.target_instrument == "option"
                    else "long_stock"
                ),
                "fallback_expression_bucket_ids": [],
            },
            decision_time=candidate.decision_time,
        )
        classifications = tuple(
            classification
            for classification in result.classifications
            if classification.ticker != self.target_ticker
        ) + (forced,)
        if hasattr(self.wrapped, "repository"):
            self.wrapped.repository.save_trade_classifications((forced,))
        return StrategyPipelineResult(
            strategy_run=result.strategy_run,
            candidates=candidates,
            selected_trades=result.selected_trades,
            watch_candidates=result.watch_candidates,
            classifications=classifications,
        )


def _build_smoke_trading_decision_pipeline(
    *,
    repository: Any,
    source_repository: Any,
    manual_request_service: Any,
) -> TradingDecisionPipeline:
    return TradingDecisionPipeline(
        repository=repository,
        source_repository=source_repository,
        prompt_registry=PromptRegistry.get_default(),
        manual_request_service=manual_request_service,
        model_name=app_config.TRADING_MODEL_NAME,
        agent_runner=_smoke_agent_runner,
    )


class _ScopedManualRequestService:
    def __init__(self, *, wrapped: Any, request_id: str) -> None:
        self.wrapped = wrapped
        self.request_id = request_id

    def load_active(self) -> tuple[object, ...]:
        return tuple(request for request in self.wrapped.load_active() if request.request_id == self.request_id)

    def record_evaluation(self, request_id: str, *, result_status: str, signal_snapshot_id: str | None) -> object:
        return self.wrapped.record_evaluation(
            request_id,
            result_status=result_status,
            signal_snapshot_id=signal_snapshot_id,
        )


class _SmokeRiskWorkflow:
    def __init__(self, *, wrapped: Any, target_ticker: str, target_instrument: str) -> None:
        self.wrapped = wrapped
        self.target_ticker = target_ticker
        self.target_instrument = target_instrument

    def run(
        self,
        *,
        candidates: tuple[object, ...],
        classifications: tuple[object, ...],
        portfolio_context: object,
        decision_time: datetime,
    ) -> object:
        result = self.wrapped.run(
            candidates=candidates,
            classifications=classifications,
            portfolio_context=portfolio_context,
            decision_time=decision_time,
        )
        normalized = []
        for decision in getattr(result, "risk_decisions", ()):
            if getattr(decision, "ticker", None) != self.target_ticker:
                normalized.append(decision)
                continue
            quantity = (
                max(1.0, float(int(round(float(decision.approved_quantity or 0.0))) or 1))
                if self.target_instrument == "option"
                else max(1.0, float(int(round(float(decision.approved_quantity or 0.0))) or 1))
            )
            fill_price = float(decision.approved_notional or 0.0) / float(decision.approved_quantity or 1.0)
            approved_notional = quantity * fill_price if fill_price > 0 else float(decision.approved_notional or 0.0)
            normalized.append(
                replace(
                    decision,
                    approved_quantity=quantity,
                    approved_notional=approved_notional,
                )
            )
        return SimpleNamespace(risk_decisions=tuple(normalized))


def _smoke_agent_runner(prompt: str, model_name: str) -> dict[str, Any]:
    del model_name
    payload = _extract_input_payload(prompt)
    candidate_context = dict(payload.get("candidate_context") or {})
    classification_context = dict(payload.get("classification_context") or {})
    manual_request_context = dict(payload.get("manual_request_context") or {})
    risk_context = dict(payload.get("risk_context") or {})
    strategy_id = str(payload.get("strategy_id") or candidate_context.get("strategy_id") or "")
    expression_bucket_id = str(
        payload.get("expression_bucket_id") or classification_context.get("expression_bucket_id") or ""
    )
    trade_identity = str(payload.get("trade_identity") or classification_context.get("trade_identity") or "")
    instrument_type = str(payload.get("instrument_type") or classification_context.get("instrument_type") or "")
    selection_source = str(payload.get("selection_source") or candidate_context.get("selection_source") or "")
    manual_request_id = payload.get("manual_request_id") or manual_request_context.get("manual_request_id")
    manual_request_mode = payload.get("manual_request_mode") or manual_request_context.get("manual_request_mode")
    candidate_score = float(payload.get("candidate_score") or candidate_context.get("candidate_score") or 0.0)
    benchmark_context = dict(payload.get("benchmark_context") or candidate_context.get("benchmark_context") or {})
    should_enter = (
        manual_request_mode == "paper_trade_eligible" and risk_context.get("status") == "approved"
    )
    should_enter_stock = should_enter and trade_identity == "tactical_stock_trade" and instrument_type == "stock"
    should_enter_option = should_enter and trade_identity == "tactical_option_trade"
    target_weight = float(risk_context.get("approved_weight") or 0.0)
    return {
        "content": {
            "ticker": payload["ticker"],
            "decision": (
                "open_option_strategy"
                if should_enter_option
                else ("enter_long" if should_enter_stock else "no_trade")
            ),
            "strategy_id": strategy_id,
            "expression_bucket_id": expression_bucket_id,
            "trade_identity": trade_identity,
            "instrument_type": "option" if should_enter_option else instrument_type,
            "selection_source": selection_source,
            "manual_request_id": manual_request_id,
            "confidence": candidate_score,
            "confidence_basis": {"smoke_mode": True},
            "benchmark_context": benchmark_context,
            "target_weight": target_weight if (should_enter_stock or should_enter_option) else 0.0,
            "max_loss_pct": 0.02 if (should_enter_stock or should_enter_option) else 0.0,
            "time_horizon": "1d-5d" if should_enter_stock else ("1w-4w" if should_enter_option else "monitor_only"),
            "entry_plan": (
                "market_open_fractional_buy"
                if should_enter_stock
                else ("open_defined_risk_option" if should_enter_option else "do_not_enter")
            ),
            "exit_plan": (
                "risk_manager_stop_or_manual_exit"
                if should_enter_stock
                else ("close_or_roll_before_event_risk" if should_enter_option else "no_position_to_exit")
            ),
            "thesis": (
                "Smoke override produced a minimal executable long decision."
                if should_enter_stock
                else (
                    "Smoke override produced a minimal executable option decision."
                    if should_enter_option
                    else "Smoke override preserved a no-trade outcome."
                )
            ),
            "key_signals": ["smoke_override"],
            "counterarguments": ["smoke_only"],
            "risk_checks": ["risk_status_approved"] if (should_enter_stock or should_enter_option) else ["no_trade_path"],
            "invalidators": ["smoke_only"],
            "learning_factors_used": [],
            "schema_version": "v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    }


def _extract_input_payload(prompt: str) -> dict[str, Any]:
    marker = "Input JSON:"
    if marker not in prompt:
        raise ValueError("smoke_prompt_missing_input_json")
    payload = prompt.split(marker, 1)[1].strip()
    left = payload.find("{")
    if left == -1:
        raise ValueError("smoke_prompt_missing_json_object")
    decoder = json.JSONDecoder()
    parsed, _end = decoder.raw_decode(payload[left:])
    if not isinstance(parsed, dict):
        raise ValueError("smoke_prompt_input_payload_is_not_object")
    return parsed


def _resolve_smoke_status(
    *,
    runtime: dict[str, Any],
    instrument: str,
    execute_paper_orders: bool,
    order: Any,
    option_order: Any,
) -> str:
    execution = dict(runtime.get("execution") or {})
    summary = dict(runtime.get("summary") or {})
    if execute_paper_orders:
        if instrument == "option":
            return (
                "passed"
                if execution.get("option_orders_submitted", 0) >= 1 and option_order is not None
                else "failed"
            )
        return "passed" if execution.get("orders_submitted", 0) >= 1 and order is not None else "failed"
    return (
        "passed"
        if int(summary.get("risk_decision_count", 0)) >= 1 and int(summary.get("trading_decision_count", 0)) >= 1
        else "failed"
    )


def _decision_json(decision: Any) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "trading_decision_id": str(decision.trading_decision_id),
        "ticker": decision.ticker,
        "decision": decision.decision,
        "trade_identity": decision.trade_identity,
        "instrument_type": decision.instrument_type,
        "manual_request_id": str(decision.manual_request_id) if decision.manual_request_id is not None else None,
    }


def _paper_order_json(order: Any) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "paper_order_id": str(order.paper_order_id),
        "broker_order_id": str(order.broker_order_id) if order.broker_order_id is not None else None,
        "client_order_id": order.client_order_id,
        "ticker": order.ticker,
        "status": order.status,
        "quantity": float(order.quantity),
        "rejection_reason": order.rejection_reason,
    }


def _paper_execution_json(execution: Any) -> dict[str, Any] | None:
    if execution is None:
        return None
    return {
        "paper_execution_id": str(execution.paper_execution_id),
        "broker_order_id": str(execution.broker_order_id) if execution.broker_order_id is not None else None,
        "ticker": execution.ticker,
        "quantity": float(execution.quantity),
        "fill_price": float(execution.fill_price),
        "executed_at": execution.executed_at.isoformat(),
    }


def _paper_option_order_json(order: Any) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "paper_option_order_id": str(order.paper_option_order_id),
        "broker_order_id": str(order.broker_order_id) if order.broker_order_id is not None else None,
        "client_order_id": order.client_order_id,
        "ticker": order.ticker,
        "status": order.status,
        "quantity": int(order.quantity),
        "option_strategy_type": order.option_strategy_type,
        "rejection_reason": order.rejection_reason,
    }


def _paper_option_execution_json(execution: Any) -> dict[str, Any] | None:
    if execution is None:
        return None
    return {
        "paper_option_execution_id": str(execution.paper_option_execution_id),
        "broker_order_id": str(execution.broker_order_id) if execution.broker_order_id is not None else None,
        "ticker": execution.ticker,
        "quantity": int(execution.quantity),
        "fill_price": float(execution.fill_price),
        "executed_at": execution.executed_at.isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="NVDA")
    parser.add_argument("--instrument", choices=("stock", "option"), default="stock")
    parser.add_argument("--env-file", help="Optional dotenv file to load before constructing live dependencies.")
    parser.add_argument("--dry-run", action="store_true", help="Run the smoke without actually submitting paper orders.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.env_file:
        load_dotenv(args.env_file)

    report = run_smoke(
        ticker=args.ticker,
        instrument=args.instrument,
        execute_paper_orders=not args.dry_run,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
