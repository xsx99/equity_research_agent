"""Configuration settings."""
from pathlib import Path
import os

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
load_dotenv(ENV_FILE)

DATABASE_URL = os.getenv("DATABASE_URL") or (
    "postgresql://{user}:{password}@{host}:{port}/{db}".format(
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        db=os.getenv("POSTGRES_DATABASE", "mono_db"),
    )
)

# SEC EDGAR settings
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "lillian@synchronicity.com")
SEC_RATE_LIMIT = 10  # requests per second (SEC allows 10)

# Scheduler settings
SCHEDULER_TIMEZONE = os.getenv(
    "SCHEDULER_TIMEZONE",
    "US/Eastern",
)
SEC_EDGAR_SCHEDULE_HOUR = int(
    os.getenv("SEC_EDGAR_SCHEDULE_HOUR", "2")
)
SEC_EDGAR_SCHEDULE_MINUTE = int(
    os.getenv("SEC_EDGAR_SCHEDULE_MINUTE", "0")
)
SEC_EDGAR_TARGET_DAY_OFFSET = int(
    os.getenv("SEC_EDGAR_TARGET_DAY_OFFSET", "0")
)
SEC_EDGAR_RUN_ON_STARTUP = os.getenv(
    "SEC_EDGAR_RUN_ON_STARTUP",
    "false",
).lower() in ("1", "true", "yes", "y")

# SEC feed pagination settings
SEC_ATOM_PAGE_SIZE = int(os.getenv("SEC_ATOM_PAGE_SIZE", "100"))

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
RESEARCH_MODEL_NAME = os.getenv("RESEARCH_MODEL_NAME", "gemini-2.5-flash-lite")
