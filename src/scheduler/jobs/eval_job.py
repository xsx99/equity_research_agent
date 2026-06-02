"""Scheduled job for the evaluation pipeline."""
from __future__ import annotations

from src.core.config import (
    EVAL_RUN_ON_STARTUP,
    EVAL_SCHEDULE_HOUR,
    EVAL_SCHEDULE_MINUTE,
)
from src.core.logging import get_logger
from src.db.connection import get_session
from src.research.workflows.evaluation import EvalPipeline
from src.scheduler.base import BaseJob, JobConfig

logger = get_logger(__name__)


class EvalJob(BaseJob):
    """
    Scheduled job that runs :class:`~src.research.workflows.evaluation.EvalPipeline`
    for all eligible (matured) research runs once per day.
    """

    run_on_startup: bool = EVAL_RUN_ON_STARTUP

    @property
    def config(self) -> JobConfig:
        return JobConfig(
            job_id="eval_pipeline",
            trigger="cron",
            trigger_kwargs={
                "hour": EVAL_SCHEDULE_HOUR,
                "minute": EVAL_SCHEDULE_MINUTE,
            },
        )

    def run(self) -> None:
        """Execute one evaluation pipeline batch run."""
        logger.info("eval_job_started")
        try:
            with get_session() as session:
                pipeline = EvalPipeline(session=session)
                result = pipeline.run_all()

            logger.info(
                "eval_job_completed",
                evaluated=result.evaluated,
                skipped=result.skipped,
                failed=result.failed,
            )
        except Exception as e:
            logger.error("eval_job_failed", error=str(e), exc_info=True)
