"""Scheduled job for the trading pre-open runtime."""
from __future__ import annotations

from src.core import config as app_config
from src.core.logging import get_logger
from src.scheduler.base import BaseJob, JobConfig
from src.trading.runtime import run_job_phase

logger = get_logger(__name__)


class TradingPreopenJob(BaseJob):
    @property
    def config(self) -> JobConfig:
        return JobConfig(
            job_id="trading_preopen",
            trigger="cron",
            trigger_kwargs={"hour": 8, "minute": 45, "day_of_week": "mon-fri"},
        )

    def run(self) -> None:
        logger.info("trading_preopen_job_started")
        try:
            result = run_job_phase(
                "preopen",
                execute_paper_orders=app_config.TRADING_EXECUTE_PAPER_ORDERS,
                execute_paper_option_orders=app_config.TRADING_EXECUTE_PAPER_OPTION_ORDERS,
            )
            if result.get("status") == "skipped":
                logger.warning(
                    "trading_preopen_job_skipped",
                    status="skipped",
                    reasons=list(result.get("summary", {}).get("reasons", [])),
                )
            else:
                logger.info("trading_preopen_job_completed", status=result["status"])
        except Exception as exc:
            logger.error("trading_preopen_job_failed", error=str(exc), exc_info=True)
