from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any

from src.db.models.trading import (
    ExecutionAttempt,
    LlmPromptRun,
    LlmPromptTemplate,
    LlmUsageEvent,
    ManualTickerRequest,
    PaperExecution,
    PaperOrder,
    PeerBasket,
    RiskDecision,
    TickerRelationship as TickerRelationshipModel,
    TradingDecision,
    TradingRuntimeRun,
    UniverseFilterConfig,
    UniverseSnapshot,
    UniverseSymbol,
    UniverseRanking,
    UniverseRankingRun,
)
from src.trading.ranking.records import (
    PeerBasketMembership,
    TickerRelationship,
    UniverseRankingRecord,
    UniverseRankingRunRecord,
)
from src.trading.execution.attempts import ExecutionAttemptRecord
from src.trading.data_sources.universe import UniverseFilterConfig as UniverseFilterConfigRecord
from src.trading.manual_review.sqlalchemy import ManualReviewAuditRow
from src.trading.repositories._base_common import (
    _datetime_value,
    _decimal_or_none,
    _latest_row_sort_key,
    _string_or_none,
    _to_uuid,
    _to_uuid_or_none,
)
from src.trading.repositories._base_manual_review import (
    _manual_review_execution_path_state,
    _manual_review_linkage_state,
)
from src.trading.workflows.trading_decision import TradingDecisionRecord


class RuntimeMiscRepositoryMixin:
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
    def save_runtime_run(self, payload: dict[str, Any]) -> None:
        row = TradingRuntimeRun(
            phase=str(payload["phase"]),
            status=str(payload["status"]),
            trade_date=payload["trade_date"],
            as_of=_datetime_value(payload["as_of"]),
            started_at=_datetime_value(payload["started_at"]),
            completed_at=_datetime_value(payload["completed_at"]),
            summary_json=dict(payload.get("summary_json") or {}),
            execution_json=dict(payload.get("execution_json") or {}),
            metadata_json=dict(payload.get("metadata_json") or {}),
        )
        self.session.add(row)
        self.session.flush()
    def load_latest_runtime_run(
        self,
        *,
        phase: str,
        trade_date: date | None = None,
    ) -> dict[str, Any] | None:
        query = self.session.query(TradingRuntimeRun).filter(TradingRuntimeRun.phase == phase)
        if trade_date is not None:
            query = query.filter(TradingRuntimeRun.trade_date == trade_date)
        rows = query.all()
        if not rows:
            return None
        row = max(
            rows,
            key=lambda item: (
                item.completed_at,
                item.as_of,
                getattr(item, "created_at", None) or datetime.min.replace(tzinfo=timezone.utc),
            ),
        )
        return {
            "phase": row.phase,
            "status": row.status,
            "trade_date": row.trade_date,
            "as_of": row.as_of,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "summary_json": dict(row.summary_json or {}),
            "execution_json": dict(row.execution_json or {}),
            "metadata_json": dict(row.metadata_json or {}),
        }
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

    def save_universe_ranking_run(
        self,
        run: UniverseRankingRunRecord,
        rankings: tuple[UniverseRankingRecord, ...] | list[UniverseRankingRecord],
    ) -> None:
        """Upsert a run and its full ticker cohort before it is consumed downstream."""
        run_id = _to_uuid(run.universe_ranking_run_id)
        row = self.session.query(UniverseRankingRun).filter_by(
            universe_ranking_run_id=run_id
        ).one_or_none()
        if row is None:
            row = UniverseRankingRun(universe_ranking_run_id=run_id)
            self.session.add(row)
        row.universe_snapshot_id = _to_uuid(run.universe_snapshot_id)
        row.decision_time = run.decision_time
        row.model_version = run.model_version
        row.config_json = dict(run.config_json)
        row.input_count = int(run.input_count)
        row.eligible_count = int(run.eligible_count)
        row.shortlist_count = int(run.shortlist_count)
        row.status = run.status
        row.source_metadata_json = dict(run.source_metadata_json)
        row.error_metadata_json = dict(run.error_metadata_json)
        row.started_at = run.started_at
        row.completed_at = run.completed_at

        for ranking in rankings:
            if ranking.universe_ranking_run_id != run.universe_ranking_run_id:
                raise ValueError("ranking_run_id_mismatch")
            ranking_row = self.session.query(UniverseRanking).filter_by(
                universe_ranking_run_id=run_id,
                ticker=ranking.ticker,
            ).one_or_none()
            if ranking_row is None:
                ranking_row = UniverseRanking(
                    universe_ranking_id=_to_uuid(ranking.universe_ranking_id),
                    universe_ranking_run_id=run_id,
                    ticker=ranking.ticker,
                )
                self.session.add(ranking_row)
            ranking_row.decision_time = ranking.decision_time
            ranking_row.status = ranking.status
            ranking_row.overall_rank = ranking.overall_rank
            ranking_row.overall_percentile = _decimal_or_none(ranking.overall_percentile)
            ranking_row.relative_strength_score = _decimal_or_none(ranking.relative_strength_score)
            ranking_row.data_confidence = _decimal_or_none(ranking.data_confidence)
            ranking_row.peer_group_type = ranking.peer_group_type
            ranking_row.peer_group_id = ranking.peer_group_id
            ranking_row.peer_group_size = ranking.peer_group_size
            ranking_row.is_automatic_shortlist = bool(ranking.is_automatic_shortlist)
            ranking_row.forced_inclusion_reasons_json = list(ranking.forced_inclusion_reasons)
            ranking_row.raw_metrics_json = dict(ranking.raw_metrics_json)
            ranking_row.normalized_metrics_json = dict(ranking.normalized_metrics_json)
            ranking_row.positive_contributors_json = list(ranking.positive_contributors_json)
            ranking_row.negative_contributors_json = list(ranking.negative_contributors_json)
            ranking_row.missing_inputs_json = list(ranking.missing_inputs)
            ranking_row.source_refs_json = list(ranking.source_refs)
            ranking_row.available_for_decision_at = ranking.available_for_decision_at
        self.session.flush()

    def load_universe_ranking_run(self, universe_ranking_run_id: str) -> UniverseRankingRunRecord | None:
        row = self.session.query(UniverseRankingRun).filter_by(
            universe_ranking_run_id=_to_uuid(universe_ranking_run_id)
        ).one_or_none()
        return self._universe_ranking_run_record(row) if row is not None else None

    def load_latest_universe_ranking_run(
        self,
        *,
        decision_time: datetime,
    ) -> UniverseRankingRunRecord | None:
        rows = [
            row
            for row in self.session.query(UniverseRankingRun).all()
            if row.decision_time <= decision_time
        ]
        if not rows:
            return None
        return self._universe_ranking_run_record(
            max(rows, key=lambda row: (row.decision_time, str(row.universe_ranking_run_id)))
        )

    def load_universe_rankings(
        self,
        universe_ranking_run_id: str,
    ) -> tuple[UniverseRankingRecord, ...]:
        rows = self.session.query(UniverseRanking).filter_by(
            universe_ranking_run_id=_to_uuid(universe_ranking_run_id)
        ).all()
        return tuple(
            self._universe_ranking_record(row)
            for row in sorted(rows, key=lambda row: (row.overall_rank is None, row.overall_rank or 0, row.ticker))
        )

    def load_peer_basket_memberships(
        self,
        *,
        decision_time: datetime,
    ) -> tuple[PeerBasketMembership, ...]:
        """Return the latest decision-available version of every configured basket."""
        eligible = [
            row
            for row in self.session.query(PeerBasket).all()
            if row.trade_date <= decision_time.date()
        ]
        latest_by_basket: dict[tuple[str, str], PeerBasket] = {}
        for row in eligible:
            key = (row.basket_key, row.version)
            current = latest_by_basket.get(key)
            if current is None or row.trade_date > current.trade_date:
                latest_by_basket[key] = row
        memberships: list[PeerBasketMembership] = []
        for row in latest_by_basket.values():
            valid_from = datetime.combine(row.trade_date, time.min, tzinfo=timezone.utc)
            for ticker in row.members_json or ():
                memberships.append(
                    PeerBasketMembership(
                        ticker=str(ticker),
                        basket_id=f"{row.basket_key}:{row.version}",
                        valid_from=valid_from,
                        valid_to=None,
                        available_for_decision_at=valid_from,
                        source_refs=tuple(row.source_refs_json or ()),
                    )
                )
        return tuple(sorted(memberships, key=lambda item: (item.basket_id, item.ticker)))

    def load_ticker_relationships(
        self,
        *,
        decision_time: datetime,
    ) -> tuple[TickerRelationship, ...]:
        """Load only relationships whose validity window is open at decision time."""
        rows = [
            row
            for row in self.session.query(TickerRelationshipModel).all()
            if row.valid_from <= decision_time
            and (row.valid_until is None or row.valid_until >= decision_time)
        ]
        return tuple(
            TickerRelationship(
                ticker=row.source_ticker,
                relationship_type=row.relationship_type,
                relationship_id=row.theme_id or row.target_ticker,
                valid_from=row.valid_from,
                valid_to=row.valid_until,
                available_for_decision_at=row.valid_from,
                source_refs=tuple(row.source_refs_json or ()),
            )
            for row in sorted(rows, key=lambda item: (item.source_ticker, item.relationship_type, item.target_ticker))
        )

    @staticmethod
    def _universe_ranking_run_record(row: UniverseRankingRun) -> UniverseRankingRunRecord:
        return UniverseRankingRunRecord(
            universe_ranking_run_id=str(row.universe_ranking_run_id),
            universe_snapshot_id=str(row.universe_snapshot_id),
            decision_time=row.decision_time,
            model_version=row.model_version,
            config_json=dict(row.config_json or {}),
            input_count=int(row.input_count),
            eligible_count=int(row.eligible_count),
            shortlist_count=int(row.shortlist_count),
            status=row.status,
            source_metadata_json=dict(row.source_metadata_json or {}),
            error_metadata_json=dict(row.error_metadata_json or {}),
            started_at=row.started_at,
            completed_at=row.completed_at,
        )

    @staticmethod
    def _universe_ranking_record(row: UniverseRanking) -> UniverseRankingRecord:
        return UniverseRankingRecord(
            universe_ranking_id=str(row.universe_ranking_id),
            universe_ranking_run_id=str(row.universe_ranking_run_id),
            ticker=row.ticker,
            decision_time=row.decision_time,
            status=row.status,
            overall_rank=row.overall_rank,
            overall_percentile=float(row.overall_percentile) if row.overall_percentile is not None else None,
            relative_strength_score=(
                float(row.relative_strength_score) if row.relative_strength_score is not None else None
            ),
            data_confidence=float(row.data_confidence) if row.data_confidence is not None else None,
            peer_group_type=row.peer_group_type,
            peer_group_id=row.peer_group_id,
            peer_group_size=row.peer_group_size,
            is_automatic_shortlist=bool(row.is_automatic_shortlist),
            forced_inclusion_reasons=tuple(row.forced_inclusion_reasons_json or ()),
            raw_metrics_json=dict(row.raw_metrics_json or {}),
            normalized_metrics_json=dict(row.normalized_metrics_json or {}),
            positive_contributors_json=tuple(row.positive_contributors_json or ()),
            negative_contributors_json=tuple(row.negative_contributors_json or ()),
            missing_inputs=tuple(row.missing_inputs_json or ()),
            source_refs=tuple(row.source_refs_json or ()),
            available_for_decision_at=row.available_for_decision_at,
        )
    def save_prompt_template(self, template: object) -> None:
        row = self.session.query(LlmPromptTemplate).filter_by(
            prompt_id=str(template.prompt_id),
            prompt_version=str(template.prompt_version),
        ).one_or_none()
        if row is None:
            row = LlmPromptTemplate(prompt_template_id=uuid.uuid4())
            self.session.add(row)
        row.prompt_id = str(template.prompt_id)
        row.prompt_version = str(template.prompt_version)
        row.pipeline_name = str(template.pipeline_name)
        row.template_path = str(template.template_path)
        row.template_hash = str(template.template_hash)
        row.git_commit = None
        row.output_schema_id = str(template.output_schema_id)
        row.output_schema_version = str(template.output_schema_version)
        row.lifecycle_status = "active"
        self.session.flush()
        self._last_prompt_template_id = row.prompt_template_id

    def save_prompt_run(self, prompt_run: object) -> None:
        prompt_template_id = getattr(self, "_last_prompt_template_id", None)
        if prompt_template_id is None:
            raise RuntimeError("prompt_template_must_be_saved_before_prompt_run")
        row = LlmPromptRun(
            prompt_run_id=uuid.uuid4(),
            prompt_template_id=prompt_template_id,
            pipeline_name=str(prompt_run.pipeline_name),
            pipeline_run_id=None,
            rendered_prompt_hash=str(prompt_run.rendered_prompt_hash),
            rendered_prompt_redacted=str(prompt_run.rendered_prompt_redacted),
            input_context_json=dict(prompt_run.input_context_json or {}),
            raw_output_text=str(prompt_run.raw_output_text),
            parsed_output_json=dict(prompt_run.parsed_output_json or {}),
            parse_status=str(prompt_run.parse_status),
            validation_errors_json=list(prompt_run.validation_errors_json or ()),
            fallback_action=_string_or_none(prompt_run.fallback_action),
            error_message=_string_or_none(prompt_run.error_message),
        )
        self.session.add(row)
        self.session.flush()
        self._last_prompt_run_id = row.prompt_run_id

    def save_usage_events(self, usage_events: list[object] | tuple[object, ...]) -> None:
        if not usage_events:
            return
        prompt_run_id = getattr(self, "_last_prompt_run_id", None)
        if prompt_run_id is None:
            raise RuntimeError("prompt_run_must_be_saved_before_usage_events")
        for event in usage_events:
            self.session.add(
                LlmUsageEvent(
                    llm_usage_event_id=uuid.uuid4(),
                    prompt_run_id=prompt_run_id,
                    provider=str(event.provider),
                    model=str(event.model),
                    prompt_tokens=int(event.prompt_tokens),
                    completion_tokens=int(event.completion_tokens),
                    total_tokens=int(event.total_tokens),
                    estimated_cost=Decimal(str(event.estimated_cost)),
                    latency_ms=int(event.latency_ms),
                    retry_count=int(event.retry_count),
                    status=str(event.status),
                )
            )
        self.session.flush()

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
        row.key_drivers_json = list(decision.key_drivers)
        row.counterarguments_json = list(decision.counterarguments)
        row.invalidators_json = list(decision.invalidators)
        row.prompt_run_id = None
        row.fallback_action = decision.metadata_json.get("fallback_action")
        row.paper_trade_authorized = bool(
            getattr(decision, "paper_trade_authorized", decision.metadata_json.get("paper_trade_authorized", False))
        )
        row.context_snapshot_json = {
            **dict(decision.context_snapshot_json),
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
    def save_execution_attempt(self, attempt: ExecutionAttemptRecord) -> None:
        row = self.session.query(ExecutionAttempt).filter_by(
            execution_attempt_id=_to_uuid(attempt.execution_attempt_id)
        ).one_or_none()
        if row is None:
            row = ExecutionAttempt(execution_attempt_id=_to_uuid(attempt.execution_attempt_id))
            self.session.add(row)
        row.trading_decision_id = _to_uuid_or_none(attempt.trading_decision_id)
        row.risk_decision_id = _to_uuid_or_none(attempt.risk_decision_id)
        row.paper_order_id = _to_uuid_or_none(attempt.paper_order_id)
        row.paper_option_order_id = _to_uuid_or_none(attempt.paper_option_order_id)
        row.ticker = attempt.ticker
        row.strategy_id = attempt.strategy_id
        row.trade_identity = attempt.trade_identity
        row.instrument_type = attempt.instrument_type
        row.phase = attempt.phase
        row.action = attempt.action
        row.outcome = attempt.outcome
        row.reason_code = attempt.reason_code
        row.detail = attempt.detail
        row.created_at = attempt.created_at
        row.metadata_json = dict(attempt.metadata_json)
        self.session.flush()
    def load_manual_review_audit_rows(self) -> tuple[ManualReviewAuditRow, ...]:
        active_requests = (
            self.session.query(ManualTickerRequest)
            .filter(ManualTickerRequest.status == "active")
            .all()
        )
        active_request_ids = [
            request_id
            for row in active_requests
            if (request_id := _to_uuid_or_none(getattr(row, "manual_ticker_request_id", None))) is not None
        ]
        decisions_by_request_id: dict[str, Any] = {}
        decision_rows = (
            self.session.query(TradingDecision)
            .filter(TradingDecision.manual_request_id.in_(active_request_ids))
            .all()
            if active_request_ids
            else ()
        )
        for row in decision_rows:
            request_id = _string_or_none(getattr(row, "manual_request_id", None))
            if request_id is None:
                continue
            current = decisions_by_request_id.get(request_id)
            if current is None or _latest_row_sort_key(
                row,
                "decision_time",
                "trading_decision_id",
            ) > _latest_row_sort_key(current, "decision_time", "trading_decision_id"):
                decisions_by_request_id[request_id] = row
        risk_ids = [
            risk_id
            for decision in decisions_by_request_id.values()
            if (risk_id := _to_uuid_or_none(getattr(decision, "risk_decision_id", None))) is not None
        ]
        risk_by_id = {
            _string_or_none(getattr(row, "risk_decision_id", None)): row
            for row in (
                self.session.query(RiskDecision)
                .filter(RiskDecision.risk_decision_id.in_(risk_ids))
                .all()
                if risk_ids
                else ()
            )
            if _string_or_none(getattr(row, "risk_decision_id", None)) is not None
        }
        decision_ids = [
            decision_id
            for decision in decisions_by_request_id.values()
            if (decision_id := _to_uuid_or_none(getattr(decision, "trading_decision_id", None))) is not None
        ]
        orders_by_decision_id: dict[str, Any] = {}
        order_rows = (
            self.session.query(PaperOrder)
            .filter(PaperOrder.trading_decision_id.in_(decision_ids))
            .all()
            if decision_ids
            else ()
        )
        for row in order_rows:
            decision_id = _string_or_none(getattr(row, "trading_decision_id", None))
            if decision_id is None:
                continue
            current = orders_by_decision_id.get(decision_id)
            if current is None or _latest_row_sort_key(
                row,
                "created_at",
                "paper_order_id",
            ) > _latest_row_sort_key(current, "created_at", "paper_order_id"):
                orders_by_decision_id[decision_id] = row
        order_ids = [
            order_id
            for order in orders_by_decision_id.values()
            if (order_id := _to_uuid_or_none(getattr(order, "paper_order_id", None))) is not None
        ]
        executions_by_order_id: dict[str, Any] = {}
        execution_rows = (
            self.session.query(PaperExecution)
            .filter(PaperExecution.paper_order_id.in_(order_ids))
            .all()
            if order_ids
            else ()
        )
        for row in execution_rows:
            order_id = _string_or_none(getattr(row, "paper_order_id", None))
            if order_id is None:
                continue
            current = executions_by_order_id.get(order_id)
            if current is None or _latest_row_sort_key(
                row,
                "executed_at",
                "paper_execution_id",
            ) > _latest_row_sort_key(current, "executed_at", "paper_execution_id"):
                executions_by_order_id[order_id] = row

        audit_rows: list[ManualReviewAuditRow] = []
        for request in sorted(
            active_requests,
            key=lambda row: (
                -(
                    getattr(row, "created_at", None).timestamp()
                    if getattr(row, "created_at", None) is not None
                    else 0.0
                ),
                str(getattr(row, "ticker", "") or ""),
            ),
        ):
            request_id = str(request.manual_ticker_request_id)
            decision = decisions_by_request_id.get(request_id)
            risk = risk_by_id.get(_string_or_none(getattr(decision, "risk_decision_id", None)))
            order = orders_by_decision_id.get(_string_or_none(getattr(decision, "trading_decision_id", None)))
            execution = executions_by_order_id.get(_string_or_none(getattr(order, "paper_order_id", None)))
            latest_signal_snapshot_id = _string_or_none(getattr(request, "latest_signal_snapshot_id", None))
            if latest_signal_snapshot_id is None and decision is not None:
                latest_signal_snapshot_id = _string_or_none(
                    dict(getattr(decision, "metadata_json", {}) or {}).get("signal_snapshot_id")
                )
            execution_path_state, latest_block_reason = _manual_review_execution_path_state(
                request=request,
                decision=decision,
                risk=risk,
                order=order,
                execution=execution,
                latest_signal_snapshot_id=latest_signal_snapshot_id,
            )
            audit_rows.append(
                ManualReviewAuditRow(
                    manual_ticker_request_id=request_id,
                    ticker=request.ticker,
                    reason=request.reason,
                    mode=request.mode,
                    status=request.status,
                    created_at=request.created_at,
                    last_evaluated_at=request.last_evaluated_at,
                    latest_result_status=request.latest_result_status,
                    latest_signal_snapshot_id=latest_signal_snapshot_id,
                    latest_trading_decision_id=_string_or_none(getattr(decision, "trading_decision_id", None)),
                    latest_decision_action=(getattr(decision, "decision", None) if decision is not None else None),
                    latest_risk_outcome=(getattr(risk, "status", None) if risk is not None else None),
                    latest_order_status=(getattr(order, "status", None) if order is not None else None),
                    latest_execution_status=(
                        "filled"
                        if execution is not None
                        else ("rejected" if getattr(order, "status", None) == "rejected" else None)
                    ),
                    latest_execution_time=getattr(execution, "executed_at", None),
                    execution_path_state=execution_path_state,
                    latest_block_reason=latest_block_reason,
                    linkage_state=_manual_review_linkage_state(
                        latest_signal_snapshot_id=latest_signal_snapshot_id,
                        decision=decision,
                        risk=risk,
                        order=order,
                        execution=execution,
                    ),
                )
            )
        return tuple(audit_rows)
