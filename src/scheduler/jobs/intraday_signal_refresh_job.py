"""Scheduled job for the trading intraday signal refresh runtime."""
from __future__ import annotations

from src.core.logging import get_logger
from src.scheduler.base import BaseJob, JobConfig
from src.trading.runtime import run_job_phase

logger = get_logger(__name__)


class IntradaySignalRefreshJob(BaseJob):
    @property
    def config(self) -> JobConfig:
        return JobConfig(
            job_id="intraday_signal_refresh",
            trigger="cron",
            trigger_kwargs={"hour": "10-15", "minute": 0, "day_of_week": "mon-fri"},
        )

    def run(self) -> None:
        logger.info("intraday_signal_refresh_job_started")
        try:
            result = run_job_phase("intraday_refresh")
            if result.get("status") == "skipped":
                logger.warning(
                    "intraday_signal_refresh_job_skipped",
                    status="skipped",
                    reasons=list(result.get("summary", {}).get("reasons", [])),
                )
            else:
                logger.info("intraday_signal_refresh_job_completed", status=result["status"])
        except Exception as exc:
            logger.error("intraday_signal_refresh_job_failed", error=str(exc), exc_info=True)
