"""Scheduled post-close ingestion of daily market bars."""
from __future__ import annotations

from src.core.logging import get_logger
from src.db.connection import get_session
from src.providers.market_data.yfinance_prices import fetch_daily_bars_for_symbols
from src.scheduler.base import BaseJob, JobConfig
from src.trading.repositories.source_sqlalchemy import SQLAlchemySignalSourceRepository
from src.trading.workflows.market_daily_bars import (
    MarketDailyBarsBatch,
    load_active_daily_bar_tickers,
)

logger = get_logger(__name__)


class MarketDailyBarsJob(BaseJob):
    """Run the daily-bar batch once after the regular market close."""

    @property
    def config(self) -> JobConfig:
        return JobConfig(
            job_id="market_daily_bars",
            trigger="cron",
            trigger_kwargs={"hour": 16, "minute": 5, "day_of_week": "mon-fri"},
        )

    def run(self) -> None:
        logger.info("market_daily_bars_job_started")
        try:
            with get_session() as session:
                repository = SQLAlchemySignalSourceRepository(session)
                result = MarketDailyBarsBatch(
                    active_ticker_loader=lambda: load_active_daily_bar_tickers(session),
                    yahoo_fetcher=fetch_daily_bars_for_symbols,
                    repository=repository,
                ).run()
            logger.info(
                "market_daily_bars_job_completed",
                tickers_requested=result.tickers_requested,
                tickers_succeeded=result.tickers_succeeded,
                tickers_missing=list(result.tickers_missing),
            )
        except Exception as exc:
            logger.error("market_daily_bars_job_failed", error=str(exc), exc_info=True)
