"""Scheduler service — registers and starts all background jobs."""
from __future__ import annotations

from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from src.core.config import SCHEDULER_TIMEZONE
from src.core.logging import get_logger
from src.core.timezones import resolve_timezone
from src.scheduler.base import BaseJob
from src.scheduler.jobs.eval_job import EvalJob
from src.scheduler.jobs.intraday_signal_refresh_job import IntradaySignalRefreshJob
from src.scheduler.jobs.manual_ticker_review_job import ManualTickerReviewJob
from src.scheduler.jobs.research_job import ResearchJob
from src.scheduler.jobs.sec_edgar_job import SECEdgarJob
from src.scheduler.jobs.strategy_evolution_job import StrategyEvolutionJob
from src.scheduler.jobs.trading_preopen_job import TradingPreopenJob
from src.scheduler.jobs.trading_reflection_job import TradingReflectionJob

logger = get_logger(__name__)


class SchedulerService:
    """
    Wraps APScheduler's :class:`~apscheduler.schedulers.blocking.BlockingScheduler`.

    Jobs are registered explicitly by passing them to the constructor.
    Call :meth:`start` to begin the blocking scheduler loop.

    Example::

        service = SchedulerService(jobs=[SECEdgarJob()])
        service.start()
    """

    def __init__(self, jobs: list[BaseJob]) -> None:
        self._jobs = jobs

    def start(self) -> None:
        """Run ``run_on_startup`` jobs, then start the blocking scheduler."""
        tz = self._resolve_timezone()
        scheduler = BlockingScheduler(timezone=tz)

        for job in self._jobs:
            cfg = job.config
            scheduler.add_job(
                job.run,
                cfg.trigger,
                id=cfg.job_id,
                coalesce=cfg.coalesce,
                max_instances=cfg.max_instances,
                misfire_grace_time=cfg.misfire_grace_time,
                **cfg.trigger_kwargs,
            )
            logger.info("job_registered", job_id=cfg.job_id, trigger=cfg.trigger)

        # Run startup jobs synchronously before entering the scheduler loop
        for job in self._jobs:
            if job.run_on_startup:
                logger.info("job_startup_run", job_id=job.config.job_id)
                job.run()

        logger.info("scheduler_starting", timezone=str(tz), job_count=len(self._jobs))
        scheduler.start()

    @staticmethod
    def _resolve_timezone() -> ZoneInfo:
        resolved = resolve_timezone(SCHEDULER_TIMEZONE, fallback="UTC")
        if str(resolved) == "UTC" and SCHEDULER_TIMEZONE != "UTC":
            logger.warning(
                "invalid_timezone", timezone=SCHEDULER_TIMEZONE, fallback="UTC"
            )
        return resolved


def build_scheduler_jobs() -> list[BaseJob]:
    """Return the default scheduler job set for deployed services."""
    return [
        SECEdgarJob(),
        ResearchJob(),
        EvalJob(),
        TradingPreopenJob(),
        ManualTickerReviewJob(),
        IntradaySignalRefreshJob(),
        TradingReflectionJob(),
        StrategyEvolutionJob(),
    ]
