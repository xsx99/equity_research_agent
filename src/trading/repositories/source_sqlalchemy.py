"""SQL-backed source artifact persistence and point-in-time reads."""
from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from src.db.models.insider_trades import InsiderTrade
from src.db.models.trading import (
    EventNewsItem,
    FundamentalSnapshot,
    MarketDailyBar,
    ProviderRequestRun,
    SocialMacroItem,
    SourceIngestionRun,
)
from src.trading.data_sources.provider_resilience import ProviderRequestRunRecord
from src.trading.signals.sources import (
    EventNewsItemRecord,
    FundamentalSnapshotRecord,
    MarketDailyBarRecord,
    SocialMacroItemRecord,
    SourceIngestionRunRecord,
    SourceRecord,
    source_record_from_event_news_item,
    source_record_from_fundamental_snapshot,
    source_record_from_insider_trade,
    source_record_from_social_macro_item,
)


class SQLAlchemySignalSourceRepository:
    """Persist normalized source artifacts and rebuild PIT source rows."""

    def __init__(self, session: Any) -> None:
        self.session = session
        self._runtime_records: list[SourceRecord] = []

    def add(self, *records: SourceRecord) -> None:
        """SourceIngestionService compatibility hook.

        Normalized source rows are persisted through dedicated table methods below.
        The live SQL adapter does not need an extra catch-all source table.
        """
        self._runtime_records.extend(records)

    def record_source_ingestion_run(self, run: SourceIngestionRunRecord) -> None:
        row = self.session.query(SourceIngestionRun).filter_by(
            source_ingestion_run_id=_to_uuid(run.source_ingestion_run_id)
        ).one_or_none()
        if row is None:
            row = SourceIngestionRun(source_ingestion_run_id=_to_uuid(run.source_ingestion_run_id))
            self.session.add(row)
        row.source_family = run.source_family
        row.run_type = run.run_type
        row.scope_json = dict(run.scope_json)
        row.provider = run.provider
        row.as_of = run.as_of
        row.started_at = run.started_at
        row.completed_at = run.completed_at
        row.status = run.status
        row.coverage_json = dict(run.coverage_json)
        row.error_code = run.error_code
        row.error_message = run.error_message
        row.metadata_json = dict(run.metadata_json)
        self.session.flush()

    def record_provider_request(self, run: ProviderRequestRunRecord) -> None:
        row_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{run.provider}:{run.endpoint}:{run.scope}:{run.started_at.isoformat()}",
        )
        row = self.session.query(ProviderRequestRun).filter_by(
            provider_request_run_id=row_id
        ).one_or_none()
        if row is None:
            row = ProviderRequestRun(provider_request_run_id=row_id)
            self.session.add(row)
        row.source_ingestion_run_id = _to_uuid_or_none(getattr(run, "source_ingestion_run_id", None))
        row.provider = run.provider
        row.endpoint = run.endpoint
        row.source_family = run.source_family
        row.scope_json = {"scope": run.scope}
        row.cache_status = run.cache_status
        row.request_count = int(run.request_count)
        row.budget_remaining = int(run.budget_remaining)
        row.retry_count = int(run.retry_count)
        row.backoff_ms = int(run.backoff_ms)
        row.latency_ms = int(run.latency_ms)
        row.status = run.status
        row.error_code = run.error_code
        row.circuit_state = run.circuit_state
        row.degraded_mode = bool(run.degraded_mode)
        row.started_at = run.started_at
        row.completed_at = run.completed_at
        row.metadata_json = {}
        self.session.flush()

    def save_fundamental_snapshot(self, snapshot: FundamentalSnapshotRecord) -> None:
        row = self.session.query(FundamentalSnapshot).filter_by(
            fundamental_snapshot_id=_to_uuid(snapshot.fundamental_snapshot_id)
        ).one_or_none()
        if row is None:
            row = FundamentalSnapshot(fundamental_snapshot_id=_to_uuid(snapshot.fundamental_snapshot_id))
            self.session.add(row)
        row.ticker = snapshot.ticker
        row.fiscal_period = snapshot.fiscal_period
        row.as_of_date = snapshot.as_of_date
        row.provider = snapshot.provider
        row.source_refs_json = list(snapshot.source_refs_json)
        row.event_time = snapshot.event_time
        row.published_at = snapshot.published_at
        row.ingested_at = snapshot.ingested_at
        row.available_for_decision_at = snapshot.available_for_decision_at
        row.raw_payload_ref = snapshot.raw_payload_ref
        row.normalized_metrics_json = dict(snapshot.normalized_metrics_json)
        self.session.flush()

    def save_market_daily_bars(
        self,
        bars: Iterable[MarketDailyBarRecord | Mapping[str, Any]]
        | MarketDailyBarRecord
        | Mapping[str, Any],
    ) -> None:
        """Insert or update daily bars by their ticker/date/provider natural key."""
        if isinstance(bars, (MarketDailyBarRecord, Mapping)):
            bars = (bars,)

        for value in bars:
            bar = _market_daily_bar_record(value)
            row = self.session.query(MarketDailyBar).filter_by(
                ticker=bar.ticker,
                trade_date=bar.trade_date,
                provider=bar.provider,
            ).one_or_none()
            if row is None:
                row = MarketDailyBar()
                self.session.add(row)
            row.ticker = bar.ticker
            row.trade_date = bar.trade_date
            row.open_raw = bar.open_raw
            row.high_raw = bar.high_raw
            row.low_raw = bar.low_raw
            row.close_raw = bar.close_raw
            row.adj_close = bar.adj_close
            row.volume_raw = bar.volume_raw
            row.dividend = bar.dividend
            row.stock_split = bar.stock_split
            row.provider = bar.provider
            row.ingested_at = bar.ingested_at
            row.available_for_decision_at = bar.available_for_decision_at
            row.quality_flags_json = bar.quality_flags_json
            if bar.created_at is not None:
                row.created_at = bar.created_at
        self.session.flush()

    def load_market_daily_bars(
        self,
        ticker: str,
        decision_time: datetime,
        limit: int,
    ) -> tuple[MarketDailyBarRecord, ...]:
        """Load the latest decision-visible bars in chronological order."""
        if limit <= 0:
            return ()
        symbol = ticker.strip().upper()
        rows = self.session.query(MarketDailyBar).filter(
            MarketDailyBar.ticker == symbol,
            MarketDailyBar.available_for_decision_at <= decision_time,
        ).all()
        eligible = [
            row
            for row in rows
            if row.ticker == symbol and row.available_for_decision_at <= decision_time
        ]
        eligible.sort(key=lambda row: row.trade_date, reverse=True)
        return tuple(
            self._to_market_daily_bar_record(row)
            for row in reversed(eligible[:limit])
        )

    def load_market_daily_bars_for_symbols(
        self,
        tickers: Iterable[str],
        decision_time: datetime,
        limit_per_ticker: int,
    ) -> dict[str, tuple[MarketDailyBarRecord, ...]]:
        """Load the latest decision-visible bars independently for each ticker."""
        if limit_per_ticker <= 0:
            return {}
        symbols = tuple(dict.fromkeys(ticker.strip().upper() for ticker in tickers))
        if not symbols:
            return {}
        symbol_set = set(symbols)
        rows = self.session.query(MarketDailyBar).filter(
            MarketDailyBar.ticker.in_(symbol_set),
            MarketDailyBar.available_for_decision_at <= decision_time,
        ).all()
        grouped: dict[str, list[MarketDailyBar]] = {symbol: [] for symbol in symbols}
        for row in rows:
            if (
                row.ticker in symbol_set
                and row.available_for_decision_at <= decision_time
            ):
                grouped[row.ticker].append(row)

        result: dict[str, tuple[MarketDailyBarRecord, ...]] = {}
        for symbol, symbol_rows in grouped.items():
            symbol_rows.sort(key=lambda row: row.trade_date, reverse=True)
            selected = symbol_rows[:limit_per_ticker]
            if selected:
                result[symbol] = tuple(
                    self._to_market_daily_bar_record(row)
                    for row in reversed(selected)
                )
        return result

    def save_event_news_item(self, item: EventNewsItemRecord) -> None:
        row = self.session.query(EventNewsItem).filter_by(
            event_news_item_id=_to_uuid(item.event_news_item_id)
        ).one_or_none()
        if row is None:
            row = EventNewsItem(event_news_item_id=_to_uuid(item.event_news_item_id))
            self.session.add(row)
        row.ticker = item.ticker
        row.source_ticker = item.source_ticker
        row.event_type = item.event_type
        row.direction = item.direction
        row.sentiment = item.sentiment
        row.importance = item.importance
        row.headline = item.headline
        row.summary = item.summary
        row.provider = item.provider
        row.source_refs_json = list(item.source_refs_json)
        row.dedupe_key = item.dedupe_key
        row.event_time = item.event_time
        row.published_at = item.published_at
        row.ingested_at = item.ingested_at
        row.available_for_decision_at = item.available_for_decision_at
        row.raw_payload_ref = item.raw_payload_ref
        row.metadata_json = dict(item.metadata_json)
        self.session.flush()

    def save_social_macro_item(self, item: SocialMacroItemRecord) -> None:
        row = self.session.query(SocialMacroItem).filter_by(
            social_macro_item_id=_to_uuid(item.social_macro_item_id)
        ).one_or_none()
        if row is None:
            row = SocialMacroItem(social_macro_item_id=_to_uuid(item.social_macro_item_id))
            self.session.add(row)
        row.ticker = item.ticker
        row.category = item.category
        row.source_type = item.source_type
        row.source_key = item.source_key
        row.provider = item.provider
        row.title = item.title
        row.summary = item.summary
        row.direction = item.direction
        row.sentiment_direction = item.sentiment_direction
        row.importance_score = item.importance_score
        row.importance_label = item.importance_label
        row.policy_headwind_flag = item.policy_headwind_flag
        row.policy_tailwind_flag = item.policy_tailwind_flag
        row.explicit_ticker_mention_flag = item.explicit_ticker_mention_flag
        row.explicit_theme_mention_flag = item.explicit_theme_mention_flag
        row.theme_tags_json = list(item.theme_tags_json)
        row.company_name_mentions_json = list(item.company_name_mentions_json)
        row.source_refs_json = list(item.source_refs_json)
        row.dedupe_key = item.dedupe_key
        row.event_time = item.event_time
        row.published_at = item.published_at
        row.ingested_at = item.ingested_at
        row.available_for_decision_at = item.available_for_decision_at
        row.raw_payload_ref = item.raw_payload_ref
        row.metadata_json = dict(item.metadata_json)
        self.session.flush()

    def records_for_ticker(self, ticker: str) -> tuple[SourceRecord, ...]:
        symbol = ticker.strip().upper()
        records = [
            record for record in self._runtime_records if record.ticker == symbol
        ]
        records.extend(
            [
            source_record_from_fundamental_snapshot(self._to_fundamental_record(row))
            for row in self.session.query(FundamentalSnapshot).filter_by(ticker=symbol).all()
            ]
        )
        records.extend(
            source_record_from_event_news_item(self._to_event_news_record(row))
            for row in self.session.query(EventNewsItem).filter_by(ticker=symbol).all()
        )
        records.extend(
            source_record_from_social_macro_item(self._to_social_macro_record(row))
            for row in self.session.query(SocialMacroItem).filter_by(ticker=symbol).all()
        )
        records.extend(
            source_record_from_insider_trade(row)
            for row in self.session.query(InsiderTrade).filter_by(ticker=symbol).all()
        )
        return tuple(sorted(records, key=lambda record: record.available_for_decision_at))

    def available_records(
        self,
        ticker: str,
        decision_time: datetime,
        *,
        source_family: str | None = None,
    ) -> tuple[SourceRecord, ...]:
        return tuple(
            record
            for record in self.records_for_ticker(ticker)
            if record.available_for_decision_at <= decision_time
            and (source_family is None or record.source_family == source_family)
        )

    def latest_available_by_family(
        self,
        ticker: str,
        source_family: str,
        decision_time: datetime,
    ) -> tuple[SourceRecord, ...]:
        records = self.available_records(ticker, decision_time, source_family=source_family)
        if not records:
            return ()
        latest = max(record.available_for_decision_at for record in records)
        return tuple(record for record in records if record.available_for_decision_at == latest)

    def latest_insider_filing_at(self) -> datetime | None:
        published_times = [
            source_record_from_insider_trade(row).published_at
            for row in self.session.query(InsiderTrade).all()
        ]
        if not published_times:
            return None
        return max(published_times)

    def _to_fundamental_record(self, row: FundamentalSnapshot) -> FundamentalSnapshotRecord:
        return FundamentalSnapshotRecord(
            fundamental_snapshot_id=str(row.fundamental_snapshot_id),
            ticker=row.ticker,
            fiscal_period=row.fiscal_period,
            as_of_date=row.as_of_date,
            provider=row.provider,
            source_refs_json=list(row.source_refs_json or []),
            event_time=row.event_time,
            published_at=row.published_at,
            ingested_at=row.ingested_at,
            available_for_decision_at=row.available_for_decision_at,
            raw_payload_ref=row.raw_payload_ref,
            normalized_metrics_json=dict(row.normalized_metrics_json or {}),
        )

    def _to_market_daily_bar_record(self, row: MarketDailyBar) -> MarketDailyBarRecord:
        return MarketDailyBarRecord(
            ticker=row.ticker,
            trade_date=row.trade_date,
            open_raw=float(row.open_raw) if row.open_raw is not None else None,
            high_raw=float(row.high_raw) if row.high_raw is not None else None,
            low_raw=float(row.low_raw) if row.low_raw is not None else None,
            close_raw=float(row.close_raw),
            adj_close=float(row.adj_close) if row.adj_close is not None else None,
            volume_raw=int(row.volume_raw) if row.volume_raw is not None else None,
            dividend=float(row.dividend or 0),
            stock_split=float(row.stock_split or 0),
            provider=row.provider,
            ingested_at=row.ingested_at,
            available_for_decision_at=row.available_for_decision_at,
            quality_flags_json=row.quality_flags_json or {},
            created_at=row.created_at,
        )

    def _to_event_news_record(self, row: EventNewsItem) -> EventNewsItemRecord:
        return EventNewsItemRecord(
            event_news_item_id=str(row.event_news_item_id),
            ticker=row.ticker,
            source_ticker=row.source_ticker,
            event_type=row.event_type,
            direction=row.direction,
            sentiment=row.sentiment,
            importance=row.importance,
            headline=row.headline,
            summary=row.summary,
            provider=row.provider,
            source_refs_json=list(row.source_refs_json or []),
            dedupe_key=row.dedupe_key,
            event_time=row.event_time,
            published_at=row.published_at,
            ingested_at=row.ingested_at,
            available_for_decision_at=row.available_for_decision_at,
            raw_payload_ref=row.raw_payload_ref,
            metadata_json=dict(row.metadata_json or {}),
        )

    def _to_social_macro_record(self, row: SocialMacroItem) -> SocialMacroItemRecord:
        return SocialMacroItemRecord(
            social_macro_item_id=str(row.social_macro_item_id),
            ticker=row.ticker,
            category=row.category,
            source_type=row.source_type,
            source_key=row.source_key,
            provider=row.provider,
            title=row.title,
            summary=row.summary,
            direction=row.direction,
            sentiment_direction=row.sentiment_direction,
            importance_score=float(row.importance_score) if row.importance_score is not None else None,
            importance_label=row.importance_label,
            policy_headwind_flag=bool(row.policy_headwind_flag),
            policy_tailwind_flag=bool(row.policy_tailwind_flag),
            explicit_ticker_mention_flag=bool(row.explicit_ticker_mention_flag),
            explicit_theme_mention_flag=bool(row.explicit_theme_mention_flag),
            theme_tags_json=list(row.theme_tags_json or []),
            company_name_mentions_json=list(row.company_name_mentions_json or []),
            source_refs_json=list(row.source_refs_json or []),
            dedupe_key=row.dedupe_key,
            event_time=row.event_time,
            published_at=row.published_at,
            ingested_at=row.ingested_at,
            available_for_decision_at=row.available_for_decision_at,
            raw_payload_ref=row.raw_payload_ref,
            metadata_json=dict(row.metadata_json or {}),
        )


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


def _market_daily_bar_record(
    value: MarketDailyBarRecord | Mapping[str, Any],
) -> MarketDailyBarRecord:
    if isinstance(value, MarketDailyBarRecord):
        return value
    return MarketDailyBarRecord(
        ticker=str(value["ticker"]),
        trade_date=value["trade_date"],
        open_raw=value.get("open_raw"),
        high_raw=value.get("high_raw"),
        low_raw=value.get("low_raw"),
        close_raw=value["close_raw"],
        adj_close=value.get("adj_close"),
        volume_raw=value.get("volume_raw"),
        dividend=value.get("dividend", 0.0),
        stock_split=value.get("stock_split", 0.0),
        provider=str(value["provider"]),
        ingested_at=value["ingested_at"],
        available_for_decision_at=value["available_for_decision_at"],
        quality_flags_json=value.get("quality_flags_json", {}),
        created_at=value.get("created_at"),
    )
