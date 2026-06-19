"""Scheduled job for active manual ticker reviews."""
from __future__ import annotations

from src.core import config as app_config
from src.core.logging import get_logger
from src.scheduler.base import BaseJob, JobConfig
from src.trading.runtime import run_job_phase

logger = get_logger(__name__)


class ManualTickerReviewJob(BaseJob):
    @property
    def config(self) -> JobConfig:
        return JobConfig(
            job_id="manual_ticker_review",
            trigger="cron",
            trigger_kwargs={"hour": 8, "minute": 50, "day_of_week": "mon-fri"},
        )

    def run(self) -> None:
        logger.info("manual_ticker_review_job_started")
        try:
            result = run_job_phase(
                "manual_review",
                execute_paper_orders=app_config.TRADING_EXECUTE_PAPER_ORDERS,
                execute_paper_option_orders=app_config.TRADING_EXECUTE_PAPER_OPTION_ORDERS,
            )
            if result.get("status") == "skipped":
                logger.warning(
                    "manual_ticker_review_job_skipped",
                    status="skipped",
                    reasons=list(result.get("summary", {}).get("reasons", [])),
                )
            else:
                logger.info("manual_ticker_review_job_completed", status=result["status"])
        except Exception as exc:
            logger.error("manual_ticker_review_job_failed", error=str(exc), exc_info=True)
