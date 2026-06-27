"""SQLAlchemy-backed persistence for trading artifacts."""
from __future__ import annotations

from src.trading.repositories._base import _RepositoryBase
from src.trading.repositories._base_payloads import _trading_decision_payload
from src.trading.repositories.mixins.execution import ExecutionRepositoryMixin
from src.trading.repositories.mixins.intraday import IntradayRepositoryMixin
from src.trading.repositories.mixins.macro_calendar import MacroCalendarRepositoryMixin
from src.trading.repositories.mixins.reflection import ReflectionRepositoryMixin
from src.trading.repositories.mixins.risk import RiskRepositoryMixin
from src.trading.repositories.mixins.runtime_misc import RuntimeMiscRepositoryMixin
from src.trading.repositories.mixins.signals import SignalsRepositoryMixin
from src.trading.repositories.mixins.strategy import StrategyRepositoryMixin


class SQLAlchemyTradingRepository(
    StrategyRepositoryMixin,
    SignalsRepositoryMixin,
    RiskRepositoryMixin,
    ExecutionRepositoryMixin,
    IntradayRepositoryMixin,
    ReflectionRepositoryMixin,
    MacroCalendarRepositoryMixin,
    RuntimeMiscRepositoryMixin,
    _RepositoryBase,
):
    """Composed trading repository. Behavior matches the pre-split implementation."""


SqlAlchemyTradingRepository = SQLAlchemyTradingRepository
