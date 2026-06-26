from __future__ import annotations

from src.trading.repositories._base import *  # noqa: F401,F403


class IntradayRepositoryMixin:
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
    def load_latest_intraday_signal_snapshots_for_tickers(
        self,
        *,
        tickers: tuple[str, ...],
        trade_date: date,
    ) -> dict[str, IntradaySignalSnapshotRecord]:
        selected_by_ticker: dict[str, IntradaySignalSnapshotRecord] = {}
        ticker_set = {ticker.strip().upper() for ticker in tickers}
        for row in self.session.query(IntradaySignalSnapshot).all():
            if row.ticker not in ticker_set:
                continue
            if row.decision_time.date() != trade_date:
                continue
            snapshot = IntradaySignalSnapshotRecord(
                intraday_signal_snapshot_id=str(row.intraday_signal_snapshot_id),
                intraday_signal_scan_id=str(row.intraday_signal_scan_id),
                ticker=row.ticker,
                decision_time=row.decision_time,
                baseline_signal_snapshot_id=str(row.baseline_signal_snapshot_id),
                previous_intraday_snapshot_id=(
                    str(row.previous_intraday_snapshot_id) if row.previous_intraday_snapshot_id is not None else None
                ),
                refreshed_signals_json=dict(row.refreshed_signals_json or {}),
                carried_forward_signals_json=dict(row.carried_forward_signals_json or {}),
                delta_vs_baseline_json=dict(row.delta_vs_baseline_json or {}),
                delta_vs_previous_json=dict(row.delta_vs_previous_json or {}),
                source_freshness_json=dict(row.source_freshness_json or {}),
                metadata_json=dict(row.metadata_json or {}),
                created_at=row.created_at,
            )
            current = selected_by_ticker.get(snapshot.ticker)
            if current is None or snapshot.decision_time > current.decision_time:
                selected_by_ticker[snapshot.ticker] = snapshot
        return selected_by_ticker
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
    def load_existing_news_alert_dedupe_keys(
        self,
        *,
        tickers: tuple[str, ...],
        trade_date: date,
    ) -> frozenset[str]:
        ticker_set = {ticker.strip().upper() for ticker in tickers}
        return frozenset(
            row.dedupe_key
            for row in self.session.query(NewsAlert).all()
            if row.ticker in ticker_set and row.created_at.date() == trade_date
        )
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
    def load_intraday_scope(self, *, trade_date: date) -> tuple[str, ...]:
        tickers: set[str] = set()
        tickers.update(position.ticker for position in self.load_paper_positions())
        tickers.update(position.ticker for position in self.load_paper_option_positions())
        tickers.update(
            row.ticker
            for row in self.session.query(PaperOrder).all()
            if row.trade_date == trade_date and row.ticker
        )
        tickers.update(
            row.ticker
            for row in self.session.query(CandidateScore).all()
            if row.decision_time.date() == trade_date and row.ticker
        )
        tickers.update(
            row.ticker
            for row in self.session.query(TradingDecision).all()
            if row.decision_time.date() == trade_date and row.ticker
        )
        tickers.update(
            row.ticker
            for row in self.session.query(ManualTickerRequest).filter_by(status="active").all()
            if row.ticker
        )
        return tuple(sorted(tickers))
    def load_intraday_request_contexts(
        self,
        *,
        tickers: tuple[str, ...],
        trade_date: date,
    ) -> dict[str, Any]:
        ticker_set = {ticker.strip().upper() for ticker in tickers}
        contexts: dict[str, Any] = {}
        stock_positions_by_ticker = {position.ticker: position for position in self.load_paper_positions()}
        option_positions_by_ticker = {position.ticker: position for position in self.load_paper_option_positions()}
        manual_request_by_ticker: dict[str, Any] = {}
        for row in self.session.query(ManualTickerRequest).filter_by(status="active").all():
            if row.ticker not in ticker_set:
                continue
            current = manual_request_by_ticker.get(row.ticker)
            if current is None or (row.created_at, str(row.manual_ticker_request_id)) > (
                current.created_at,
                str(current.manual_ticker_request_id),
            ):
                manual_request_by_ticker[row.ticker] = row
        classifications_by_id = {
            str(row.trade_classification_id): row
            for row in self.session.query(TradeClassification).all()
            if row.ticker in ticker_set and row.decision_time.date() == trade_date
        }
        latest_candidate_by_ticker: dict[str, Any] = {}
        for row in self.session.query(CandidateScore).all():
            if row.ticker not in ticker_set or row.decision_time.date() != trade_date:
                continue
            current = latest_candidate_by_ticker.get(row.ticker)
            if current is None or row.available_for_decision_at > current.available_for_decision_at:
                latest_candidate_by_ticker[row.ticker] = row
        latest_decision_by_ticker: dict[str, Any] = {}
        for row in self.session.query(TradingDecision).all():
            if row.ticker not in ticker_set or row.decision_time.date() != trade_date:
                continue
            current = latest_decision_by_ticker.get(row.ticker)
            if current is None or row.available_for_decision_at > current.available_for_decision_at:
                latest_decision_by_ticker[row.ticker] = row

        for ticker in ticker_set:
            decision = latest_decision_by_ticker.get(ticker)
            candidate = latest_candidate_by_ticker.get(ticker)
            stock_position = stock_positions_by_ticker.get(ticker)
            option_position = option_positions_by_ticker.get(ticker)
            position = option_position or stock_position
            manual_request = manual_request_by_ticker.get(ticker)
            manual_mode = manual_request.mode if manual_request is not None else None
            classification = None
            if decision is not None and decision.trade_classification_id is not None:
                classification = classifications_by_id.get(str(decision.trade_classification_id))
            metadata_json = _intraday_context_metadata(
                decision=decision,
                option_position=option_position,
            )
            if manual_request is not None:
                metadata_json = {
                    **dict(metadata_json or {}),
                    "manual_request_last_evaluated_at": (
                        manual_request.last_evaluated_at.isoformat()
                        if manual_request.last_evaluated_at is not None
                        else None
                    ),
                    "manual_request_latest_result_status": manual_request.latest_result_status,
                    "manual_request_latest_signal_snapshot_id": (
                        str(manual_request.latest_signal_snapshot_id)
                        if manual_request.latest_signal_snapshot_id is not None
                        else None
                    ),
                }
            selection_source = (
                "manual_request"
                if manual_request is not None
                else (
                    decision.selection_source
                    if decision is not None
                    else (
                        candidate.selection_source
                        if candidate is not None
                        else ("risk_manager" if position is not None else "scanner")
                    )
                )
            )
            if selection_source not in {"scanner", "manual_request", "watchlist_pin", "risk_manager"}:
                selection_source = "risk_manager" if position is not None else "scanner"
            instrument_type = "option" if option_position is not None else (decision.instrument_type if decision is not None else "stock")
            contexts[ticker] = SimpleNamespace(
                selection_source=selection_source,
                strategy_id=(
                    decision.strategy_id
                    if decision is not None
                    else (candidate.strategy_id if candidate is not None else "intraday_refresh_unknown")
                ),
                strategy_version=(
                    decision.strategy_version
                    if decision is not None
                    else (candidate.strategy_version if candidate is not None else "v1")
                ),
                expression_bucket_id=(
                    decision.expression_bucket_id
                    if decision is not None
                    else (classification.expression_bucket_id if classification is not None else "long_stock")
                ),
                expression_bucket_version=(
                    decision.expression_bucket_version
                    if decision is not None
                    else (classification.expression_bucket_version if classification is not None else "v1")
                ),
                trade_identity=(
                    position.trade_identity
                    if position is not None
                    else (
                        decision.trade_identity
                        if decision is not None
                        else (classification.trade_identity if classification is not None else "tactical_stock_trade")
                    )
                ),
                instrument_type=instrument_type,
                candidate_score=float(candidate.candidate_score) if candidate is not None else 0.0,
                target_weight=float(decision.target_weight) if decision is not None else 0.0,
                allow_open_new=bool(
                    manual_mode == "paper_trade_eligible"
                    or (decision is not None and bool(decision.paper_trade_authorized))
                ),
                manual_request_id=(
                    str(manual_request.manual_ticker_request_id)
                    if manual_request is not None
                    else None
                ),
                manual_request_mode=manual_mode,
                metadata_json=metadata_json,
            )
        return contexts
    def load_intraday_candidate_context(
        self,
        *,
        tickers: tuple[str, ...],
        trade_date: date,
    ) -> dict[str, tuple[str, ...]]:
        ticker_set = {ticker.strip().upper() for ticker in tickers}
        return {
            row.ticker: (row.ticker,)
            for row in self.session.query(CandidateScore).all()
            if row.ticker in ticker_set and row.decision_time.date() == trade_date
        }
