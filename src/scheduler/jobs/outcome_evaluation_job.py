"""Scheduled job for persisted candidate outcome maturation."""
from __future__ import annotations

from src.core.logging import get_logger
from src.scheduler.base import BaseJob, JobConfig
from src.trading.runtime import run_job_phase

logger = get_logger(__name__)


class OutcomeEvaluationJob(BaseJob):
    @property
    def config(self) -> JobConfig:
        return JobConfig(
            job_id="outcome_evaluation",
            trigger="cron",
            trigger_kwargs={"hour": 16, "minute": 10, "day_of_week": "mon-fri"},
        )

    def run(self) -> None:
        logger.info("outcome_evaluation_job_started")
        try:
            result = run_job_phase("outcome_evaluation")
            status = result.get("status")
            if status in {"skipped", "degraded"}:
                logger.warning(
                    "outcome_evaluation_job_completed",
                    status=status,
                    reasons=list(result.get("summary", {}).get("reasons", ())),
                )
            else:
                logger.info("outcome_evaluation_job_completed", status=status)
        except Exception as exc:
            logger.error("outcome_evaluation_job_failed", error=str(exc), exc_info=True)
