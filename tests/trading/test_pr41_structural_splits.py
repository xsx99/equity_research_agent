from __future__ import annotations


def test_capability_modules_export_moved_workflow_surfaces():
    from src.trading.data_sources.universe_scan import UniverseScanPipeline
    from src.trading.execution.paper_execution import (
        PaperExecutionWorkflow,
        PaperExecutionWorkflowResult,
        _build_option_order_request,
    )
    from src.trading.execution.paper_execution_options import (
        _build_option_order_request as option_order_request_from_options,
        _hedge_trading_decision_from_generated_action,
        _option_decision_from_trading_decision,
    )
    from src.trading.portfolio.sync import (
        BrokerPortfolioSyncResult,
        BrokerPortfolioSyncWorkflow,
    )
    from src.trading.signals.pipeline import (
        SignalPipeline,
        SourceIngestionServiceProtocol,
    )
    from src.trading.strategies.scoring import (
        StrategyPipeline,
        StrategyPipelineResult,
    )

    assert callable(_build_option_order_request)
    assert _build_option_order_request is option_order_request_from_options
    assert callable(_hedge_trading_decision_from_generated_action)
    assert callable(_option_decision_from_trading_decision)
    assert PaperExecutionWorkflow is not None
    assert PaperExecutionWorkflowResult is not None
    assert SignalPipeline is not None
    assert SourceIngestionServiceProtocol is not None
    assert StrategyPipeline is not None
    assert StrategyPipelineResult is not None
    assert BrokerPortfolioSyncWorkflow is not None
    assert BrokerPortfolioSyncResult is not None
    assert UniverseScanPipeline is not None


def test_workflow_shims_preserve_moved_capability_identity():
    import src.trading.data_sources.universe_scan as canonical_universe
    import src.trading.execution.paper_execution as canonical_execution
    import src.trading.execution.paper_execution_options as canonical_execution_options
    import src.trading.portfolio.sync as canonical_portfolio
    import src.trading.signals.pipeline as canonical_signals
    import src.trading.strategies.scoring as canonical_strategies
    import src.trading.workflows.paper_execution as workflow_execution
    import src.trading.workflows.paper_execution_options as workflow_execution_options
    import src.trading.workflows.portfolio_sync as workflow_portfolio
    import src.trading.workflows.signal_snapshot as workflow_signals
    import src.trading.workflows.strategy_scoring as workflow_strategies
    import src.trading.workflows.universe_scan as workflow_universe

    assert workflow_execution.PaperExecutionWorkflow is canonical_execution.PaperExecutionWorkflow
    assert (
        workflow_execution.PaperExecutionWorkflowResult
        is canonical_execution.PaperExecutionWorkflowResult
    )
    assert (
        workflow_execution._build_option_order_request
        is canonical_execution_options._build_option_order_request
    )
    assert (
        workflow_execution_options._build_option_order_request
        is canonical_execution_options._build_option_order_request
    )
    assert (
        workflow_execution._build_option_order_request
        is workflow_execution_options._build_option_order_request
    )
    assert workflow_signals.SignalPipeline is canonical_signals.SignalPipeline
    assert (
        workflow_signals.SourceIngestionServiceProtocol
        is canonical_signals.SourceIngestionServiceProtocol
    )
    assert workflow_strategies.StrategyPipeline is canonical_strategies.StrategyPipeline
    assert (
        workflow_strategies.StrategyPipelineResult
        is canonical_strategies.StrategyPipelineResult
    )
    assert (
        workflow_portfolio.BrokerPortfolioSyncWorkflow
        is canonical_portfolio.BrokerPortfolioSyncWorkflow
    )
    assert (
        workflow_portfolio.BrokerPortfolioSyncResult
        is canonical_portfolio.BrokerPortfolioSyncResult
    )
    assert workflow_universe.UniverseScanPipeline is canonical_universe.UniverseScanPipeline


def test_pr41_import_smoke_for_runtime_and_workflow_entrypoints():
    import src.trading.intraday.rebalance as rebalance
    import src.trading.runtime.intraday_refresh_dependencies as intraday_dependencies
    import src.trading.runtime.preopen_dependencies as preopen_dependencies
    import src.trading.workflows as workflows

    assert rebalance is not None
    assert intraday_dependencies is not None
    assert preopen_dependencies is not None
    assert workflows is not None
