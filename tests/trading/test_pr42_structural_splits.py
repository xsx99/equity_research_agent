from __future__ import annotations


def test_shared_runtime_utilities_move_to_capability_homes():
    import src.trading.risk.lookahead_risk as canonical_lookahead
    import src.trading.runtime.lookahead_risk as runtime_lookahead
    import src.trading.runtime.trade_day as runtime_trade_day
    import src.trading.trade_day as canonical_trade_day

    assert canonical_trade_day.trade_date_for is runtime_trade_day.trade_date_for
    assert canonical_trade_day.local_day_bounds_utc is runtime_trade_day.local_day_bounds_utc
    assert (
        canonical_lookahead.LookaheadRiskWorkflowHelper
        is runtime_lookahead.LookaheadRiskWorkflowHelper
    )


def test_preopen_phase_exports_and_runtime_shims_preserve_identity():
    import src.trading.phases.preopen as canonical_preopen
    import src.trading.phases.preopen.dependencies as canonical_dependencies
    import src.trading.phases.preopen.risk as canonical_risk
    import src.trading.phases.preopen.runner as canonical_runner
    import src.trading.runtime.preopen as runtime_preopen
    import src.trading.runtime.preopen_dependencies as runtime_dependencies
    import src.trading.runtime.preopen_risk as runtime_risk
    import src.trading.runtime.preopen_runner as runtime_runner

    assert canonical_preopen.run_preopen_once is runtime_preopen.run_preopen_once
    assert canonical_preopen.run_live_preopen_once is runtime_preopen.run_live_preopen_once
    assert (
        canonical_preopen.build_live_preopen_dependencies
        is canonical_dependencies.build_live_preopen_dependencies
    )
    assert (
        canonical_dependencies.build_live_preopen_dependencies
        is runtime_dependencies.build_live_preopen_dependencies
    )
    assert canonical_runner.LivePreopenRuntime is runtime_runner.LivePreopenRuntime
    assert canonical_risk._LiveRiskWorkflow is runtime_risk._LiveRiskWorkflow


def test_manual_review_phase_exports_and_old_paths_preserve_identity():
    import src.trading.manual_review.requests as requests_shim
    import src.trading.manual_review.sqlalchemy as sqlalchemy_shim
    import src.trading.phases.manual_review as canonical_manual_review
    import src.trading.phases.manual_review.requests as canonical_requests
    import src.trading.phases.manual_review.sqlalchemy as canonical_sqlalchemy
    import src.trading.phases.preopen as canonical_preopen
    import src.trading.runtime.manual_review as runtime_manual_review

    assert (
        canonical_manual_review.LiveManualReviewRuntime
        is runtime_manual_review.LiveManualReviewRuntime
    )
    assert (
        canonical_manual_review.build_live_manual_review_dependencies
        is runtime_manual_review.build_live_manual_review_dependencies
    )
    assert (
        canonical_manual_review.build_live_preopen_dependencies
        is canonical_preopen.build_live_preopen_dependencies
    )
    assert canonical_requests.ManualTickerRequest is requests_shim.ManualTickerRequest
    assert (
        canonical_requests.ManualTickerRequestService
        is requests_shim.ManualTickerRequestService
    )
    assert (
        canonical_sqlalchemy.SQLAlchemyManualTickerRequestService
        is sqlalchemy_shim.SQLAlchemyManualTickerRequestService
    )


def test_intraday_phase_exports_and_old_paths_preserve_identity():
    import src.trading.intraday.news_alerts as news_alerts_shim
    import src.trading.intraday.rebalance as rebalance_shim
    import src.trading.intraday.signals as signals_shim
    import src.trading.phases.intraday as canonical_intraday
    import src.trading.phases.intraday.dependencies as canonical_dependencies
    import src.trading.phases.intraday.helpers as canonical_helpers
    import src.trading.phases.intraday.news_alerts as canonical_news_alerts
    import src.trading.phases.intraday.rebalance as canonical_rebalance
    import src.trading.phases.intraday.runner as canonical_runner
    import src.trading.phases.intraday.signals as canonical_signals
    import src.trading.runtime.intraday_refresh as runtime_intraday
    import src.trading.runtime.intraday_refresh_dependencies as runtime_dependencies
    import src.trading.runtime.intraday_refresh_helpers as runtime_helpers
    import src.trading.runtime.intraday_refresh_runner as runtime_runner

    assert (
        canonical_intraday.run_intraday_refresh_once
        is runtime_intraday.run_intraday_refresh_once
    )
    assert (
        canonical_intraday.run_live_intraday_refresh_once
        is runtime_intraday.run_live_intraday_refresh_once
    )
    assert (
        canonical_dependencies.build_live_intraday_refresh_dependencies
        is runtime_dependencies.build_live_intraday_refresh_dependencies
    )
    assert (
        canonical_runner.LiveIntradayRefreshRuntime
        is runtime_runner.LiveIntradayRefreshRuntime
    )
    assert (
        canonical_helpers._build_intraday_refresh_payload
        is runtime_helpers._build_intraday_refresh_payload
    )
    assert (
        canonical_rebalance.IntradayRebalancePipeline
        is rebalance_shim.IntradayRebalancePipeline
    )
    assert canonical_news_alerts.NewsAlertService is news_alerts_shim.NewsAlertService
    assert (
        canonical_signals.IntradaySignalSnapshotRecord
        is signals_shim.IntradaySignalSnapshotRecord
    )


def test_pr42_import_smoke_for_entrypoints_and_shims():
    import src.scheduler.jobs.intraday_signal_refresh_job as intraday_job
    import src.scheduler.jobs.manual_ticker_review_job as manual_job
    import src.scheduler.jobs.trading_preopen_job as preopen_job
    import src.trading.runtime.dispatch as dispatch
    import src.trading.runtime.intraday_refresh as intraday_refresh
    import src.trading.runtime.manual_review as manual_review
    import src.trading.runtime.preopen as preopen

    assert dispatch is not None
    assert preopen is not None
    assert manual_review is not None
    assert intraday_refresh is not None
    assert preopen_job is not None
    assert manual_job is not None
    assert intraday_job is not None
