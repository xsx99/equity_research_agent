"""Scheduled job for the trading reflection runtime."""
from __future__ import annotations

from src.core.logging import get_logger
from src.scheduler.base import BaseJob, JobConfig
from src.trading.runtime import run_job_phase

logger = get_logger(__name__)


class TradingReflectionJob(BaseJob):
    @property
    def config(self) -> JobConfig:
        return JobConfig(
            job_id="trading_reflection",
            trigger="cron",
            trigger_kwargs={"hour": 16, "minute": 20, "day_of_week": "mon-fri"},
        )

    def run(self) -> None:
        logger.info("trading_reflection_job_started")
        try:
            result = run_job_phase("reflection")
            logger.info("trading_reflection_job_completed", status=result["status"])
        except Exception as exc:
            logger.error("trading_reflection_job_failed", error=str(exc), exc_info=True)
