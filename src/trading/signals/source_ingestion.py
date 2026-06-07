"""Provider-backed source ingestion adapters for PR02 signal snapshots."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timezone
from typing import Any, Callable, Iterable, Protocol

from src.providers.market_data.types import DailyBar, MarketDataProvider
from src.providers.news_data.helpers import (
    condense_news_items,
    news_importance,
    parse_news_datetime,
)
from src.providers.news_data.types import NewsItem, NewsProvider
from src.trading.data_sources.provider_resilience import (
    ProviderRequestRecorder,
    ProviderRequestRunRecord,
    ProviderResiliencePolicy,
)
from src.trading.signals.sources import (
    EventNewsItemRecord,
    FundamentalSnapshotRecord,
    SourceIngestionRunRecord,
    SourceRecord,
    source_record_from_event_news_item,
    source_record_from_fundamental_snapshot,
)
from src.trading.data_sources.universe import normalize_ticker


class SignalSourceWriter(Protocol):
    """Repository that stores normalized source rows for the SignalPipeline."""

    def add(self, *records: SourceRecord) -> None:
        """Persist source records."""


class SourceIngestionArtifactRepository(Protocol):
    """Repository abstraction for PR02 ingestion metadata and normalized rows."""

    def record_source_ingestion_run(self, run: SourceIngestionRunRecord) -> None:
        """Persist source ingestion run metadata."""

    def record_provider_request(self, run: ProviderRequestRunRecord) -> None:
        """Persist one provider request telemetry row."""

    def save_fundamental_snapshot(self, snapshot: FundamentalSnapshotRecord) -> None:
        """Persist one normalized fundamental snapshot row."""

    def save_event_news_item(self, item: EventNewsItemRecord) -> None:
        """Persist one normalized event/news row."""


@dataclass(frozen=True)
class SourceIngestionResult:
    """Result returned by a targeted or scheduled source ingestion refresh."""

    ingestion_run: SourceIngestionRunRecord
    source_records: tuple[SourceRecord, ...]
    fundamental_snapshots: tuple[FundamentalSnapshotRecord, ...]
    event_news_items: tuple[EventNewsItemRecord, ...]


@dataclass(frozen=True)
class _EventsNewsRefreshResult:
    items: tuple[EventNewsItemRecord, ...]
    summary: dict[str, int]


class SourceIngestionService:
    """Adapt existing market/news providers into replayable SignalPipeline rows."""

    def __init__(
        self,
        *,
        market_provider: MarketDataProvider,
        news_provider: NewsProvider | None,
        source_repository: SignalSourceWriter,
        artifact_repository: SourceIngestionArtifactRepository,
        provider_name: str,
        lookback_days: int = 252,
        news_limit: int = 5,
        max_requests_per_endpoint: int = 100,
        now: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.market_provider = market_provider
        self.news_provider = news_provider
        self.source_repository = source_repository
        self.artifact_repository = artifact_repository
        self.provider_name = provider_name
        self.lookback_days = lookback_days
        self.news_limit = news_limit
        self.max_requests_per_endpoint = max_requests_per_endpoint
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper or (lambda seconds: None)

    def refresh_tickers(
        self,
        tickers: Iterable[str],
        *,
        as_of: datetime,
        run_type: str,
        source_families: Iterable[str] = ("technical", "fundamental", "events_news"),
    ) -> SourceIngestionResult:
        """Refresh source rows for tickers through provider resilience guardrails."""
        normalized_tickers = _normalize_tickers(tickers)
        families = tuple(dict.fromkeys(source_families))
        ingestion_run_id = str(uuid.uuid4())
        started_at = self.now()
        provisional_ingestion_run = SourceIngestionRunRecord(
            source_ingestion_run_id=ingestion_run_id,
            source_family=families[0] if len(families) == 1 else "all",
            run_type=run_type,
            scope_json={"tickers": normalized_tickers, "source_families": list(families)},
            provider=self.provider_name,
            as_of=as_of,
            started_at=started_at,
            completed_at=None,
            # The current schema has no "running" state; persist a placeholder parent row first
            # so provider-request telemetry can reference it through a real FK during the run.
            status="degraded",
            coverage_json={
                "tickers_requested": len(normalized_tickers),
                "source_records": 0,
                "fundamental_snapshots": 0,
                "event_news_items": 0,
            },
            metadata_json={"phase": "started"},
        )
        self.artifact_repository.record_source_ingestion_run(provisional_ingestion_run)
        recorder = _LinkedProviderRequestRecorder(
            repository=self.artifact_repository,
            source_ingestion_run_id=ingestion_run_id,
        )
        bars_policy = self._policy("market_bars", "technical", recorder)
        context_policy = self._policy("market_context", "fundamental", recorder)
        news_policy = self._policy("news", "events_news", recorder)
        source_records: list[SourceRecord] = []
        fundamental_snapshots: list[FundamentalSnapshotRecord] = []
        event_news_items: list[EventNewsItemRecord] = []
        news_condensation_summary = {
            "raw_news_item_count": 0,
            "kept_news_item_count": 0,
            "dropped_low_signal_count": 0,
            "dropped_duplicate_count": 0,
            "dropped_irrelevant_count": 0,
        }
        errors: list[Exception] = []

        for ticker in normalized_tickers:
            if "technical" in families:
                try:
                    record = self._refresh_technical(ticker, as_of, bars_policy)
                    if record is not None:
                        source_records.append(record)
                except Exception as exc:
                    errors.append(exc)
            if "fundamental" in families:
                try:
                    snapshot = self._refresh_fundamental(ticker, as_of, context_policy)
                    if snapshot is not None:
                        fundamental_snapshots.append(snapshot)
                        source_records.append(source_record_from_fundamental_snapshot(snapshot))
                except Exception as exc:
                    errors.append(exc)
            if "events_news" in families and self.news_provider is not None:
                try:
                    refresh_result = self._refresh_events_news(ticker, as_of, news_policy)
                    event_news_items.extend(refresh_result.items)
                    source_records.extend(source_record_from_event_news_item(item) for item in refresh_result.items)
                    for key, value in refresh_result.summary.items():
                        news_condensation_summary[key] += value
                except Exception as exc:
                    errors.append(exc)

        if source_records:
            self.source_repository.add(*source_records)
        for snapshot in fundamental_snapshots:
            self.artifact_repository.save_fundamental_snapshot(snapshot)
        for item in event_news_items:
            self.artifact_repository.save_event_news_item(item)

        status = _ingestion_status(errors=errors, source_records=source_records)
        ingestion_run = SourceIngestionRunRecord(
            source_ingestion_run_id=ingestion_run_id,
            source_family=families[0] if len(families) == 1 else "all",
            run_type=run_type,
            scope_json={"tickers": normalized_tickers, "source_families": list(families)},
            provider=self.provider_name,
            as_of=as_of,
            started_at=started_at,
            completed_at=self.now(),
            status=status,
            coverage_json={
                "tickers_requested": len(normalized_tickers),
                "source_records": len(source_records),
                "fundamental_snapshots": len(fundamental_snapshots),
                "event_news_items": len(event_news_items),
            },
            error_code=errors[0].__class__.__name__ if errors else None,
            error_message=str(errors[0]) if errors else None,
            metadata_json={
                "error_count": len(errors),
                "news_condensation": news_condensation_summary,
            },
        )
        self.artifact_repository.record_source_ingestion_run(ingestion_run)
        return SourceIngestionResult(
            ingestion_run=ingestion_run,
            source_records=tuple(source_records),
            fundamental_snapshots=tuple(fundamental_snapshots),
            event_news_items=tuple(event_news_items),
        )

    def _policy(
        self,
        endpoint: str,
        source_family: str,
        recorder: ProviderRequestRecorder,
    ) -> ProviderResiliencePolicy:
        return ProviderResiliencePolicy(
            provider=self.provider_name,
            endpoint=endpoint,
            source_family=source_family,
            max_requests=self.max_requests_per_endpoint,
            recorder=recorder,
            now=self.now,
            sleeper=self.sleeper,
        )

    def _refresh_technical(
        self,
        ticker: str,
        as_of: datetime,
        policy: ProviderResiliencePolicy,
    ) -> SourceRecord | None:
        bars = policy.execute(
            ticker,
            lambda: self.market_provider.fetch_daily_bars(ticker, lookback_days=self.lookback_days),
        )
        if not isinstance(bars, list):
            return None
        normalized_bars = [dict(bar) for bar in bars if isinstance(bar, dict)]
        if not normalized_bars:
            return None
        event_time = _latest_bar_event_time(normalized_bars, fallback=as_of)
        return SourceRecord(
            ticker=ticker,
            source_family="technical",
            source=self.provider_name,
            source_table="market_bars",
            source_record_id=f"market_bars:{ticker}:{event_time.isoformat()}",
            event_time=event_time,
            published_at=as_of,
            ingested_at=as_of,
            available_for_decision_at=as_of,
            payload={"bars": normalized_bars},
        )

    def _refresh_fundamental(
        self,
        ticker: str,
        as_of: datetime,
        policy: ProviderResiliencePolicy,
    ) -> FundamentalSnapshotRecord | None:
        context = policy.execute(ticker, lambda: self.market_provider.fetch_context(ticker))
        if not isinstance(context, dict) or not context:
            return None
        snapshot_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"fundamental:{ticker}:{as_of.isoformat()}"))
        metrics = {
            key: value
            for key, value in context.items()
            if key
            in {
                "market_cap",
                "revenue_growth_score",
                "margin_trend_score",
                "quality_score",
                "valuation_percentile",
                "ev_sales_percentile",
                "fcf_margin_score",
                "short_interest_pct_float",
                "pe_ratio",
                "ps_ratio",
                "sector",
                "company_name",
                "earnings_in_days",
            }
        }
        return FundamentalSnapshotRecord(
            fundamental_snapshot_id=snapshot_id,
            ticker=ticker,
            fiscal_period=None,
            as_of_date=as_of.date(),
            provider=self.provider_name,
            source_refs_json=[
                {
                    "source": self.provider_name,
                    "source_table": "provider_context",
                    "source_record_id": snapshot_id,
                }
            ],
            event_time=as_of,
            published_at=as_of,
            ingested_at=as_of,
            available_for_decision_at=as_of,
            raw_payload_ref=None,
            normalized_metrics_json=metrics,
        )

    def _refresh_events_news(
        self,
        ticker: str,
        as_of: datetime,
        policy: ProviderResiliencePolicy,
    ) -> _EventsNewsRefreshResult:
        if self.news_provider is None:
            return _EventsNewsRefreshResult(
                items=(),
                summary=_empty_news_condensation_summary(),
            )
        items = policy.execute(
            ticker,
            lambda: self.news_provider.fetch_recent(ticker=ticker, limit=self.news_limit),
        )
        if not isinstance(items, list):
            return _EventsNewsRefreshResult(
                items=(),
                summary=_empty_news_condensation_summary(),
            )
        if _news_condenser_enabled():
            condensed = condense_news_items(ticker=ticker, items=items, as_of=as_of)
            records = tuple(
                _event_news_item_from_condensed(ticker, item, as_of, self.provider_name)
                for item in condensed.kept_items
            )
            return _EventsNewsRefreshResult(
                items=records,
                summary={
                    "raw_news_item_count": condensed.raw_news_item_count,
                    "kept_news_item_count": condensed.kept_news_item_count,
                    "dropped_low_signal_count": condensed.dropped_low_signal_count,
                    "dropped_duplicate_count": condensed.dropped_duplicate_count,
                    "dropped_irrelevant_count": condensed.dropped_irrelevant_count,
                },
            )
        records: list[EventNewsItemRecord] = []
        for item in items:
            if isinstance(item, dict):
                records.append(_event_news_item_from_provider(ticker, item, as_of, self.provider_name))
        return _EventsNewsRefreshResult(
            items=tuple(records),
            summary={
                "raw_news_item_count": len(items),
                "kept_news_item_count": len(records),
                "dropped_low_signal_count": 0,
                "dropped_duplicate_count": 0,
                "dropped_irrelevant_count": 0,
            },
        )


class _LinkedProviderRequestRecorder:
    """Attach ingestion run identity before persisting provider telemetry."""

    def __init__(
        self,
        *,
        repository: SourceIngestionArtifactRepository,
        source_ingestion_run_id: str,
    ) -> None:
        self.repository = repository
        self.source_ingestion_run_id = source_ingestion_run_id

    def record(self, run: ProviderRequestRunRecord) -> None:
        self.repository.record_provider_request(
            replace(run, source_ingestion_run_id=self.source_ingestion_run_id)
        )


def _event_news_item_from_provider(
    ticker: str,
    item: NewsItem,
    as_of: datetime,
    provider_name: str,
) -> EventNewsItemRecord:
    title = str(item.get("title") or "").strip()
    summary = str(item.get("summary") or "").strip()
    source = str(item.get("source") or provider_name).strip() or provider_name
    url = str(item.get("url") or "").strip() or None
    signal_type = str(item.get("signal_type") or "general_news")
    published_at = parse_news_datetime(item.get("published_at"), fallback=as_of)
    available_at = max(published_at, as_of)
    provider_dedupe = (url or title or f"{ticker}:{published_at.isoformat()}").strip().lower()
    dedupe_key = f"{ticker.upper()}|{provider_dedupe}"
    item_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"event_news:{dedupe_key}"))
    event_type = "general_news"
    sentiment = None
    return EventNewsItemRecord(
        event_news_item_id=item_id,
        ticker=ticker,
        source_ticker=ticker,
        event_type=event_type,
        direction=sentiment,
        sentiment=sentiment,
        importance=news_importance(signal_type, event_type),
        headline=title or None,
        summary=summary or None,
        provider=provider_name,
        source_refs_json=[
            {
                "source": source,
                "source_table": "provider_news",
                "source_record_id": item_id,
            }
        ],
        dedupe_key=dedupe_key,
        event_time=published_at,
        published_at=published_at,
        ingested_at=as_of,
        available_for_decision_at=available_at,
        raw_payload_ref=url,
        metadata_json={"signal_type": signal_type},
    )


def _event_news_item_from_condensed(
    ticker: str,
    item: Any,
    as_of: datetime,
    provider_name: str,
) -> EventNewsItemRecord:
    dedupe_key = item.duplicate_group_key
    item_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"event_news:{dedupe_key}"))
    source = str(item.source or provider_name).strip() or provider_name
    metadata_json = dict(item.metadata)
    metadata_json["signal_type"] = item.signal_type
    return EventNewsItemRecord(
        event_news_item_id=item_id,
        ticker=ticker,
        source_ticker=ticker,
        event_type=item.event_type,
        direction=item.sentiment,
        sentiment=item.sentiment,
        importance=item.importance,
        headline=item.title or None,
        summary=item.summary or None,
        provider=provider_name,
        source_refs_json=[
            {
                "source": source,
                "source_table": "provider_news",
                "source_record_id": item_id,
            }
        ],
        dedupe_key=dedupe_key,
        event_time=item.published_at,
        published_at=item.published_at,
        ingested_at=as_of,
        available_for_decision_at=item.available_for_decision_at,
        raw_payload_ref=item.url,
        metadata_json=metadata_json,
    )


def _normalize_tickers(tickers: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(normalize_ticker(ticker) for ticker in tickers if ticker.strip()))


def _ingestion_status(*, errors: list[Exception], source_records: list[SourceRecord]) -> str:
    if not errors:
        return "succeeded"
    if source_records:
        return "degraded"
    return "failed"


def _latest_bar_event_time(bars: list[DailyBar], *, fallback: datetime) -> datetime:
    if not bars:
        return fallback
    raw_date = bars[-1].get("date")
    if isinstance(raw_date, datetime):
        return _ensure_aware(raw_date)
    if isinstance(raw_date, date):
        return datetime.combine(raw_date, time.min, tzinfo=timezone.utc)
    return parse_news_datetime(raw_date, fallback=fallback)

def _empty_news_condensation_summary() -> dict[str, int]:
    return {
        "raw_news_item_count": 0,
        "kept_news_item_count": 0,
        "dropped_low_signal_count": 0,
        "dropped_duplicate_count": 0,
        "dropped_irrelevant_count": 0,
    }


def _news_condenser_enabled() -> bool:
    raw = os.getenv("TRADING_NEWS_CONDENSER_ENABLED", "1").strip().casefold()
    return raw not in {"0", "false", "off", "no"}
