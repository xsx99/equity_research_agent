from __future__ import annotations


def test_option_strategy_builder_exports_trading_decision_option_helpers():
    from src.trading.workflows.option_strategy_builder import (
        _build_option_strategy_payload,
        _build_option_strategy_payloads,
        _decision_action_for_expression,
    )
    from src.trading.workflows.trading_decision import (
        _build_option_strategy_payloads as trading_decision_option_payloads,
    )

    assert callable(_build_option_strategy_payload)
    assert callable(_decision_action_for_expression)
    assert trading_decision_option_payloads is _build_option_strategy_payloads


def test_paper_execution_options_exports_option_execution_helpers():
    from src.trading.workflows.paper_execution_options import (
        _build_option_order_request,
        _hedge_trading_decision_from_generated_action,
        _option_decision_from_trading_decision,
    )
    from src.trading.workflows.paper_execution import (
        _build_option_order_request as paper_execution_option_order_request,
    )

    assert callable(_hedge_trading_decision_from_generated_action)
    assert callable(_option_decision_from_trading_decision)
    assert paper_execution_option_order_request is _build_option_order_request


def test_today_loaders_exports_router_private_helpers():
    from src.web.routers.today_loaders import _TAB_LABELS, _build_header, _load_trade_detail
    from src.web.routers.today import (
        _build_header as router_build_header,
        _load_trade_detail as router_load_trade_detail,
    )

    assert ("portfolio", "Portfolio") in _TAB_LABELS
    assert callable(_build_header)
    assert callable(_load_trade_detail)
    assert callable(router_build_header)
    assert callable(router_load_trade_detail)


def test_trading_models_package_reexports_submodule_models():
    from src.db.models.trading.enums import StrategyLifecycleStatus
    from src.db.models.trading.execution import TradingDecision
    from src.db.models.trading import TradingDecision as reexported_trading_decision

    assert StrategyLifecycleStatus.ACTIVE == "active"
    assert reexported_trading_decision is TradingDecision


def test_today_workspace_split_keeps_public_builder_and_detail_module():
    from src.web.presenters.today_workspace import build_ticker_workspace
    from src.web.presenters.today_workspace_detail import _build_detail

    assert callable(build_ticker_workspace)
    assert callable(_build_detail)
