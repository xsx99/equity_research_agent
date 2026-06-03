"""SQLAlchemy-backed persistence for trading artifacts."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from src.db.models.trading import (
    CandidateScore,
    IntradayRebalanceDecision,
    IntradaySignalScan,
    IntradaySignalSnapshot,
    NewsAlert,
    OptionRiskSnapshot,
    OptionStrategyDecision,
    OptionStrategyLeg,
    PaperExecution,
    PaperOptionExecution,
    PaperOptionOrder,
    PaperOptionPosition as PaperOptionPositionModel,
    PaperOrder,
    PaperPosition,
    PortfolioRiskSnapshot,
    PortfolioSnapshot as PortfolioSnapshotModel,
    PositionSizingDecision,
    RiskDecision,
    RiskFactorExposure,
    RiskHedgeDecision,
    SignalSnapshot,
    StrategyDefinition,
    StrategyRun,
    StrategyEvaluationResult,
    StrategyProposal,
    TradeClassification,
    TradingDecision,
    UniverseFilterConfig,
    UniverseSnapshot,
    UniverseSymbol,
)
from src.trading.data_sources.universe import UniverseFilterConfig as UniverseFilterConfigRecord
from src.trading.brokers.paper_option import (
    PaperOptionExecutionRecord,
    PaperOptionOrderRecord,
    PaperOptionPosition,
)
from src.trading.brokers.paper_stock import PaperExecutionRecord, PaperOrderRecord
from src.trading.intraday.news_alerts import NewsAlertRecord
from src.trading.intraday.signals import IntradaySignalScanRecord, IntradaySignalSnapshotRecord
from src.trading.risk.hedges import RiskHedgeDecisionRecord
from src.trading.risk.options import OptionRiskSnapshotRecord
from src.trading.options.strategy import OptionStrategyDecisionRecord, OptionStrategyLegRecord
from src.trading.portfolio.state import PortfolioSnapshot, StockPosition
from src.trading.signals import SignalSnapshotResult
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord, StrategyRunRecord
from src.trading.strategies.matching import StrategyDefinitionRecord
from src.trading.workflows.trading_decision import TradingDecisionRecord


class SQLAlchemyTradingRepository:
    """Persist PR6 paper-broker artifacts into SQLAlchemy ORM models."""

    def __init__(self, session: Any) -> None:
        self.session = session

    def save_strategy_definition(self, definition: StrategyDefinitionRecord) -> None:
        row = self.session.query(StrategyDefinition).filter_by(
            strategy_definition_id=_to_uuid(definition.strategy_definition_id)
        ).one_or_none()
        if row is None:
            row = StrategyDefinition(
                strategy_definition_id=_to_uuid(definition.strategy_definition_id),
                strategy_id=definition.strategy_id,
                version=definition.version,
            )
            self.session.add(row)
        row.display_name = definition.display_name
        row.strategy_layer = definition.strategy_layer
        row.typical_horizon = definition.typical_horizon
        row.allowed_common_stock_direction = "long_only"
        row.config_json = dict(definition.config_json)
        row.lifecycle_status = definition.lifecycle_status
        row.source = definition.source
        row.is_active = definition.is_active
        self.session.flush()

    def load_strategy_definitions(self) -> list[StrategyDefinitionRecord]:
        rows = self.session.query(StrategyDefinition).all()
        return [
            StrategyDefinitionRecord(
                strategy_definition_id=str(row.strategy_definition_id),
                strategy_id=row.strategy_id,
                version=row.version,
                display_name=row.display_name,
                strategy_layer=row.strategy_layer,
                typical_horizon=row.typical_horizon,
                config_json=dict(row.config_json or {}),
                lifecycle_status=row.lifecycle_status,
                is_active=bool(row.is_active),
                source=row.source,
            )
            for row in rows
        ]

    def load_active_strategy_definitions(self) -> list[StrategyDefinitionRecord]:
        return [
            row
            for row in self.load_strategy_definitions()
            if row.is_active and row.lifecycle_status in {"active", "experimental", "shadow"}
        ]

    def load_active_universe_filter_config(self) -> UniverseFilterConfigRecord:
        rows = [
            row
            for row in self.session.query(UniverseFilterConfig).all()
            if bool(row.is_active)
        ]
        if not rows:
            raise RuntimeError("active_universe_filter_config_not_found")
        row = max(rows, key=lambda item: (int(item.version), getattr(item, "created_at", None) or 0))
        return UniverseFilterConfigRecord(
            profile_name=row.profile_name,
            version=int(row.version),
            min_price=float(row.min_price),
            min_avg_dollar_volume=float(row.min_avg_dollar_volume),
            included_sectors=tuple(row.included_sectors_json or ()),
            excluded_sectors=tuple(row.excluded_sectors_json or ()),
            included_industries=tuple(row.included_industries_json or ()),
            excluded_industries=tuple(row.excluded_industries_json or ()),
            exchanges=tuple(row.exchanges_json or ()),
            asset_types=tuple(row.asset_types_json or ()),
            manual_include=tuple(row.manual_include_json or ()),
            manual_exclude=tuple(row.manual_exclude_json or ()),
            is_active=bool(row.is_active),
        )

    def save_universe_snapshot(self, snapshot: Any) -> None:
        filter_row = self._require_universe_filter_config_row(snapshot.filter_config)
        row = self.session.query(UniverseSnapshot).filter_by(
            universe_snapshot_id=_to_uuid(snapshot.snapshot_id)
        ).one_or_none()
        if row is None:
            row = UniverseSnapshot(universe_snapshot_id=_to_uuid(snapshot.snapshot_id))
            self.session.add(row)
        row.universe_filter_config_id = filter_row.universe_filter_config_id
        row.snapshot_date = snapshot.snapshot_time.date()
        row.started_at = snapshot.snapshot_time
        row.completed_at = snapshot.snapshot_time
        row.provider = str(snapshot.metadata.get("provider", "live"))
        row.status = "succeeded"
        row.included_count = len(tuple(snapshot.included))
        row.excluded_count = len(tuple(snapshot.excluded))
        row.metadata_json = dict(snapshot.metadata)

        for decision in (*snapshot.included, *snapshot.excluded):
            symbol_row = self.session.query(UniverseSymbol).filter_by(
                universe_snapshot_id=_to_uuid(snapshot.snapshot_id),
                symbol=decision.symbol,
            ).one_or_none()
            if symbol_row is None:
                symbol_row = UniverseSymbol(
                    universe_symbol_id=uuid.uuid4(),
                    universe_snapshot_id=_to_uuid(snapshot.snapshot_id),
                    symbol=decision.symbol,
                )
                self.session.add(symbol_row)
            symbol_row.company_name = decision.asset.company_name
            symbol_row.asset_type = decision.asset.asset_type
            symbol_row.exchange = decision.asset.exchange
            symbol_row.sector = decision.asset.sector
            symbol_row.industry = decision.asset.industry
            symbol_row.price = _decimal_or_none(decision.asset.price)
            symbol_row.avg_dollar_volume = _decimal_or_none(decision.asset.avg_dollar_volume)
            symbol_row.status = decision.status
            symbol_row.exclusion_reason = decision.exclusion_reason
            symbol_row.metadata_json = {}
        self.session.flush()

    def save_strategy_proposal(self, proposal: Any) -> None:
        row = StrategyProposal(
            strategy_proposal_id=_to_uuid(proposal.strategy_proposal_id),
            trade_date=proposal.trade_date,
            prompt_run_id=None,
            proposal_status=proposal.proposal_status,
            proposed_strategy_id=proposal.proposed_strategy_id,
            display_name=proposal.display_name,
            proposed_lifecycle_status=proposal.proposed_lifecycle_status,
            duplicate_of_strategy_id=proposal.duplicate_of_strategy_id,
            rejection_reason=proposal.rejection_reason,
            source="reflection_learning",
            evidence_summary=proposal.evidence_summary,
            proposal_json=dict(proposal.proposal_json),
            metadata_json=dict(proposal.metadata_json),
        )
        self.session.add(row)
        self.session.flush()

    def _require_universe_filter_config_row(self, config: UniverseFilterConfigRecord) -> UniverseFilterConfig:
        row = self.session.query(UniverseFilterConfig).filter_by(
            profile_name=config.profile_name,
            version=int(config.version),
        ).one_or_none()
        if row is None:
            raise RuntimeError(
                f"universe_filter_config_not_found:{config.profile_name}:v{config.version}"
            )
        return row

    def save_strategy_run(self, run: StrategyRunRecord) -> None:
        row = self.session.query(StrategyRun).filter_by(strategy_run_id=_to_uuid(run.strategy_run_id)).one_or_none()
        if row is None:
            row = StrategyRun(strategy_run_id=_to_uuid(run.strategy_run_id))
            self.session.add(row)
        row.decision_time = run.decision_time
        row.snapshot_type = run.snapshot_type
        row.status = run.status
        row.metadata_json = dict(run.metadata_json)
        self.session.flush()

    def save_signal_snapshot(self, snapshot: SignalSnapshotResult) -> None:
        row = self.session.query(SignalSnapshot).filter_by(
            signal_snapshot_id=_to_uuid(snapshot.signal_snapshot_id)
        ).one_or_none()
        if row is None:
            row = SignalSnapshot(signal_snapshot_id=_to_uuid(snapshot.signal_snapshot_id))
            self.session.add(row)
        row.ticker = snapshot.ticker
        row.snapshot_type = snapshot.snapshot_type
        row.decision_time = snapshot.decision_time
        row.available_for_decision_at = snapshot.available_for_decision_at
        row.max_input_available_for_decision_at = snapshot.max_input_available_for_decision_at
        row.signal_json = dict(snapshot.signal_json)
        row.source_freshness_json = dict(snapshot.source_freshness_json)
        row.missing_signals_json = list(snapshot.missing_signals_json)
        row.stale_signals_json = list(snapshot.stale_signals_json)
        row.source_record_refs_json = list(snapshot.source_record_refs_json)
        row.source_available_times_json = dict(snapshot.source_available_times_json)
        row.excluded_future_source_count = int(snapshot.excluded_future_source_count)
        row.point_in_time_passed = bool(snapshot.point_in_time_passed)
        row.selection_source = snapshot.selection_source
        row.manual_request_id = _to_uuid_or_none(snapshot.manual_request_id)
        row.universe_snapshot_id = None
        row.metadata_json = {}
        self.session.flush()

    def load_signal_snapshots_for_decision(
        self,
        *,
        decision_time: Any,
        snapshot_type: str = "pre_open",
    ) -> tuple[SignalSnapshotResult, ...]:
        selected_by_ticker: dict[str, SignalSnapshotResult] = {}
        for row in self.session.query(SignalSnapshot).all():
            if row.snapshot_type != snapshot_type:
                continue
            if row.decision_time != decision_time:
                continue
            if row.available_for_decision_at > decision_time:
                continue
            snapshot = SignalSnapshotResult(
                signal_snapshot_id=str(row.signal_snapshot_id),
                ticker=row.ticker,
                snapshot_type=row.snapshot_type,
                decision_time=row.decision_time,
                available_for_decision_at=row.available_for_decision_at,
                max_input_available_for_decision_at=row.max_input_available_for_decision_at,
                signal_json=dict(row.signal_json or {}),
                source_freshness_json=dict(row.source_freshness_json or {}),
                missing_signals_json=list(row.missing_signals_json or []),
                stale_signals_json=list(row.stale_signals_json or []),
                source_record_refs_json=list(row.source_record_refs_json or []),
                source_available_times_json=dict(row.source_available_times_json or {}),
                excluded_future_source_count=int(row.excluded_future_source_count or 0),
                point_in_time_passed=bool(row.point_in_time_passed),
                selection_source=row.selection_source,
                manual_request_id=str(row.manual_request_id) if row.manual_request_id is not None else None,
            )
            current = selected_by_ticker.get(snapshot.ticker)
            if current is None or snapshot.available_for_decision_at > current.available_for_decision_at:
                selected_by_ticker[snapshot.ticker] = snapshot
        return tuple(snapshot for _ticker, snapshot in sorted(selected_by_ticker.items()))

    def save_candidate_scores(self, candidates: list[CandidateScoreRecord] | tuple[CandidateScoreRecord, ...]) -> None:
        for candidate in candidates:
            row = self.session.query(CandidateScore).filter_by(
                candidate_score_id=_to_uuid(candidate.candidate_score_id)
            ).one_or_none()
            if row is None:
                row = CandidateScore(candidate_score_id=_to_uuid(candidate.candidate_score_id))
                self.session.add(row)
            row.strategy_run_id = _to_uuid(candidate.strategy_run_id)
            row.signal_snapshot_id = _to_uuid_or_none(candidate.signal_snapshot_id)
            row.ticker = candidate.ticker
            row.strategy_id = candidate.strategy_id
            row.strategy_version = candidate.strategy_version
            row.strategy_definition_id = _to_uuid_or_none(candidate.strategy_definition_id)
            row.candidate_score = Decimal(str(candidate.candidate_score))
            row.direction = candidate.direction
            row.action = candidate.action
            row.typical_horizon = candidate.typical_horizon
            row.core_signal_evidence_json = dict(candidate.core_signal_evidence)
            row.missing_required_signals_json = list(candidate.missing_required_signals)
            row.unsupported_missing_signal_families_json = list(candidate.unsupported_missing_signal_families)
            row.invalidators_json = list(candidate.invalidators)
            row.risk_tags_json = list(candidate.risk_tags)
            row.macro_compatibility = candidate.macro_compatibility
            row.selection_source = candidate.selection_source
            row.manual_request_id = _to_uuid_or_none(candidate.manual_request_id)
            row.selection_reason = candidate.selection_reason
            row.rejection_reason = candidate.rejection_reason
            row.benchmark_context_json = dict(candidate.benchmark_context)
            row.decision_time = candidate.decision_time
            row.available_for_decision_at = candidate.available_for_decision_at
            row.source_record_refs_json = list(candidate.source_record_refs_json)
        self.session.flush()

    def save_trade_classifications(
        self,
        classifications: list[TradeClassificationRecord] | tuple[TradeClassificationRecord, ...],
    ) -> None:
        for classification in classifications:
            row = self.session.query(TradeClassification).filter_by(
                trade_classification_id=_to_uuid(classification.trade_classification_id)
            ).one_or_none()
            if row is None:
                row = TradeClassification(
                    trade_classification_id=_to_uuid(classification.trade_classification_id)
                )
                self.session.add(row)
            row.candidate_score_id = _to_uuid(classification.candidate_score_id)
            row.strategy_run_id = _to_uuid(classification.strategy_run_id)
            row.ticker = classification.ticker
            row.selected_strategy_id = classification.selected_strategy_id
            row.selected_strategy_version = classification.selected_strategy_version
            row.expression_bucket_id = classification.expression_bucket_id
            row.expression_bucket_version = classification.expression_bucket_version
            row.trade_identity = classification.trade_identity
            row.watch_type = classification.watch_type
            row.direction = classification.direction
            row.intended_horizon = classification.intended_horizon
            row.exit_policy = classification.exit_policy
            row.result_status = classification.result_status
            row.classification_reason = classification.classification_reason
            row.selected_strategy_context_json = dict(classification.selected_strategy_context_json)
            row.decision_time = classification.decision_time
        self.session.flush()

    def save_position_sizing_decision(self, decision: Any) -> None:
        row = self.session.query(PositionSizingDecision).filter_by(
            position_sizing_decision_id=_to_uuid(decision.position_sizing_decision_id)
        ).one_or_none()
        if row is None:
            row = PositionSizingDecision(
                position_sizing_decision_id=_to_uuid(decision.position_sizing_decision_id)
            )
            self.session.add(row)
        row.candidate_score_id = _to_uuid_or_none(decision.candidate_score_id)
        row.trade_classification_id = _to_uuid_or_none(decision.trade_classification_id)
        row.ticker = decision.ticker
        row.risk_appetite = decision.risk_appetite
        row.base_weight = Decimal(str(decision.base_weight))
        row.volatility_adjusted_weight = Decimal(str(decision.volatility_adjusted_weight))
        row.liquidity_capped_weight = Decimal(str(decision.liquidity_capped_weight))
        row.final_weight = Decimal(str(decision.final_weight))
        row.final_notional = Decimal(str(decision.final_notional))
        row.applied_caps_json = list(decision.applied_caps)
        row.binding_constraint = decision.binding_constraint
        row.decision_time = decision.decision_time
        row.metadata_json = dict(decision.metadata_json)
        self.session.flush()

    def save_portfolio_risk_snapshot(self, snapshot: Any) -> None:
        row = self.session.query(PortfolioRiskSnapshot).filter_by(
            portfolio_risk_snapshot_id=_to_uuid(snapshot.portfolio_risk_snapshot_id)
        ).one_or_none()
        if row is None:
            row = PortfolioRiskSnapshot(
                portfolio_risk_snapshot_id=_to_uuid(snapshot.portfolio_risk_snapshot_id)
            )
            self.session.add(row)
        row.decision_time = snapshot.decision_time
        row.risk_appetite = snapshot.risk_appetite
        row.resolver_version = snapshot.resolver_version
        row.margin_model_profile = snapshot.margin_model_profile
        row.margin_model_version = snapshot.margin_model_version
        row.account_equity = Decimal(str(snapshot.account_equity))
        row.cash_balance = Decimal(str(snapshot.cash_balance))
        row.buying_power = Decimal(str(snapshot.buying_power))
        row.excess_liquidity = Decimal(str(snapshot.excess_liquidity))
        row.stock_margin_requirement = Decimal(str(snapshot.stock_margin_requirement))
        row.option_margin_requirement = Decimal(str(snapshot.option_margin_requirement))
        row.total_margin_requirement = Decimal(str(snapshot.total_margin_requirement))
        row.initial_margin_requirement = _decimal_or_none(snapshot.initial_margin_requirement)
        row.maintenance_margin_requirement = _decimal_or_none(snapshot.maintenance_margin_requirement)
        row.margin_requirement_source = snapshot.margin_requirement_source
        row.net_exposure = Decimal(str(snapshot.net_exposure))
        row.gross_exposure = Decimal(str(snapshot.gross_exposure))
        row.beta_adjusted_net_exposure = Decimal(str(snapshot.beta_adjusted_net_exposure))
        row.concentration_flags_json = list(snapshot.concentration_flags)
        row.metadata_json = dict(snapshot.metadata_json)
        self.session.flush()

    def save_risk_factor_exposures(
        self,
        exposures: list[Any] | tuple[Any, ...],
    ) -> None:
        for exposure in exposures:
            row = RiskFactorExposure(
                risk_factor_exposure_id=uuid.uuid4(),
                portfolio_risk_snapshot_id=_to_uuid(exposure.metadata_json["portfolio_risk_snapshot_id"])
                if "portfolio_risk_snapshot_id" in exposure.metadata_json
                else _latest_portfolio_risk_snapshot_id(self.session),
                factor_type=exposure.factor_type,
                factor_value=exposure.factor_value,
                gross_exposure=Decimal(str(exposure.gross_exposure)),
                net_exposure=Decimal(str(exposure.net_exposure)),
                long_exposure=Decimal(str(exposure.long_exposure)),
                short_exposure=Decimal(str(exposure.short_exposure)),
                position_count=int(exposure.position_count),
                metadata_json=dict(exposure.metadata_json),
            )
            self.session.add(row)
        self.session.flush()

    def save_risk_decision(self, decision: Any) -> None:
        row = self.session.query(RiskDecision).filter_by(
            risk_decision_id=_to_uuid(decision.risk_decision_id)
        ).one_or_none()
        if row is None:
            row = RiskDecision(risk_decision_id=_to_uuid(decision.risk_decision_id))
            self.session.add(row)
        row.candidate_score_id = _to_uuid_or_none(decision.candidate_score_id)
        row.trade_classification_id = _to_uuid_or_none(decision.trade_classification_id)
        row.position_sizing_decision_id = _to_uuid_or_none(decision.position_sizing_decision_id)
        row.portfolio_risk_snapshot_id = _to_uuid_or_none(decision.portfolio_risk_snapshot_id)
        row.ticker = decision.ticker
        row.status = decision.status
        row.reason_code = decision.reason_code
        row.approved_weight = Decimal(str(decision.approved_weight))
        row.approved_notional = Decimal(str(decision.approved_notional))
        row.approved_quantity = Decimal(str(decision.approved_quantity))
        row.applied_rules_json = list(decision.applied_rules)
        row.generated_hedge_action_json = (
            dict(decision.generated_hedge_action) if decision.generated_hedge_action is not None else None
        )
        row.decision_time = decision.decision_time
        row.metadata_json = dict(decision.metadata_json)
        self.session.flush()

    def save_prompt_template(self, template: object) -> None:
        return None

    def save_prompt_run(self, prompt_run: object) -> None:
        return None

    def save_usage_events(self, usage_events: list[object] | tuple[object, ...]) -> None:
        return None

    def save_trading_decision(self, decision: TradingDecisionRecord) -> None:
        row = self.session.query(TradingDecision).filter_by(
            trading_decision_id=_to_uuid(decision.trading_decision_id)
        ).one_or_none()
        if row is None:
            row = TradingDecision(trading_decision_id=_to_uuid(decision.trading_decision_id))
            self.session.add(row)
        row.candidate_score_id = _to_uuid_or_none(decision.candidate_score_id)
        row.trade_classification_id = _to_uuid_or_none(decision.trade_classification_id)
        row.risk_decision_id = _to_uuid_or_none(decision.risk_decision_id)
        row.ticker = decision.ticker
        row.decision = decision.decision
        row.strategy_id = decision.strategy_id
        row.strategy_version = decision.strategy_version
        row.expression_bucket_id = decision.expression_bucket_id
        row.expression_bucket_version = decision.expression_bucket_version
        row.trade_identity = decision.trade_identity
        row.instrument_type = decision.instrument_type
        row.selection_source = decision.selection_source
        row.manual_request_id = _to_uuid_or_none(decision.manual_request_id)
        row.confidence = Decimal(str(decision.confidence))
        row.target_weight = Decimal(str(decision.target_weight))
        row.approved_weight = Decimal(str(decision.approved_weight))
        row.max_loss_pct = Decimal(str(decision.max_loss_pct))
        row.time_horizon = decision.time_horizon
        row.thesis = decision.thesis
        row.invalidators_json = list(decision.invalidators)
        row.prompt_run_id = None
        row.fallback_action = decision.metadata_json.get("fallback_action")
        row.paper_trade_authorized = bool(decision.metadata_json.get("paper_trade_authorized", False))
        row.context_snapshot_json = {
            "prompt_template": {
                "prompt_id": getattr(decision.prompt_template, "prompt_id", None),
                "prompt_version": getattr(decision.prompt_template, "prompt_version", None),
            },
            "prompt_run": getattr(decision.prompt_run, "__dict__", {}),
            "usage_events": [getattr(event, "__dict__", {}) for event in decision.usage_events],
        }
        row.decision_time = decision.decision_time
        row.available_for_decision_at = decision.available_for_decision_at
        row.metadata_json = dict(decision.metadata_json)
        self.session.flush()

    def save_strategy_evaluation_result(self, result: Any) -> None:
        row = StrategyEvaluationResult(
            strategy_evaluation_result_id=_to_uuid(result.strategy_evaluation_result_id),
            strategy_definition_id=_to_uuid_or_none(result.strategy_definition_id),
            strategy_proposal_id=_to_uuid_or_none(result.strategy_proposal_id),
            strategy_id=result.strategy_id,
            evaluation_type=result.evaluation_type,
            evaluation_status=result.evaluation_status,
            prior_lifecycle_status=result.prior_lifecycle_status,
            new_lifecycle_status=result.new_lifecycle_status,
            reason_code=result.reason_code,
            evidence_summary=result.evidence_summary,
            metrics_json=dict(result.metrics_json),
            created_at=result.created_at,
        )
        self.session.add(row)
        self.session.flush()

    def save_paper_order(self, order: PaperOrderRecord) -> None:
        row = self.session.query(PaperOrder).filter_by(client_order_id=order.client_order_id).one_or_none()
        if row is None:
            row = PaperOrder(
                paper_order_id=_to_uuid(order.paper_order_id),
                client_order_id=order.client_order_id,
            )
            self.session.add(row)
        row.broker_order_id = order.broker_order_id
        row.trading_decision_id = _to_uuid_or_none(order.trading_decision_id)
        row.risk_decision_id = _to_uuid_or_none(order.risk_decision_id)
        row.ticker = order.ticker
        row.strategy_id = order.strategy_id
        row.action = order.action
        row.trade_date = order.trade_date
        row.quantity = Decimal(str(order.quantity))
        row.order_price = _decimal_or_none(order.limit_price)
        row.status = order.status
        row.rejection_reason = order.rejection_reason
        row.created_at = order.created_at
        self.session.flush()

    def save_intraday_signal_scan(self, scan: IntradaySignalScanRecord) -> None:
        row = self.session.query(IntradaySignalScan).filter_by(
            intraday_signal_scan_id=_to_uuid(scan.intraday_signal_scan_id)
        ).one_or_none()
        if row is None:
            row = IntradaySignalScan(intraday_signal_scan_id=_to_uuid(scan.intraday_signal_scan_id))
            self.session.add(row)
        row.decision_time = scan.decision_time
        row.started_at = scan.started_at
        row.completed_at = scan.completed_at
        row.status = scan.status
        row.scope_json = dict(scan.scope_json)
        row.coverage_json = dict(scan.coverage_json)
        row.error_message = scan.error_message
        row.metadata_json = dict(scan.metadata_json)
        self.session.flush()

    def save_intraday_signal_snapshot(self, snapshot: IntradaySignalSnapshotRecord) -> None:
        row = self.session.query(IntradaySignalSnapshot).filter_by(
            intraday_signal_snapshot_id=_to_uuid(snapshot.intraday_signal_snapshot_id)
        ).one_or_none()
        if row is None:
            row = IntradaySignalSnapshot(
                intraday_signal_snapshot_id=_to_uuid(snapshot.intraday_signal_snapshot_id)
            )
            self.session.add(row)
        row.intraday_signal_scan_id = _to_uuid(snapshot.intraday_signal_scan_id)
        row.ticker = snapshot.ticker
        row.decision_time = snapshot.decision_time
        row.baseline_signal_snapshot_id = _to_uuid_or_none(snapshot.baseline_signal_snapshot_id)
        row.previous_intraday_snapshot_id = _to_uuid_or_none(snapshot.previous_intraday_snapshot_id)
        row.refreshed_signals_json = dict(snapshot.refreshed_signals_json)
        row.carried_forward_signals_json = dict(snapshot.carried_forward_signals_json)
        row.delta_vs_baseline_json = dict(snapshot.delta_vs_baseline_json)
        row.delta_vs_previous_json = dict(snapshot.delta_vs_previous_json)
        row.source_freshness_json = dict(snapshot.source_freshness_json)
        row.metadata_json = dict(snapshot.metadata_json)
        row.created_at = snapshot.created_at
        self.session.flush()

    def save_news_alert(self, alert: NewsAlertRecord) -> None:
        row = self.session.query(NewsAlert).filter_by(dedupe_key=alert.dedupe_key).one_or_none()
        if row is None:
            row = NewsAlert(news_alert_id=_to_uuid(alert.news_alert_id), dedupe_key=alert.dedupe_key)
            self.session.add(row)
        row.ticker = alert.ticker
        row.source_ticker = alert.source_ticker
        row.alert_type = alert.alert_type
        row.sentiment = alert.sentiment
        row.severity = alert.severity
        row.source = alert.source
        row.published_at = alert.published_at
        row.headline = alert.headline
        row.summary = alert.summary
        row.strategy_relevance_json = list(alert.strategy_relevance)
        row.affected_positions_json = list(alert.affected_positions)
        row.affected_candidates_json = list(alert.affected_candidates)
        row.affected_themes_json = list(alert.affected_themes)
        row.readthrough_source_ticker = alert.readthrough_source_ticker
        row.action_required = alert.action_required
        row.event_news_item_id = _to_uuid_or_none(alert.event_news_item_id)
        row.metadata_json = dict(alert.metadata_json)
        row.created_at = alert.created_at
        self.session.flush()

    def save_intraday_rebalance_decision(self, decision: Any) -> None:
        row = self.session.query(IntradayRebalanceDecision).filter_by(
            intraday_rebalance_decision_id=_to_uuid(decision.intraday_rebalance_decision_id)
        ).one_or_none()
        if row is None:
            row = IntradayRebalanceDecision(
                intraday_rebalance_decision_id=_to_uuid(decision.intraday_rebalance_decision_id)
            )
            self.session.add(row)
        row.ticker = decision.ticker
        row.action = decision.action
        row.status = decision.status
        row.reason_code = decision.reason_code
        row.confidence = Decimal(str(decision.confidence))
        row.target_weight = Decimal(str(decision.target_weight))
        row.approved_quantity = Decimal(str(decision.approved_quantity))
        row.thesis = decision.thesis
        row.urgency = decision.urgency
        row.rationale_json = list(decision.rationale)
        row.available_for_decision_at = decision.available_for_decision_at
        row.decision_time = decision.decision_time
        row.risk_decision_id = _to_uuid_or_none(decision.risk_decision_id)
        row.metadata_json = dict(decision.metadata_json)
        self.session.flush()

    def save_paper_execution(self, execution: PaperExecutionRecord) -> None:
        row = self.session.query(PaperExecution).filter_by(
            paper_execution_id=_to_uuid(execution.paper_execution_id)
        ).one_or_none()
        if row is None:
            row = PaperExecution(
                paper_execution_id=_to_uuid(execution.paper_execution_id),
            )
            self.session.add(row)
        row.paper_order_id = _to_uuid(execution.paper_order_id)
        row.broker_order_id = execution.broker_order_id
        row.ticker = execution.ticker
        row.quantity = Decimal(str(execution.quantity))
        row.fill_price = Decimal(str(execution.fill_price))
        row.trade_date = execution.trade_date
        row.executed_at = execution.executed_at
        row.net_cash_effect = Decimal(str(execution.net_cash_effect))
        self.session.flush()

    def save_option_strategy_decision(self, decision: OptionStrategyDecisionRecord) -> None:
        row = self.session.query(OptionStrategyDecision).filter_by(
            option_strategy_decision_id=_to_uuid(decision.option_strategy_decision_id)
        ).one_or_none()
        if row is None:
            row = OptionStrategyDecision(option_strategy_decision_id=_to_uuid(decision.option_strategy_decision_id))
            self.session.add(row)
        row.trading_decision_id = _to_uuid_or_none(decision.trading_decision_id)
        row.ticker = decision.ticker
        row.trade_identity = decision.trade_identity
        row.decision_action = decision.decision_action
        row.option_strategy_type = decision.option_strategy_type
        row.status = decision.status
        row.rejection_reason = decision.rejection_reason
        row.strategy_id = decision.strategy_id
        row.strategy_version = decision.strategy_version
        row.expression_bucket_id = decision.expression_bucket_id
        row.expression_bucket_version = decision.expression_bucket_version
        row.underlying_price = Decimal(str(decision.underlying_price))
        row.expiry = decision.expiry
        row.net_debit_or_credit = Decimal(str(decision.net_debit_or_credit))
        row.max_loss = Decimal(str(decision.max_loss))
        row.max_profit = _decimal_or_none(decision.max_profit)
        row.breakevens_json = list(decision.breakevens)
        row.margin_requirement = Decimal(str(decision.margin_requirement))
        row.buying_power_effect = Decimal(str(decision.buying_power_effect))
        row.assignment_notional = Decimal(str(decision.assignment_notional))
        row.portfolio_delta = Decimal(str(decision.portfolio_delta))
        row.portfolio_gamma = Decimal(str(decision.portfolio_gamma))
        row.portfolio_theta = Decimal(str(decision.portfolio_theta))
        row.portfolio_vega = Decimal(str(decision.portfolio_vega))
        row.earnings_date = decision.earnings_date
        row.event_through_expiry = decision.event_through_expiry
        row.strategy_pairing_method = decision.strategy_pairing_method
        row.assignment_plan = decision.assignment_plan
        row.margin_model_profile = decision.margin_model_profile
        row.margin_model_version = decision.margin_model_version
        row.margin_requirement_source = decision.margin_requirement_source
        row.profit_target_pct = Decimal(str(decision.profit_target_pct))
        row.max_loss_rule = decision.max_loss_rule
        row.roll_conditions_json = list(decision.roll_conditions)
        row.close_conditions_json = list(decision.close_conditions)
        row.metadata_json = dict(decision.metadata_json)
        row.created_at = decision.created_at
        self.session.flush()

    def save_option_strategy_legs(
        self,
        legs: list[OptionStrategyLegRecord] | tuple[OptionStrategyLegRecord, ...],
    ) -> None:
        for leg in legs:
            row = self.session.query(OptionStrategyLeg).filter_by(
                option_strategy_leg_id=_to_uuid(leg.option_strategy_leg_id)
            ).one_or_none()
            if row is None:
                row = OptionStrategyLeg(option_strategy_leg_id=_to_uuid(leg.option_strategy_leg_id))
                self.session.add(row)
            row.option_strategy_decision_id = _to_uuid(leg.option_strategy_decision_id)
            row.ticker = leg.ticker
            row.option_type = leg.option_type
            row.side = leg.side
            row.quantity = int(leg.quantity)
            row.strike = Decimal(str(leg.strike))
            row.expiry = leg.expiry
            row.dte = int(leg.dte)
            row.delta = Decimal(str(leg.delta))
            row.gamma = Decimal(str(leg.gamma))
            row.theta = Decimal(str(leg.theta))
            row.vega = Decimal(str(leg.vega))
            row.iv_rank = _decimal_or_none(leg.iv_rank)
            row.bid = Decimal(str(leg.bid))
            row.ask = Decimal(str(leg.ask))
            row.mid = Decimal(str(leg.mid))
            row.chosen_price = Decimal(str(leg.chosen_price))
            row.created_at = leg.created_at
        self.session.flush()

    def save_option_risk_snapshot(self, snapshot: OptionRiskSnapshotRecord) -> None:
        row = OptionRiskSnapshot(
            option_risk_snapshot_id=_to_uuid(snapshot.option_risk_snapshot_id),
            ticker=snapshot.ticker,
            trade_identity=snapshot.trade_identity,
            option_strategy_type=snapshot.option_strategy_type,
            underlying_price=Decimal(str(snapshot.underlying_price)),
            portfolio_delta=Decimal(str(snapshot.portfolio_delta)),
            portfolio_gamma=Decimal(str(snapshot.portfolio_gamma)),
            portfolio_theta=Decimal(str(snapshot.portfolio_theta)),
            portfolio_vega=Decimal(str(snapshot.portfolio_vega)),
            net_debit_or_credit=Decimal(str(snapshot.net_debit_or_credit)),
            max_loss=Decimal(str(snapshot.max_loss)),
            max_profit=_decimal_or_none(snapshot.max_profit),
            margin_requirement=Decimal(str(snapshot.margin_requirement)),
            buying_power_effect=Decimal(str(snapshot.buying_power_effect)),
            assignment_notional=Decimal(str(snapshot.assignment_notional)),
            worst_case_assignment_notional=Decimal(str(snapshot.worst_case_assignment_notional)),
            margin_model_profile=snapshot.margin_model_profile,
            margin_model_version=snapshot.margin_model_version,
            margin_requirement_source=snapshot.margin_requirement_source,
            risk_status=snapshot.risk_status,
            reason_code=snapshot.reason_code,
            metadata_json=dict(snapshot.metadata_json),
            created_at=snapshot.created_at,
        )
        self.session.add(row)
        self.session.flush()

    def save_risk_hedge_decision(self, decision: RiskHedgeDecisionRecord) -> None:
        row = RiskHedgeDecision(
            risk_hedge_decision_id=_to_uuid(decision.risk_hedge_decision_id),
            risk_decision_id=_to_uuid_or_none(decision.risk_decision_id),
            ticker=decision.ticker,
            trade_identity=decision.trade_identity,
            action=decision.action,
            option_strategy_type=decision.option_strategy_type,
            rationale=decision.rationale,
            hedge_cost=Decimal(str(decision.hedge_cost)),
            protected_notional=Decimal(str(decision.protected_notional)),
            metadata_json=dict(decision.metadata_json),
            created_at=decision.created_at,
        )
        self.session.add(row)
        self.session.flush()

    def has_paper_execution(self, paper_execution_id: str) -> bool:
        return self.session.query(PaperExecution).filter_by(
            paper_execution_id=_to_uuid(paper_execution_id)
        ).one_or_none() is not None

    def save_paper_option_order(self, order: PaperOptionOrderRecord) -> None:
        row = self.session.query(PaperOptionOrder).filter_by(
            paper_option_order_id=_to_uuid(order.paper_option_order_id)
        ).one_or_none()
        if row is None:
            row = PaperOptionOrder(paper_option_order_id=_to_uuid(order.paper_option_order_id))
            self.session.add(row)
        row.trading_decision_id = _to_uuid_or_none(order.trading_decision_id)
        row.risk_decision_id = _to_uuid_or_none(order.risk_decision_id)
        row.option_strategy_decision_id = _to_uuid_or_none(order.option_strategy_decision_id)
        row.ticker = order.ticker
        row.strategy_id = order.strategy_id
        row.option_strategy_type = order.option_strategy_type
        row.action = order.action
        row.trade_identity = order.trade_identity
        row.trade_date = order.trade_date
        row.quantity = int(order.quantity)
        row.limit_price = Decimal(str(order.limit_price))
        row.status = order.status
        row.rejection_reason = order.rejection_reason
        row.margin_requirement = Decimal(str(order.margin_requirement))
        row.buying_power_effect = Decimal(str(order.buying_power_effect))
        row.created_at = order.created_at
        self.session.flush()

    def save_paper_option_execution(self, execution: PaperOptionExecutionRecord) -> None:
        row = self.session.query(PaperOptionExecution).filter_by(
            paper_option_execution_id=_to_uuid(execution.paper_option_execution_id)
        ).one_or_none()
        if row is None:
            row = PaperOptionExecution(paper_option_execution_id=_to_uuid(execution.paper_option_execution_id))
            self.session.add(row)
        row.paper_option_order_id = _to_uuid(execution.paper_option_order_id)
        row.ticker = execution.ticker
        row.quantity = int(execution.quantity)
        row.fill_price = Decimal(str(execution.fill_price))
        row.trade_date = execution.trade_date
        row.executed_at = execution.executed_at
        row.net_cash_effect = Decimal(str(execution.net_cash_effect))
        self.session.flush()

    def has_paper_option_execution(self, paper_option_execution_id: str) -> bool:
        return self.session.query(PaperOptionExecution).filter_by(
            paper_option_execution_id=_to_uuid(paper_option_execution_id)
        ).one_or_none() is not None

    def load_paper_positions(self) -> tuple[StockPosition, ...]:
        rows = self.session.query(PaperPosition).filter_by(status="open").all()
        positions = [
            StockPosition(
                ticker=row.ticker,
                quantity=float(row.quantity),
                average_cost=float(row.average_cost),
                market_price=float(row.market_price),
                market_value=float(row.market_value),
                trade_identity=row.trade_identity,
                strategy_id=row.strategy_id,
                opened_at=row.opened_at,
                updated_at=row.updated_at,
                direction=row.direction,
            )
            for row in rows
        ]
        return tuple(sorted(positions, key=lambda item: item.ticker))

    def replace_paper_positions(self, positions: tuple[StockPosition, ...] | list[StockPosition]) -> None:
        latest_by_ticker = {position.ticker: position for position in positions}
        existing_rows = self.session.query(PaperPosition).all()
        open_rows_by_ticker = {row.ticker: row for row in existing_rows if row.status == "open"}

        for ticker, position in latest_by_ticker.items():
            row = open_rows_by_ticker.get(ticker)
            if row is None:
                row = PaperPosition(
                    paper_position_id=uuid.uuid4(),
                    ticker=ticker,
                )
                self.session.add(row)
            row.strategy_id = position.strategy_id
            row.trade_identity = position.trade_identity
            row.direction = position.direction
            row.quantity = Decimal(str(position.quantity))
            row.average_cost = Decimal(str(position.average_cost))
            row.market_price = Decimal(str(position.market_price))
            row.market_value = Decimal(str(position.market_value))
            row.opened_at = position.opened_at
            row.updated_at = position.updated_at
            row.closed_at = None
            row.status = "open"

        for row in existing_rows:
            if row.status != "open":
                continue
            if row.ticker in latest_by_ticker:
                continue
            row.status = "closed"
            row.closed_at = row.updated_at
            row.updated_at = row.updated_at

        self.session.flush()

    def save_paper_option_position(self, position: PaperOptionPosition) -> None:
        row = self.session.query(PaperOptionPositionModel).filter_by(
            paper_option_position_id=_to_uuid(position.paper_option_position_id)
        ).one_or_none()
        if row is None:
            row = PaperOptionPositionModel(paper_option_position_id=_to_uuid(position.paper_option_position_id))
            self.session.add(row)
        row.option_strategy_decision_id = _to_uuid_or_none(position.option_strategy_decision_id)
        row.ticker = position.ticker
        row.strategy_id = position.strategy_id
        row.option_strategy_type = position.option_strategy_type
        row.trade_identity = position.trade_identity
        row.quantity = int(position.quantity)
        row.opened_at = position.opened_at
        row.updated_at = position.updated_at
        row.status = position.status
        row.expiry = position.expiry
        row.max_loss = Decimal(str(position.max_loss))
        row.margin_requirement = Decimal(str(position.margin_requirement))
        row.buying_power_effect = Decimal(str(position.buying_power_effect))
        row.assignment_notional = Decimal(str(position.assignment_notional))
        row.metadata_json = dict(position.metadata_json)
        self.session.flush()

    def load_paper_option_positions(self) -> tuple[PaperOptionPosition, ...]:
        rows = self.session.query(PaperOptionPositionModel).filter_by(status="open").all()
        positions = [
            PaperOptionPosition(
                paper_option_position_id=str(row.paper_option_position_id),
                option_strategy_decision_id=str(row.option_strategy_decision_id),
                ticker=row.ticker,
                strategy_id=row.strategy_id,
                option_strategy_type=row.option_strategy_type,
                trade_identity=row.trade_identity,
                quantity=int(row.quantity),
                opened_at=row.opened_at,
                updated_at=row.updated_at,
                status=row.status,
                expiry=row.expiry,
                max_loss=float(row.max_loss),
                margin_requirement=float(row.margin_requirement),
                buying_power_effect=float(row.buying_power_effect),
                assignment_notional=float(row.assignment_notional),
                metadata_json=dict(row.metadata_json or {}),
            )
            for row in rows
        ]
        return tuple(positions)

    def save_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        row = PortfolioSnapshotModel(
            portfolio_snapshot_id=uuid.uuid4(),
            snapshot_time=snapshot.as_of,
            cash_balance=Decimal(str(snapshot.cash_balance)),
            account_equity=Decimal(str(snapshot.account_equity)),
            net_liquidation_value=Decimal(str(snapshot.net_liquidation_value)),
            buying_power=Decimal(str(snapshot.buying_power)),
            excess_liquidity=Decimal(str(snapshot.excess_liquidity)),
            stock_market_value=Decimal(str(snapshot.stock_market_value)),
            option_market_value=Decimal(str(snapshot.option_market_value)),
            stock_margin_requirement=Decimal(str(snapshot.stock_margin_requirement)),
            option_margin_requirement=Decimal(str(snapshot.option_margin_requirement)),
            total_margin_requirement=Decimal(str(snapshot.total_margin_requirement)),
            initial_margin_requirement=Decimal(str(snapshot.initial_margin_requirement)),
            maintenance_margin_requirement=Decimal(str(snapshot.maintenance_margin_requirement)),
            margin_model_profile=snapshot.margin_model_profile,
            margin_model_version=snapshot.margin_model_version,
            margin_requirement_source=snapshot.margin_requirement_source,
            day_pnl=Decimal(str(snapshot.day_pnl)),
            realized_pnl=Decimal(str(snapshot.realized_pnl)),
            unrealized_pnl=Decimal(str(snapshot.unrealized_pnl)),
            metadata_json=dict(snapshot.metadata_json),
        )
        self.session.add(row)
        self.session.flush()


SqlAlchemyTradingRepository = SQLAlchemyTradingRepository


def _to_uuid(value: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, str(value))


def _to_uuid_or_none(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    return _to_uuid(value)


def _decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _latest_portfolio_risk_snapshot_id(session: Any) -> uuid.UUID:
    rows = session.query(PortfolioRiskSnapshot).all()
    if not rows:
        raise RuntimeError("portfolio_risk_snapshot_not_found_for_exposure")
    latest = max(
        rows,
        key=lambda row: (
            getattr(row, "decision_time", None),
            getattr(row, "created_at", None),
        ),
    )
    return latest.portfolio_risk_snapshot_id
