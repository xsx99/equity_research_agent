"""Entry point for running the data collector service."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.connection import init_db
from src.collector.scheduler import start_scheduler
from src.logging import get_logger

logger = get_logger(__name__)


def main():
    """Initialize database and start the scheduler."""
    logger.info("initializing_database")
    init_db()
    logger.info("database_ready")

    logger.info("collector_service_starting")
    start_scheduler()


if __name__ == "__main__":
    main()
