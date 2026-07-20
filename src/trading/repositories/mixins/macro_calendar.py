from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import or_

from src.db.models.trading import (
    CalendarEvent,
    EventNewsItem,
    MacroSnapshot,
    PortfolioEventRiskAssessment,
    SocialMacroItem,
)
from src.trading.events import CalendarEventRecord, PortfolioEventRiskAssessmentRecord
from src.trading.macro import MacroSnapshotRecord
from src.trading.repositories._base_common import _to_uuid, _to_uuid_or_none
from src.trading.repositories._base_records import (
    _calendar_event_record,
    _macro_snapshot_record,
    _portfolio_event_risk_assessment_record,
    _portfolio_event_risk_assessment_storage_key,
)


class MacroCalendarRepositoryMixin:
    def save_macro_snapshot(self, snapshot: MacroSnapshotRecord) -> None:
        row = None
        natural_key = (snapshot.trade_date, snapshot.snapshot_time, snapshot.source_set_key)
        for candidate in self.session.query(MacroSnapshot).all():
            if (
                candidate.trade_date,
                candidate.snapshot_time,
                candidate.source_set_key,
            ) == natural_key:
                row = candidate
                break
        if row is None:
            row = self.session.query(MacroSnapshot).filter_by(
                macro_snapshot_id=_to_uuid(snapshot.macro_snapshot_id)
            ).one_or_none()
        if row is None:
            row = MacroSnapshot(macro_snapshot_id=_to_uuid(snapshot.macro_snapshot_id))
            self.session.add(row)
        row.trade_date = snapshot.trade_date
        row.snapshot_time = snapshot.snapshot_time
        row.regime = snapshot.regime
        row.risk_budget_multiplier = Decimal(str(snapshot.risk_budget_multiplier))
        row.volatility_state = snapshot.volatility_state
        row.rates_state = snapshot.rates_state
        row.liquidity_state = snapshot.liquidity_state
        row.source_set_key = snapshot.source_set_key
        row.blocked_strategy_tags_json = list(snapshot.blocked_strategy_tags)
        row.invalidators_json = list(snapshot.invalidators)
        row.source_freshness_json = dict(snapshot.source_freshness)
        row.metadata_json = dict(snapshot.metadata_json)
        self.session.flush()
    def load_latest_macro_snapshot(
        self,
        *,
        trade_date: date,
        decision_time: datetime | None = None,
    ) -> MacroSnapshotRecord | None:
        query = self.session.query(MacroSnapshot).filter(MacroSnapshot.trade_date == trade_date)
        if decision_time is not None:
            query = query.filter(MacroSnapshot.snapshot_time <= decision_time)
        row = query.order_by(MacroSnapshot.snapshot_time.desc()).first()
        if row is None:
            return None
        return _macro_snapshot_record(row)
    def save_calendar_events(
        self,
        events: list[CalendarEventRecord] | tuple[CalendarEventRecord, ...],
    ) -> None:
        for event in events:
            row = None
            for candidate in self.session.query(CalendarEvent).all():
                if candidate.event_key == event.event_key:
                    row = candidate
                    break
            if row is None:
                row = self.session.query(CalendarEvent).filter_by(
                    calendar_event_id=_to_uuid(event.calendar_event_id)
                ).one_or_none()
            if row is None:
                row = CalendarEvent(calendar_event_id=_to_uuid(event.calendar_event_id))
                self.session.add(row)
            row.event_key = event.event_key
            row.event_type = event.event_type
            row.ticker = event.ticker
            row.event_time = event.event_time
            row.published_at = event.published_at
            row.available_for_decision_at = event.available_for_decision_at
            row.title = event.title
            row.severity_hint = event.severity_hint
            row.source = event.source
            row.metadata_json = dict(event.metadata_json)
        self.session.flush()
    def load_calendar_events(
        self,
        *,
        decision_time: datetime,
        ticker: str | None = None,
        event_time_start: datetime | None = None,
        event_time_end: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[CalendarEventRecord, ...]:
        symbol = ticker.strip().upper() if isinstance(ticker, str) else None
        query = self.session.query(CalendarEvent).filter(
            CalendarEvent.available_for_decision_at <= decision_time
        )
        if symbol is not None:
            query = query.filter(
                or_(CalendarEvent.ticker.is_(None), CalendarEvent.ticker == symbol)
            )
        if event_time_start is not None:
            query = query.filter(CalendarEvent.event_time >= event_time_start)
        if event_time_end is not None:
            query = query.filter(CalendarEvent.event_time <= event_time_end)
        query = query.order_by(CalendarEvent.event_time, CalendarEvent.event_key)
        if limit is not None:
            query = query.limit(limit)
        rows = query.all()
        return tuple(_calendar_event_record(row) for row in rows)
    def save_portfolio_event_risk_assessments(
        self,
        assessments: list[PortfolioEventRiskAssessmentRecord] | tuple[PortfolioEventRiskAssessmentRecord, ...],
    ) -> None:
        for assessment in assessments:
            assessment_key = _portfolio_event_risk_assessment_storage_key(assessment)
            row = None
            for candidate in self.session.query(PortfolioEventRiskAssessment).all():
                if candidate.assessment_key == assessment_key:
                    row = candidate
                    break
            if row is None and assessment.portfolio_event_risk_assessment_id is not None:
                row = self.session.query(PortfolioEventRiskAssessment).filter_by(
                    portfolio_event_risk_assessment_id=_to_uuid(
                        assessment.portfolio_event_risk_assessment_id
                    )
                ).one_or_none()
            if row is None:
                row = PortfolioEventRiskAssessment(
                    portfolio_event_risk_assessment_id=_to_uuid(
                        assessment.portfolio_event_risk_assessment_id or assessment_key
                    )
                )
                self.session.add(row)
            row.assessment_key = assessment_key
            row.calendar_event_id = _to_uuid_or_none(assessment.calendar_event_id)
            row.portfolio_risk_snapshot_id = _to_uuid_or_none(assessment.portfolio_risk_snapshot_id)
            row.decision_time = assessment.decision_time
            row.available_for_decision_at = assessment.available_for_decision_at or assessment.decision_time
            row.ticker = assessment.ticker
            row.risk_source = assessment.risk_source
            row.severity = assessment.severity
            row.event_type = assessment.event_type
            row.days_until_event = assessment.days_until_event
            row.affects_existing_position = bool(assessment.affects_existing_position)
            row.affects_pending_trade = bool(assessment.affects_pending_trade)
            row.recommended_action = assessment.recommended_action
            row.rationale = assessment.rationale
            row.metadata_json = dict(assessment.metadata_json)
        self.session.flush()
    def load_portfolio_event_risk_assessments(
        self,
        *,
        decision_time: datetime,
        ticker: str | None = None,
        available_since: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[PortfolioEventRiskAssessmentRecord, ...]:
        symbol = ticker.strip().upper() if isinstance(ticker, str) else None
        query = self.session.query(PortfolioEventRiskAssessment).filter(
            PortfolioEventRiskAssessment.available_for_decision_at <= decision_time
        )
        if symbol is not None:
            query = query.filter(PortfolioEventRiskAssessment.ticker == symbol)
        if available_since is not None:
            query = query.filter(PortfolioEventRiskAssessment.available_for_decision_at >= available_since)
        query = query.order_by(
            PortfolioEventRiskAssessment.available_for_decision_at,
            PortfolioEventRiskAssessment.portfolio_event_risk_assessment_id,
        )
        if limit is not None:
            query = query.limit(limit)
        rows = query.all()
        return tuple(_portfolio_event_risk_assessment_record(row) for row in rows)
    def load_decision_visible_macro_news(
        self,
        *,
        decision_time: datetime,
        ticker: str | None = None,
        available_since: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[object, ...]:
        symbol = ticker.strip().upper() if isinstance(ticker, str) else None
        query = self.session.query(SocialMacroItem).filter(
            SocialMacroItem.available_for_decision_at <= decision_time
        )
        if symbol is not None:
            query = query.filter(SocialMacroItem.ticker == symbol)
        if available_since is not None:
            query = query.filter(SocialMacroItem.available_for_decision_at >= available_since)
        query = query.order_by(
            SocialMacroItem.available_for_decision_at.desc(),
            SocialMacroItem.social_macro_item_id,
        )
        if limit is not None:
            query = query.limit(limit)
        rows = query.all()
        rows.sort(key=lambda row: (row.available_for_decision_at, str(row.social_macro_item_id)))
        return tuple(self._to_social_macro_item_record(row) for row in rows)
    def load_decision_visible_event_news(
        self,
        *,
        decision_time: datetime,
        ticker: str | None = None,
        available_since: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[object, ...]:
        symbol = ticker.strip().upper() if isinstance(ticker, str) else None
        query = self.session.query(EventNewsItem).filter(
            EventNewsItem.available_for_decision_at <= decision_time
        )
        if symbol is not None:
            query = query.filter(
                or_(EventNewsItem.ticker == symbol, EventNewsItem.source_ticker == symbol)
            )
        if available_since is not None:
            query = query.filter(EventNewsItem.available_for_decision_at >= available_since)
        query = query.order_by(
            EventNewsItem.available_for_decision_at.desc(),
            EventNewsItem.event_news_item_id,
        )
        if limit is not None:
            query = query.limit(limit)
        rows = query.all()
        rows.sort(key=lambda row: (row.available_for_decision_at, str(row.event_news_item_id)))
        return tuple(self._to_event_news_item_record(row) for row in rows)

    def load_decision_available_risk_macro_context(
        self,
        *,
        trade_date: date,
        decision_time: datetime,
        ticker: str | None = None,
        event_time_start: datetime | None = None,
        event_time_end: datetime | None = None,
        news_available_since: datetime | None = None,
        news_limit: int | None = None,
        assessment_available_since: datetime | None = None,
        assessment_limit: int | None = None,
    ) -> dict[str, object]:
        return {
            "macro_snapshot": self.load_latest_macro_snapshot(
                trade_date=trade_date,
                decision_time=decision_time,
            ),
            "calendar_events": self.load_calendar_events(
                decision_time=decision_time,
                ticker=ticker,
                event_time_start=event_time_start,
                event_time_end=event_time_end,
            ),
            "portfolio_event_risk_assessments": self.load_portfolio_event_risk_assessments(
                decision_time=decision_time,
                ticker=ticker,
                available_since=assessment_available_since,
                limit=assessment_limit,
            ),
            "macro_news": self.load_decision_visible_macro_news(
                decision_time=decision_time,
                ticker=ticker,
                available_since=news_available_since,
                limit=news_limit,
            ),
            "event_news": self.load_decision_visible_event_news(
                decision_time=decision_time,
                ticker=ticker,
                available_since=news_available_since,
                limit=news_limit,
            ),
        }
