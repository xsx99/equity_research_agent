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
COLLECTOR_INTERVAL_MINUTES = int(os.getenv("COLLECTOR_INTERVAL_MINUTES", "15"))
COLLECTOR_TIMEZONE = os.getenv("COLLECTOR_TIMEZONE", "US/Eastern")
COLLECTOR_SCHEDULE_HOUR = int(os.getenv("COLLECTOR_SCHEDULE_HOUR", "2"))
COLLECTOR_SCHEDULE_MINUTE = int(os.getenv("COLLECTOR_SCHEDULE_MINUTE", "0"))
COLLECTOR_TARGET_DAY_OFFSET = int(os.getenv("COLLECTOR_TARGET_DAY_OFFSET", "0"))
COLLECTOR_RUN_ON_STARTUP = os.getenv("COLLECTOR_RUN_ON_STARTUP", "false").lower() in (
    "1", "true", "yes", "y"
)

# SEC feed pagination settings
SEC_ATOM_PAGE_SIZE = int(os.getenv("SEC_ATOM_PAGE_SIZE", "100"))
