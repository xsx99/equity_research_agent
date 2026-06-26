from __future__ import annotations


def test_sqlalchemy_repository_facade_is_composed_from_mixins_and_base():
    from src.trading.repositories._base import _RepositoryBase
    from src.trading.repositories.mixins.execution import ExecutionRepositoryMixin
    from src.trading.repositories.mixins.intraday import IntradayRepositoryMixin
    from src.trading.repositories.mixins.macro_calendar import MacroCalendarRepositoryMixin
    from src.trading.repositories.mixins.reflection import ReflectionRepositoryMixin
    from src.trading.repositories.mixins.risk import RiskRepositoryMixin
    from src.trading.repositories.mixins.runtime_misc import RuntimeMiscRepositoryMixin
    from src.trading.repositories.mixins.signals import SignalsRepositoryMixin
    from src.trading.repositories.mixins.strategy import StrategyRepositoryMixin
    from src.trading.repositories.sqlalchemy import SQLAlchemyTradingRepository, SqlAlchemyTradingRepository

    assert SqlAlchemyTradingRepository is SQLAlchemyTradingRepository
    assert issubclass(SQLAlchemyTradingRepository, StrategyRepositoryMixin)
    assert issubclass(SQLAlchemyTradingRepository, SignalsRepositoryMixin)
    assert issubclass(SQLAlchemyTradingRepository, RiskRepositoryMixin)
    assert issubclass(SQLAlchemyTradingRepository, ExecutionRepositoryMixin)
    assert issubclass(SQLAlchemyTradingRepository, IntradayRepositoryMixin)
    assert issubclass(SQLAlchemyTradingRepository, ReflectionRepositoryMixin)
    assert issubclass(SQLAlchemyTradingRepository, MacroCalendarRepositoryMixin)
    assert issubclass(SQLAlchemyTradingRepository, RuntimeMiscRepositoryMixin)
    assert issubclass(SQLAlchemyTradingRepository, _RepositoryBase)


def test_sqlalchemy_repository_public_api_still_exposes_known_methods():
    from src.trading.repositories.sqlalchemy import SQLAlchemyTradingRepository

    for method_name in (
        "save_strategy_definition",
        "load_active_strategy_definitions",
        "save_trading_decision",
        "load_manual_review_audit_rows",
        "load_latest_runtime_run",
    ):
        assert hasattr(SQLAlchemyTradingRepository, method_name)
