"""Research pipeline package — orchestration, repository helpers, and pipeline runner."""
from src.research.repository import (
    get_active_tickers,
    get_watchlist,
    add_ticker,
    deactivate_ticker,
    create_run,
    mark_run_running,
    mark_run_succeeded,
    mark_run_failed,
    persist_output,
)
from src.research.pipeline import ResearchPipeline, PipelineResult, TickerResult

__all__ = [
    "get_active_tickers",
    "get_watchlist",
    "add_ticker",
    "deactivate_ticker",
    "create_run",
    "mark_run_running",
    "mark_run_succeeded",
    "mark_run_failed",
    "persist_output",
    "ResearchPipeline",
    "PipelineResult",
    "TickerResult",
]
