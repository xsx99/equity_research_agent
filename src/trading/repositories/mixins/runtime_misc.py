from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
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
    RiskDecision,
    TradingDecision,
    TradingRuntimeRun,
    UniverseFilterConfig,
    UniverseSnapshot,
    UniverseSymbol,
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
        active_requests = [
            row
            for row in self.session.query(ManualTickerRequest).all()
            if getattr(row, "status", None) == "active"
        ]
        decisions_by_request_id: dict[str, Any] = {}
        for row in self.session.query(TradingDecision).all():
            request_id = _string_or_none(getattr(row, "manual_request_id", None))
            if request_id is None:
                continue
            current = decisions_by_request_id.get(request_id)
            if current is None or _latest_row_sort_key(row, "decision_time", "trading_decision_id") > _latest_row_sort_key(
                current,
                "decision_time",
                "trading_decision_id",
            ):
                decisions_by_request_id[request_id] = row
        risk_by_id = {
            _string_or_none(getattr(row, "risk_decision_id", None)): row
            for row in self.session.query(RiskDecision).all()
            if _string_or_none(getattr(row, "risk_decision_id", None)) is not None
        }
        orders_by_decision_id: dict[str, Any] = {}
        for row in self.session.query(PaperOrder).all():
            decision_id = _string_or_none(getattr(row, "trading_decision_id", None))
            if decision_id is None:
                continue
            current = orders_by_decision_id.get(decision_id)
            if current is None or _latest_row_sort_key(row, "created_at", "paper_order_id") > _latest_row_sort_key(
                current,
                "created_at",
                "paper_order_id",
            ):
                orders_by_decision_id[decision_id] = row
        executions_by_order_id: dict[str, Any] = {}
        for row in self.session.query(PaperExecution).all():
            order_id = _string_or_none(getattr(row, "paper_order_id", None))
            if order_id is None:
                continue
            current = executions_by_order_id.get(order_id)
            if current is None or _latest_row_sort_key(row, "executed_at", "paper_execution_id") > _latest_row_sort_key(
                current,
                "executed_at",
                "paper_execution_id",
            ):
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
