"""Trading foundation ORM models package."""

from src.db.models.trading.enums import *
from src.db.models.trading.strategy import *
from src.db.models.trading.llm import *
from src.db.models.trading.signals import *
from src.db.models.trading.macro_calendar import *
from src.db.models.trading.risk import *
from src.db.models.trading.execution import *
from src.db.models.trading.intraday import *
from src.db.models.trading.reflection import *
from src.db.models.trading.universe import *

for _module_name in (
    "enums",
    "strategy",
    "llm",
    "signals",
    "macro_calendar",
    "risk",
    "execution",
    "intraday",
    "reflection",
    "universe",
):
    globals().pop(_module_name, None)


def __dir__():
    hidden_names = {
        "annotations",
        "enums",
        "strategy",
        "llm",
        "signals",
        "macro_calendar",
        "risk",
        "execution",
        "intraday",
        "reflection",
        "universe",
    }
    return sorted(
        name
        for name in globals()
        if not name.startswith("_") and name not in hidden_names
    )


del _module_name
