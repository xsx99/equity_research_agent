"""Entry point for running the data collector service."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.connection import init_db
from src.collector.scheduler import start_scheduler


def main():
    """Initialize database and start the scheduler."""
    print("Initializing database...")
    init_db()
    print("Database ready.")

    print("Starting SEC Form 4 collector service...")
    start_scheduler()


if __name__ == "__main__":
    main()
