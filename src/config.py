"""Configuration settings."""
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/insider_trading"
)

# SEC EDGAR settings
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "YourCompany contact@yourcompany.com")
SEC_RATE_LIMIT = 10  # requests per second (SEC allows 10)

# Scheduler settings
SCHEDULER_TIMEZONE = os.getenv(
    "SCHEDULER_TIMEZONE",
    os.getenv("COLLECTOR_TIMEZONE", "US/Eastern"),
)
SEC_EDGAR_SCHEDULE_HOUR = int(
    os.getenv("SEC_EDGAR_SCHEDULE_HOUR", os.getenv("COLLECTOR_SCHEDULE_HOUR", "2"))
)
SEC_EDGAR_SCHEDULE_MINUTE = int(
    os.getenv("SEC_EDGAR_SCHEDULE_MINUTE", os.getenv("COLLECTOR_SCHEDULE_MINUTE", "0"))
)
SEC_EDGAR_TARGET_DAY_OFFSET = int(
    os.getenv("SEC_EDGAR_TARGET_DAY_OFFSET", os.getenv("COLLECTOR_TARGET_DAY_OFFSET", "0"))
)
SEC_EDGAR_RUN_ON_STARTUP = os.getenv(
    "SEC_EDGAR_RUN_ON_STARTUP",
    os.getenv("COLLECTOR_RUN_ON_STARTUP", "false"),
).lower() in ("1", "true", "yes", "y")

# SEC feed pagination settings
SEC_ATOM_PAGE_SIZE = int(os.getenv("SEC_ATOM_PAGE_SIZE", "100"))
