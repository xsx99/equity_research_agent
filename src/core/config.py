import os
import warnings
from pathlib import Path

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
    "America/New_York",
)
SEC_EDGAR_SCHEDULE_HOUR = int(
    os.getenv("SEC_EDGAR_SCHEDULE_HOUR", "2")
)
SEC_EDGAR_SCHEDULE_MINUTE = int(
    os.getenv("SEC_EDGAR_SCHEDULE_MINUTE", "0")
)
SEC_EDGAR_TARGET_DAY_OFFSET = int(
    os.getenv("SEC_EDGAR_TARGET_DAY_OFFSET", "-1")
)
SEC_EDGAR_RUN_ON_STARTUP = os.getenv(
    "SEC_EDGAR_RUN_ON_STARTUP",
    "false",
).lower() in ("1", "true", "yes", "y")

# SEC feed pagination settings
SEC_ATOM_PAGE_SIZE = int(os.getenv("SEC_ATOM_PAGE_SIZE", "100"))

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
FMP_API_KEY = os.getenv("FMP_API_KEY")
APP_ENV = os.getenv("APP_ENV", "development").lower()
RESEARCH_MODEL_NAME = os.getenv("RESEARCH_MODEL_NAME", "gemini-2.5-flash-lite")
DEFAULT_FAST_MODEL_NAME = os.getenv("DEFAULT_FAST_MODEL_NAME", RESEARCH_MODEL_NAME)
TRADING_MODEL_NAME = os.getenv("TRADING_MODEL_NAME", DEFAULT_FAST_MODEL_NAME)
INTRADAY_REBALANCE_MODEL_NAME = os.getenv("INTRADAY_REBALANCE_MODEL_NAME", TRADING_MODEL_NAME)
REFLECTION_MODEL_NAME_RAW = os.getenv("REFLECTION_MODEL_NAME", "").strip()
REFLECTION_MODEL_NAME = REFLECTION_MODEL_NAME_RAW or DEFAULT_FAST_MODEL_NAME
REFLECTION_MODEL_CONFIGURED = bool(REFLECTION_MODEL_NAME_RAW)
TRADING_UNIVERSE_SYMBOLS = os.getenv("TRADING_UNIVERSE_SYMBOLS", "")


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "y")


TRADING_EXECUTE_PAPER_ORDERS = _env_bool("TRADING_EXECUTE_PAPER_ORDERS", True)
TRADING_EXECUTE_PAPER_OPTION_ORDERS = _env_bool("TRADING_EXECUTE_PAPER_OPTION_ORDERS", False)

if APP_ENV in {"prod", "production"} and not REFLECTION_MODEL_CONFIGURED:
    warnings.warn(
        "REFLECTION_MODEL_NAME is not configured; falling back to DEFAULT_FAST_MODEL_NAME",
        RuntimeWarning,
        stacklevel=1,
    )

# Research scheduler settings (weekdays only; pre-open batch)
RESEARCH_SCHEDULE_HOUR = int(os.getenv("RESEARCH_SCHEDULE_HOUR", "9"))
RESEARCH_SCHEDULE_MINUTE = int(os.getenv("RESEARCH_SCHEDULE_MINUTE", "20"))
RESEARCH_RUN_ON_STARTUP = os.getenv("RESEARCH_RUN_ON_STARTUP", "false").lower() in (
    "1", "true", "yes", "y"
)

# Eval scheduler settings (once daily, shortly after close)
EVAL_SCHEDULE_HOUR = int(os.getenv("EVAL_SCHEDULE_HOUR", "16"))
EVAL_SCHEDULE_MINUTE = int(os.getenv("EVAL_SCHEDULE_MINUTE", "10"))
EVAL_RUN_ON_STARTUP = os.getenv("EVAL_RUN_ON_STARTUP", "false").lower() in (
    "1", "true", "yes", "y"
)
