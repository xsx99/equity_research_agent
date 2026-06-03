"""Provider-backed source ingestion adapters for PR02 signal snapshots."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timezone
from typing import Any, Callable, Iterable, Protocol

from src.providers.market_data.types import DailyBar, MarketDataProvider
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
                    items = self._refresh_events_news(ticker, as_of, news_policy)
                    event_news_items.extend(items)
                    source_records.extend(source_record_from_event_news_item(item) for item in items)
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
            metadata_json={"error_count": len(errors)},
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
    ) -> tuple[EventNewsItemRecord, ...]:
        if self.news_provider is None:
            return ()
        items = policy.execute(
            ticker,
            lambda: self.news_provider.fetch_recent(ticker=ticker, limit=self.news_limit),
        )
        if not isinstance(items, list):
            return ()
        records: list[EventNewsItemRecord] = []
        for item in items:
            if isinstance(item, dict):
                records.append(_event_news_item_from_provider(ticker, item, as_of, self.provider_name))
        return tuple(records)


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
    published_at = _parse_datetime(item.get("published_at"), fallback=as_of)
    available_at = max(published_at, as_of)
    dedupe_key = (url or title or f"{ticker}:{published_at.isoformat()}").strip().lower()
    item_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"event_news:{ticker}:{dedupe_key}"))
    event_type = _news_event_type(signal_type, title, summary)
    sentiment = _news_sentiment(title, summary, event_type)
    return EventNewsItemRecord(
        event_news_item_id=item_id,
        ticker=ticker,
        source_ticker=ticker,
        event_type=event_type,
        direction=sentiment,
        sentiment=sentiment,
        importance=_news_importance(signal_type),
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
    return _parse_datetime(raw_date, fallback=fallback)


def _parse_datetime(value: object, *, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.combine(date.fromisoformat(raw), time.min)
            except ValueError:
                return fallback
        return _ensure_aware(parsed)
    return fallback


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _news_event_type(signal_type: str, title: str, summary: str) -> str:
    text = f"{title} {summary}".casefold()
    normalized_type = signal_type.strip().casefold()
    if normalized_type == "analyst_rating":
        if "downgrade" in text:
            return "analyst_downgrade"
        if "upgrade" in text:
            return "analyst_upgrade"
        if "price target" in text or "target" in text:
            return "price_target_revision"
        return "analyst_rating"
    if normalized_type == "earnings_guidance":
        return "guidance_news"
    if normalized_type == "earnings":
        return "own_earnings_headline"
    if normalized_type == "sec_filing":
        return "sec_filing"
    if "regulatory" in text or "fda" in text or "antitrust" in text:
        return "regulatory_news"
    if "order" in text or "customer" in text or "contract" in text:
        return "customer_order"
    if "product" in text or "launch" in text:
        return "product_launch"
    return "general_news"


def _news_sentiment(title: str, summary: str, event_type: str) -> str | None:
    text = f"{title} {summary}".casefold()
    negative_words = ("downgrade", "cut", "miss", "warning", "falls", "declines", "probe")
    positive_words = ("upgrade", "raise", "beat", "stronger", "wins", "launch", "approval")
    if event_type == "analyst_downgrade" or any(word in text for word in negative_words):
        return "negative"
    if event_type == "analyst_upgrade" or any(word in text for word in positive_words):
        return "positive"
    return None


def _news_importance(signal_type: str) -> str:
    if signal_type.strip().casefold() in {"earnings_guidance", "analyst_rating", "earnings", "sec_filing"}:
        return "high"
    return "normal"
