"""Entry point for running the scheduler service."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.connection import init_db
from src.core.logging import get_logger
from src.scheduler.service import SchedulerService, build_scheduler_jobs

logger = get_logger(__name__)


def main():
    """Initialize database and start the scheduler."""
    logger.info("initializing_database")
    init_db()
    logger.info("database_ready")

    logger.info("scheduler_service_starting")
    SchedulerService(jobs=build_scheduler_jobs()).start()


if __name__ == "__main__":
    main()
