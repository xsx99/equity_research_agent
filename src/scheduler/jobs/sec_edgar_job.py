"""Scheduled job for SEC EDGAR Form 4 collection."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from src.collectors.sec_edgar.collector import SECEdgarCollector
from src.core.config import (
    SCHEDULER_TIMEZONE,
    SEC_EDGAR_RUN_ON_STARTUP,
    SEC_EDGAR_SCHEDULE_HOUR,
    SEC_EDGAR_SCHEDULE_MINUTE,
    SEC_EDGAR_TARGET_DAY_OFFSET,
)
from src.core.logging import get_logger
from src.core.timezones import resolve_timezone
from src.scheduler.base import BaseJob, JobConfig

logger = get_logger(__name__)


class SECEdgarJob(BaseJob):
    """
    Scheduled job that runs :class:`~src.collectors.sec_edgar.collector.SECEdgarCollector`
    on a daily cron schedule.

    The target date is computed as ``today + SEC_EDGAR_TARGET_DAY_OFFSET``.
    Set ``SEC_EDGAR_RUN_ON_STARTUP=true`` to execute a collection run immediately
    when the scheduler starts, in addition to the regular schedule.
    """

    run_on_startup: bool = SEC_EDGAR_RUN_ON_STARTUP

    @property
    def config(self) -> JobConfig:
        return JobConfig(
            job_id="sec_edgar_form4",
            trigger="cron",
            trigger_kwargs={
                "hour": SEC_EDGAR_SCHEDULE_HOUR,
                "minute": SEC_EDGAR_SCHEDULE_MINUTE,
            },
        )

    def run(self, target_date=None) -> None:
        """Execute one SEC EDGAR collection run."""
        logger.info("sec_edgar_job_started")
        try:
            if target_date is None:
                target_date = self._get_target_date()

            collector = SECEdgarCollector(timezone=SCHEDULER_TIMEZONE)
            result = collector.collect(target_date=target_date)

            logger.info(
                "sec_edgar_job_completed",
                target_date=target_date.isoformat(),
                upserted=result.upserted,
                skipped=result.skipped,
                errors=result.errors,
            )
        except Exception as e:
            logger.error("sec_edgar_job_failed", error=str(e), exc_info=True)

    def _get_target_date(self, now: Optional[datetime] = None):
        tz = resolve_timezone(SCHEDULER_TIMEZONE, fallback="UTC")
        now = now or datetime.now(tz)
        return (now + timedelta(days=SEC_EDGAR_TARGET_DAY_OFFSET)).date()
