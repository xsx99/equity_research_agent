"""Scheduler for periodic data collection."""
from apscheduler.schedulers.blocking import BlockingScheduler
from src.collector.sec_edgar import SECEdgarCollector
from src.config import COLLECTOR_INTERVAL_MINUTES


def run_collector():
    """Run the SEC EDGAR collector."""
    collector = SECEdgarCollector()
    collector.collect_and_store()


def start_scheduler():
    """Start the APScheduler to run collector periodically."""
    scheduler = BlockingScheduler()

    # Run immediately on startup
    run_collector()

    # Schedule periodic runs
    scheduler.add_job(
        run_collector,
        'interval',
        minutes=COLLECTOR_INTERVAL_MINUTES,
        id='form4_collector'
    )

    print(f"Scheduler started. Running every {COLLECTOR_INTERVAL_MINUTES} minutes.")
    scheduler.start()
