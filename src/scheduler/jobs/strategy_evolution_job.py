"""Scheduled job for the trading strategy-evolution runtime."""
from __future__ import annotations

from src.core.logging import get_logger
from src.scheduler.base import BaseJob, JobConfig
from src.trading.runtime import run_job_phase

logger = get_logger(__name__)


class StrategyEvolutionJob(BaseJob):
    @property
    def config(self) -> JobConfig:
        return JobConfig(
            job_id="strategy_evolution",
            trigger="cron",
            trigger_kwargs={"hour": 16, "minute": 50, "day_of_week": "mon-fri"},
        )

    def run(self) -> None:
        logger.info("strategy_evolution_job_started")
        try:
            result = run_job_phase("strategy_evolution")
            logger.info("strategy_evolution_job_completed", status=result["status"])
        except Exception as exc:
            logger.error("strategy_evolution_job_failed", error=str(exc), exc_info=True)
