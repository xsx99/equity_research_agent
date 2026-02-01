"""Scheduler for periodic data collection."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.blocking import BlockingScheduler

from src.collector.sec_edgar import SECEdgarCollector
from src.config import (
    COLLECTOR_RUN_ON_STARTUP,
    COLLECTOR_SCHEDULE_HOUR,
    COLLECTOR_SCHEDULE_MINUTE,
    COLLECTOR_TARGET_DAY_OFFSET,
    COLLECTOR_TIMEZONE,
)
from src.logging import get_logger

logger = get_logger(__name__)


def _get_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(COLLECTOR_TIMEZONE)
    except ZoneInfoNotFoundError:
        logger.warning("invalid_timezone", timezone=COLLECTOR_TIMEZONE, fallback="UTC")
        return ZoneInfo("UTC")


def _get_target_date(now: datetime | None = None):
    tz = _get_timezone()
    now = now or datetime.now(tz)
    return (now + timedelta(days=COLLECTOR_TARGET_DAY_OFFSET)).date()


def run_collector(target_date=None):
    """Run the SEC EDGAR collector."""
    logger.info("collector_job_started")
    try:
        collector = SECEdgarCollector()
        if target_date is None:
            target_date = _get_target_date()
        collector.collect_and_store(target_date=target_date)
        logger.info("collector_job_completed")
    except Exception as e:
        logger.error("collector_job_failed", error=str(e), exc_info=True)
        raise


def start_scheduler():
    """Start the APScheduler to run collector periodically."""
    tz = _get_timezone()
    logger.info(
        "scheduler_starting",
        timezone=str(tz),
        schedule_hour=COLLECTOR_SCHEDULE_HOUR,
        schedule_minute=COLLECTOR_SCHEDULE_MINUTE,
        target_day_offset=COLLECTOR_TARGET_DAY_OFFSET,
    )

    scheduler = BlockingScheduler(timezone=tz)

    if COLLECTOR_RUN_ON_STARTUP:
        logger.info("initial_collection_starting")
        run_collector()

    # Schedule periodic runs
    scheduler.add_job(
        run_collector,
        "cron",
        hour=COLLECTOR_SCHEDULE_HOUR,
        minute=COLLECTOR_SCHEDULE_MINUTE,
        id="form4_collector",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    logger.info(
        "scheduler_started",
        timezone=str(tz),
        schedule_hour=COLLECTOR_SCHEDULE_HOUR,
        schedule_minute=COLLECTOR_SCHEDULE_MINUTE,
        target_day_offset=COLLECTOR_TARGET_DAY_OFFSET,
        job_id="form4_collector",
    )
    scheduler.start()
