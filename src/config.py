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
