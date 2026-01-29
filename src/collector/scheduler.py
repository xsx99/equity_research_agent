"""Scheduler for periodic data collection."""
from apscheduler.schedulers.blocking import BlockingScheduler
from src.collector.sec_edgar import SECEdgarCollector
from src.config import COLLECTOR_INTERVAL_MINUTES
from src.logging import get_logger

logger = get_logger(__name__)


def run_collector():
    """Run the SEC EDGAR collector."""
    logger.info("collector_job_started")
    try:
        collector = SECEdgarCollector()
        collector.collect_and_store()
        logger.info("collector_job_completed")
    except Exception as e:
        logger.error("collector_job_failed", error=str(e), exc_info=True)
        raise


def start_scheduler():
    """Start the APScheduler to run collector periodically."""
    logger.info(
        "scheduler_starting",
        interval_minutes=COLLECTOR_INTERVAL_MINUTES,
    )
    
    scheduler = BlockingScheduler()

    # Run immediately on startup
    logger.info("initial_collection_starting")
    run_collector()

    # Schedule periodic runs
    scheduler.add_job(
        run_collector,
        'interval',
        minutes=COLLECTOR_INTERVAL_MINUTES,
        id='form4_collector'
    )

    logger.info(
        "scheduler_started",
        interval_minutes=COLLECTOR_INTERVAL_MINUTES,
        job_id="form4_collector",
    )
    scheduler.start()
