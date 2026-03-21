"""Scheduler service for background jobs."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.blocking import BlockingScheduler

from src.collector.sec_edgar_jobs import register_sec_edgar_jobs
from src.config import SCHEDULER_TIMEZONE
from src.logging import get_logger

logger = get_logger(__name__)


def _get_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(SCHEDULER_TIMEZONE)
    except ZoneInfoNotFoundError:
        logger.warning("invalid_timezone", timezone=SCHEDULER_TIMEZONE, fallback="UTC")
        return ZoneInfo("UTC")


def start_scheduler():
    """Start the APScheduler service and register jobs."""
    tz = _get_timezone()
    logger.info("scheduler_starting", timezone=str(tz))

    scheduler = BlockingScheduler(timezone=tz)
    job_ids = register_sec_edgar_jobs(scheduler)
    logger.info("scheduler_started", timezone=str(tz), job_ids=job_ids)
    scheduler.start()
