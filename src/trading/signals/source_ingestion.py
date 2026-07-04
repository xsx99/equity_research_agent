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
    infer_news_event_type,
    infer_news_sentiment,
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
    SocialMacroItemRecord,
    SourceIngestionRunRecord,
    SourceRecord,
    source_record_from_event_news_item,
    source_record_from_fundamental_snapshot,
    source_record_from_social_macro_item,
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

    def save_social_macro_item(self, item: SocialMacroItemRecord) -> None:
        """Persist one normalized social/policy row."""


class EarningsCalendarProvider(Protocol):
    """Ticker lookup surface for upcoming earnings dates."""

    def next_earnings_date(self, ticker: str, as_of: date) -> date | None:
        """Return the next earnings date for ticker as of the supplied date."""


@dataclass(frozen=True)
class SourceIngestionResult:
    """Result returned by a targeted or scheduled source ingestion refresh."""

    ingestion_run: SourceIngestionRunRecord
    source_records: tuple[SourceRecord, ...]
    fundamental_snapshots: tuple[FundamentalSnapshotRecord, ...]
    event_news_items: tuple[EventNewsItemRecord, ...]
    social_macro_items: tuple[SocialMacroItemRecord, ...]


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
        earnings_calendar: EarningsCalendarProvider | None = None,
        global_context_fetcher: Callable[[datetime], dict[str, Any]] | None = None,
        lookback_days: int = 252,
        news_limit: int = 5,
        max_requests_per_endpoint: int = 100,
        now: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.market_provider = market_provider
        self.news_provider = news_provider
        self.earnings_calendar = earnings_calendar
        self.global_context_fetcher = global_context_fetcher
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
                "social_macro_items": 0,
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
        social_macro_policy = self._policy("global_context", "social_macro", recorder)
        option_chain_policy = self._policy("option_chain", "option_chain", recorder)
        source_records: list[SourceRecord] = []
        fundamental_snapshots: list[FundamentalSnapshotRecord] = []
        event_news_items: list[EventNewsItemRecord] = []
        social_macro_items: list[SocialMacroItemRecord] = []
        news_condensation_summary = {
            "raw_news_item_count": 0,
            "kept_news_item_count": 0,
            "dropped_low_signal_count": 0,
            "dropped_duplicate_count": 0,
            "dropped_irrelevant_count": 0,
        }
        errors: list[Exception] = []

        if "social_macro" in families:
            try:
                social_macro_items.extend(
                    self._refresh_social_macro(normalized_tickers, as_of, social_macro_policy)
                )
                source_records.extend(
                    source_record_from_social_macro_item(item) for item in social_macro_items
                )
            except Exception as exc:
                errors.append(exc)

        for ticker in normalized_tickers:
            company_name: str | None = None
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
                        normalized_metrics = (
                            snapshot.normalized_metrics_json
                            if isinstance(snapshot.normalized_metrics_json, dict)
                            else {}
                        )
                        raw_company_name = normalized_metrics.get("company_name")
                        if isinstance(raw_company_name, str) and raw_company_name.strip():
                            company_name = raw_company_name.strip()
                        fundamental_snapshots.append(snapshot)
                        source_records.append(source_record_from_fundamental_snapshot(snapshot))
                except Exception as exc:
                    errors.append(exc)
            if "option_chain" in families:
                try:
                    option_chain_record = self._refresh_option_chain(ticker, as_of, option_chain_policy)
                    if option_chain_record is not None:
                        source_records.append(option_chain_record)
                except Exception as exc:
                    errors.append(exc)
            if "events_news" in families:
                try:
                    refresh_result = self._refresh_events_news(
                        ticker,
                        as_of,
                        news_policy,
                        company_name=company_name,
                    )
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
        for item in social_macro_items:
            self.artifact_repository.save_social_macro_item(item)

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
                "social_macro_items": len(social_macro_items),
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
            social_macro_items=tuple(social_macro_items),
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
        calendar_payload = self._calendar_earnings_payload(ticker, as_of)
        if calendar_payload is not None:
            context = dict(context)
            context.update(calendar_payload)
        snapshot_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"fundamental:{ticker}:{as_of.isoformat()}"))
        metrics = {
            key: _json_safe_value(value)
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
                "earnings_date",
                "known_event_date",
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

    def _refresh_option_chain(
        self,
        ticker: str,
        as_of: datetime,
        policy: ProviderResiliencePolicy,
    ) -> SourceRecord | None:
        fetch_option_chain = getattr(self.market_provider, "fetch_option_chain", None)
        if fetch_option_chain is None:
            return None
        contracts = policy.execute(ticker, lambda: fetch_option_chain(ticker))
        if not isinstance(contracts, list):
            return None
        normalized_contracts = [dict(contract) for contract in contracts if isinstance(contract, dict)]
        if not normalized_contracts:
            return None
        return SourceRecord(
            ticker=ticker,
            source_family="option_chain",
            source=self.provider_name,
            source_table="option_chain_snapshots",
            source_record_id=f"option_chain:{ticker}:{as_of.isoformat()}",
            event_time=as_of,
            published_at=as_of,
            ingested_at=as_of,
            available_for_decision_at=as_of,
            payload={"contracts": normalized_contracts},
        )

    def _refresh_events_news(
        self,
        ticker: str,
        as_of: datetime,
        policy: ProviderResiliencePolicy,
        *,
        company_name: str | None = None,
    ) -> _EventsNewsRefreshResult:
        records: list[EventNewsItemRecord] = []
        summary = _empty_news_condensation_summary()
        if self.news_provider is not None:
            items = policy.execute(
                ticker,
                lambda: self.news_provider.fetch_recent(ticker=ticker, limit=self.news_limit),
            )
        else:
            items = []
        if not isinstance(items, list):
            items = []
        if _news_condenser_enabled():
            condensed = condense_news_items(
                ticker=ticker,
                company_name=company_name,
                items=items,
                as_of=as_of,
            )
            records.extend(
                _event_news_item_from_condensed(ticker, item, as_of, self.provider_name)
                for item in condensed.kept_items
            )
            summary = {
                "raw_news_item_count": condensed.raw_news_item_count,
                "kept_news_item_count": condensed.kept_news_item_count,
                "dropped_low_signal_count": condensed.dropped_low_signal_count,
                "dropped_duplicate_count": condensed.dropped_duplicate_count,
                "dropped_irrelevant_count": condensed.dropped_irrelevant_count,
            }
        else:
            for item in items:
                if isinstance(item, dict):
                    records.append(_event_news_item_from_provider(ticker, item, as_of, self.provider_name))
            summary = {
                "raw_news_item_count": len(items),
                "kept_news_item_count": len(records),
                "dropped_low_signal_count": 0,
                "dropped_duplicate_count": 0,
                "dropped_irrelevant_count": 0,
            }
        earnings_payload = self._calendar_earnings_payload(ticker, as_of)
        if earnings_payload is not None:
            records.append(_earnings_event_news_item(ticker, earnings_payload, as_of, self.provider_name))
        return _EventsNewsRefreshResult(
            items=tuple(records),
            summary=summary,
        )

    def _calendar_earnings_payload(self, ticker: str, as_of: datetime) -> dict[str, Any] | None:
        if self.earnings_calendar is None:
            return None
        as_of_date = as_of.date()
        try:
            earnings_date = self.earnings_calendar.next_earnings_date(ticker, as_of_date)
        except Exception:
            return None
        if earnings_date is None:
            return None
        earnings_in_days = (earnings_date - as_of_date).days
        if earnings_in_days < 0:
            return None
        return {
            "earnings_in_days": earnings_in_days,
            "earnings_date": earnings_date,
            "known_event_date": earnings_date,
        }

    def _refresh_social_macro(
        self,
        tickers: tuple[str, ...],
        as_of: datetime,
        policy: ProviderResiliencePolicy,
    ) -> tuple[SocialMacroItemRecord, ...]:
        if self.global_context_fetcher is None:
            return ()
        snapshot = policy.execute(",".join(tickers), lambda: self.global_context_fetcher(as_of))
        if not isinstance(snapshot, dict):
            return ()
        records: list[SocialMacroItemRecord] = []
        for source_key, category in (
            ("trump_updates", "trump_update"),
            ("official_updates", "official_update"),
            ("geopolitical_news", "geopolitical_news"),
        ):
            items = snapshot.get(source_key)
            if not isinstance(items, list):
                continue
            for ticker in tickers:
                for item in items:
                    if isinstance(item, dict):
                        records.append(
                            _social_macro_item_from_provider(
                                ticker=ticker,
                                source_key=source_key,
                                category=category,
                                item=item,
                                as_of=as_of,
                                provider_name=self.provider_name,
                            )
                        )
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
    published_at = parse_news_datetime(item.get("published_at"), fallback=as_of)
    available_at = max(published_at, as_of)
    provider_dedupe = (url or title or f"{ticker}:{published_at.isoformat()}").strip().lower()
    dedupe_key = f"{ticker.upper()}|{provider_dedupe}"
    item_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"event_news:{dedupe_key}"))
    event_type = infer_news_event_type(signal_type, title, summary)
    sentiment = infer_news_sentiment(title, summary, event_type)
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


def _earnings_event_news_item(
    ticker: str,
    payload: dict[str, Any],
    as_of: datetime,
    provider_name: str,
) -> EventNewsItemRecord:
    earnings_date = payload.get("earnings_date")
    if not isinstance(earnings_date, date):
        raise ValueError("earnings_date_required")
    date_text = earnings_date.isoformat()
    item_id = f"earnings:{ticker.upper()}:{date_text}"
    return EventNewsItemRecord(
        event_news_item_id=item_id,
        ticker=ticker,
        source_ticker=ticker,
        event_type="own_earnings_upcoming",
        direction=None,
        sentiment=None,
        importance="high",
        headline=f"{ticker.upper()} earnings expected {date_text}",
        summary=None,
        provider=provider_name,
        source_refs_json=[
            {
                "source": "nasdaq",
                "source_table": "earnings_calendar",
                "source_record_id": item_id,
            }
        ],
        dedupe_key=f"{ticker.upper()}|earnings|{date_text}",
        event_time=as_of,
        published_at=as_of,
        ingested_at=as_of,
        available_for_decision_at=as_of,
        raw_payload_ref=None,
        metadata_json={
            "earnings_in_days": payload["earnings_in_days"],
            "known_event_date": date_text,
            "earnings_date": date_text,
        },
    )


def _normalize_tickers(tickers: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(normalize_ticker(ticker) for ticker in tickers if ticker.strip()))


def _social_macro_item_from_provider(
    *,
    ticker: str,
    source_key: str,
    category: str,
    item: dict[str, Any],
    as_of: datetime,
    provider_name: str,
) -> SocialMacroItemRecord:
    title = str(item.get("title") or "").strip()
    summary = str(item.get("summary") or "").strip()
    source = str(item.get("source") or provider_name).strip() or provider_name
    url = str(item.get("url") or "").strip() or None
    published_at = parse_news_datetime(item.get("published_at"), fallback=as_of)
    available_at = max(published_at, as_of)
    combined = f"{title} {summary}".casefold()
    ticker_mention = ticker.casefold() in combined
    sentiment_direction = _infer_social_macro_sentiment(combined)
    importance_score, importance_label = _social_macro_importance(
        category=category,
        ticker_mention=ticker_mention,
        sentiment_direction=sentiment_direction,
    )
    provider_dedupe = (url or title or f"{category}:{published_at.isoformat()}").strip().lower()
    dedupe_key = f"{ticker.upper()}|{category}|{provider_dedupe}"
    item_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"social_macro:{dedupe_key}"))
    return SocialMacroItemRecord(
        social_macro_item_id=item_id,
        ticker=ticker,
        category=category,
        source_type="global_context",
        source_key=source_key,
        provider=provider_name,
        title=title or None,
        summary=summary or None,
        direction=sentiment_direction,
        sentiment_direction=sentiment_direction,
        importance_score=importance_score,
        importance_label=importance_label,
        policy_headwind_flag=sentiment_direction == "negative",
        policy_tailwind_flag=sentiment_direction == "positive",
        explicit_ticker_mention_flag=ticker_mention,
        explicit_theme_mention_flag=False,
        theme_tags_json=[],
        company_name_mentions_json=[],
        source_refs_json=[
            {
                "source": source,
                "source_table": "global_context",
                "source_record_id": item_id,
            }
        ],
        dedupe_key=dedupe_key,
        event_time=published_at,
        published_at=published_at,
        ingested_at=as_of,
        available_for_decision_at=available_at,
        raw_payload_ref=url,
        metadata_json={},
    )


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


def _infer_social_macro_sentiment(combined_text: str) -> str | None:
    negative_markers = (
        "tariff",
        "sanction",
        "export control",
        "airstrike",
        "war",
        "risk",
        "pressure",
        "volatile",
    )
    positive_markers = (
        "deal",
        "agreement",
        "approval",
        "support",
        "tailwind",
        "boost",
        "stimulus",
    )
    if any(marker in combined_text for marker in negative_markers):
        return "negative"
    if any(marker in combined_text for marker in positive_markers):
        return "positive"
    return None


def _social_macro_importance(
    *,
    category: str,
    ticker_mention: bool,
    sentiment_direction: str | None,
) -> tuple[float, str]:
    if ticker_mention:
        return 0.9, "high"
    if category in {"trump_update", "official_update"} and sentiment_direction is not None:
        return 0.8, "high"
    if category == "geopolitical_news":
        return 0.7, "medium"
    return 0.6, "medium"


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _ensure_aware(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    return value
