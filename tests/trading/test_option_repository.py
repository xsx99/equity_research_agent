from __future__ import annotations

from datetime import date, datetime, timezone

from src.trading.brokers.paper_option import PaperOptionExecutionRecord, PaperOptionOrderRecord, PaperOptionPosition
from src.trading.risk.hedges import RiskHedgeDecisionRecord
from src.trading.risk.options import OptionRiskSnapshotRecord
from src.trading.options.strategy import OptionStrategyDecisionRecord, OptionStrategyLegRecord
from src.trading.repositories.in_memory import InMemoryTradingRepository


def test_in_memory_repository_persists_option_artifacts():
    repository = InMemoryTradingRepository()
    now = datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc)

    repository.save_option_strategy_decision(
        OptionStrategyDecisionRecord(
            option_strategy_decision_id="option-decision-1",
            trading_decision_id="decision-1",
            ticker="NVDA",
            trade_identity="tactical_option_trade",
            decision_action="open_option_strategy",
            option_strategy_type="put_credit_spread",
            status="ready",
            rejection_reason=None,
            strategy_id="earnings_drift_v1",
            strategy_version="v1",
            expression_bucket_id="defined_risk_income_spread",
            expression_bucket_version="v1",
            underlying_price=118.0,
            expiry=date(2026, 7, 17),
            net_debit_or_credit=-1.5,
            max_loss=500.0,
            max_profit=150.0,
            breakevens=(108.5,),
            margin_requirement=500.0,
            buying_power_effect=500.0,
            assignment_notional=11_000.0,
            portfolio_delta=-0.11,
            portfolio_gamma=0.01,
            portfolio_theta=0.01,
            portfolio_vega=-0.03,
            earnings_date=date(2026, 6, 20),
            event_through_expiry=True,
            strategy_pairing_method="vertical_by_expiry_and_width",
            assignment_plan="close_or_roll_before_expiry_if_itm",
            margin_model_profile="estimated_fidelity_like_conservative_v1",
            margin_model_version="v1",
            margin_requirement_source="simulated_formula",
            profit_target_pct=0.5,
            max_loss_rule="close_at_2x_credit",
            roll_conditions=("7_dte_if_otm",),
            close_conditions=("take_profit_50pct",),
            metadata_json={},
            created_at=now,
        )
    )
    repository.save_option_strategy_legs(
        (
            OptionStrategyLegRecord(
                option_strategy_leg_id="leg-1",
                option_strategy_decision_id="option-decision-1",
                ticker="NVDA",
                option_type="put",
                side="sell",
                quantity=1,
                strike=110.0,
                expiry=date(2026, 7, 17),
                dte=45,
                delta=-0.28,
                gamma=0.02,
                theta=0.01,
                vega=-0.07,
                iv_rank=0.61,
                bid=1.4,
                ask=1.6,
                mid=1.5,
                chosen_price=1.5,
                created_at=now,
            ),
        )
    )
    repository.save_paper_option_order(
        PaperOptionOrderRecord(
            paper_option_order_id="option-order-1",
            trading_decision_id="decision-1",
            risk_decision_id="risk-1",
            option_strategy_decision_id="option-decision-1",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="put_credit_spread",
            action="open_option_strategy",
            trade_identity="tactical_option_trade",
            trade_date=date(2026, 6, 2),
            quantity=1,
            limit_price=-1.5,
            status="filled",
            rejection_reason=None,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            created_at=now,
        )
    )
    repository.save_paper_option_execution(
        PaperOptionExecutionRecord(
            paper_option_execution_id="option-execution-1",
            paper_option_order_id="option-order-1",
            ticker="NVDA",
            quantity=1,
            fill_price=-1.5,
            trade_date=date(2026, 6, 2),
            executed_at=now,
            net_cash_effect=150.0,
        )
    )
    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="option-position-1",
            option_strategy_decision_id="option-decision-1",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="put_credit_spread",
            trade_identity="tactical_option_trade",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=date(2026, 7, 17),
            max_loss=500.0,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            assignment_notional=11_000.0,
            metadata_json={},
        )
    )
    repository.save_option_risk_snapshot(
        OptionRiskSnapshotRecord(
            option_risk_snapshot_id="risk-snapshot-1",
            ticker="NVDA",
            trade_identity="tactical_option_trade",
            option_strategy_type="put_credit_spread",
            underlying_price=118.0,
            portfolio_delta=-0.11,
            portfolio_gamma=0.01,
            portfolio_theta=0.01,
            portfolio_vega=-0.03,
            net_debit_or_credit=-1.5,
            max_loss=500.0,
            max_profit=150.0,
            margin_requirement=500.0,
            buying_power_effect=500.0,
            assignment_notional=11_000.0,
            worst_case_assignment_notional=11_000.0,
            margin_model_profile="estimated_fidelity_like_conservative_v1",
            margin_model_version="v1",
            margin_requirement_source="simulated_formula",
            risk_status="approved",
            reason_code="within_limits",
            created_at=now,
            metadata_json={},
        )
    )
    repository.save_risk_hedge_decision(
        RiskHedgeDecisionRecord.create(
            risk_decision_id="risk-1",
            ticker="QQQ",
            action="open_option_strategy",
            option_strategy_type="long_put",
            rationale="risk_manager_generated_overlay",
            hedge_cost=250.0,
            protected_notional=20_000.0,
        )
    )

    assert len(repository.option_strategy_decisions) == 1
    assert len(repository.option_strategy_legs) == 1
    assert len(repository.paper_option_orders) == 1
    assert len(repository.paper_option_executions) == 1
    assert len(repository.paper_option_positions) == 1
    assert len(repository.option_risk_snapshots) == 1
    assert len(repository.risk_hedge_decisions) == 1


def test_in_memory_repository_keeps_closed_option_position_and_replacement_open_position():
    repository = InMemoryTradingRepository()
    now = datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc)

    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="option-position-1",
            option_strategy_decision_id="option-decision-1",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="long_call",
            trade_identity="tactical_option_trade",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=date(2026, 7, 17),
            max_loss=220.0,
            margin_requirement=220.0,
            buying_power_effect=220.0,
            assignment_notional=0.0,
            metadata_json={},
        )
    )
    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="option-position-1",
            option_strategy_decision_id="option-decision-1",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="long_call",
            trade_identity="tactical_option_trade",
            quantity=1,
            opened_at=now,
            updated_at=now,
            status="closed",
            expiry=date(2026, 7, 17),
            max_loss=220.0,
            margin_requirement=0.0,
            buying_power_effect=0.0,
            assignment_notional=0.0,
            metadata_json={"lifecycle_action": "close_option_strategy"},
        )
    )
    repository.save_paper_option_position(
        PaperOptionPosition(
            paper_option_position_id="option-position-2",
            option_strategy_decision_id="option-decision-2",
            ticker="NVDA",
            strategy_id="earnings_drift_v1",
            option_strategy_type="long_call",
            trade_identity="tactical_option_trade",
            quantity=2,
            opened_at=now,
            updated_at=now,
            status="open",
            expiry=date(2026, 8, 21),
            max_loss=440.0,
            margin_requirement=440.0,
            buying_power_effect=440.0,
            assignment_notional=0.0,
            metadata_json={"supersedes_option_position_id": "option-position-1"},
        )
    )

    assert len(repository.paper_option_positions) == 2
    assert repository.paper_option_positions[0].status == "closed"
    assert repository.paper_option_positions[1].status == "open"
