"""Scheduled SEC EDGAR job registration."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.base import BaseScheduler

from src.collector.sec_edgar import collect_and_store
from src.config import (
    SCHEDULER_TIMEZONE,
    SEC_EDGAR_RUN_ON_STARTUP,
    SEC_EDGAR_SCHEDULE_HOUR,
    SEC_EDGAR_SCHEDULE_MINUTE,
    SEC_EDGAR_TARGET_DAY_OFFSET,
)
from src.logging import get_logger

logger = get_logger(__name__)

SEC_EDGAR_JOB_ID = "sec_edgar_form4"


def _get_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(SCHEDULER_TIMEZONE)
    except ZoneInfoNotFoundError:
        logger.warning("invalid_timezone", timezone=SCHEDULER_TIMEZONE, fallback="UTC")
        return ZoneInfo("UTC")


def _get_target_date(now: datetime | None = None):
    tz = _get_timezone()
    now = now or datetime.now(tz)
    return (now + timedelta(days=SEC_EDGAR_TARGET_DAY_OFFSET)).date()


def run_sec_edgar_collection_job(target_date=None):
    """Run the SEC EDGAR collection job once."""
    logger.info("sec_edgar_job_started")
    try:
        if target_date is None:
            target_date = _get_target_date()
        collect_and_store(target_date=target_date, timezone=SCHEDULER_TIMEZONE)
        logger.info("sec_edgar_job_completed", target_date=target_date.isoformat())
    except Exception as e:
        logger.error("sec_edgar_job_failed", error=str(e), exc_info=True)
        raise


def register_sec_edgar_jobs(scheduler: BaseScheduler) -> list[str]:
    """Register SEC EDGAR jobs on the shared scheduler."""
    if SEC_EDGAR_RUN_ON_STARTUP:
        logger.info("sec_edgar_initial_run_starting")
        run_sec_edgar_collection_job()

    scheduler.add_job(
        run_sec_edgar_collection_job,
        "cron",
        hour=SEC_EDGAR_SCHEDULE_HOUR,
        minute=SEC_EDGAR_SCHEDULE_MINUTE,
        id=SEC_EDGAR_JOB_ID,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    logger.info(
        "sec_edgar_job_registered",
        job_id=SEC_EDGAR_JOB_ID,
        schedule_hour=SEC_EDGAR_SCHEDULE_HOUR,
        schedule_minute=SEC_EDGAR_SCHEDULE_MINUTE,
        target_day_offset=SEC_EDGAR_TARGET_DAY_OFFSET,
    )
    return [SEC_EDGAR_JOB_ID]
