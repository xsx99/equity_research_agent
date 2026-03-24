"""Evaluation pipeline — batch orchestration for scoring matured research runs.

Responsible for:
- Querying succeeded runs whose time_horizon window has elapsed.
- Fetching realized return (ticker) and benchmark return (SPY by default).
- Applying rule_v1 labeling.
- Upserting EvalResult rows via the repository layer.

Does not commit; callers own transaction boundaries.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.models.evaluation import EvalOutcomeLabel, EvaluationMethod
from src.db.models.research import ResearchOutput, ResearchRun, ResearchTimeHorizon
from src.research import repository
from src.tools.market_data import AlpacaMarketDataProvider, MarketDataProvider, fetch_return_over_range

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pure labeling function
# ---------------------------------------------------------------------------


def apply_rule_v1(
    decision: str,
    realized_return: Optional[float],
    benchmark_return: Optional[float],
    neutral_threshold: float = 0.01,
) -> Optional[str]:
    """Apply rule_v1 label matrix.

    Returns None when realized_return is None (market data unavailable).
    When benchmark_return is None, bullish/bearish cannot achieve 'correct'
    (defaults to 'partially_correct' for correct-direction moves).
    """
    if realized_return is None:
        return None

    if decision == "bullish":
        if realized_return < 0:
            return EvalOutcomeLabel.WRONG_DIRECTION.value
        if (
            realized_return > 0
            and benchmark_return is not None
            and realized_return >= benchmark_return
        ):
            return EvalOutcomeLabel.CORRECT.value
        return EvalOutcomeLabel.PARTIALLY_CORRECT.value

    if decision == "bearish":
        if realized_return > 0:
            return EvalOutcomeLabel.WRONG_DIRECTION.value
        if (
            realized_return < 0
            and benchmark_return is not None
            and realized_return <= benchmark_return
        ):
            return EvalOutcomeLabel.CORRECT.value
        return EvalOutcomeLabel.PARTIALLY_CORRECT.value

    # neutral or abstain
    if abs(realized_return) > neutral_threshold:
        return EvalOutcomeLabel.WRONG_DIRECTION.value
    return EvalOutcomeLabel.UNINFORMATIVE.value


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EvalTickerResult:
    """Outcome of evaluating a single research run."""

    run_id: uuid.UUID
    ticker: str
    success: bool
    outcome_label: Optional[str] = None
    error: Optional[str] = None


@dataclass
class EvalPipelineResult:
    """Aggregate outcome of a full eval batch."""

    evaluated: int = 0
    failed: int = 0
    skipped: int = 0
    ticker_results: list[EvalTickerResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class EvalPipeline:
    """Orchestrates the full evaluation batch pipeline.

    Parameters
    ----------
    session:
        SQLAlchemy session. Does not commit; callers own transactions.
    provider:
        MarketDataProvider for fetching returns. Defaults to AlpacaMarketDataProvider.
    benchmark_symbol:
        Ticker symbol used for benchmark comparison. Default: 'SPY'.
    neutral_threshold:
        Abs return threshold above which neutral/abstain is labeled wrong_direction.
    """

    def __init__(
        self,
        session: Session,
        provider: Optional[MarketDataProvider] = None,
        benchmark_symbol: str = "SPY",
        neutral_threshold: float = 0.01,
    ) -> None:
        self.session = session
        self.provider = provider or AlpacaMarketDataProvider()
        self.benchmark_symbol = benchmark_symbol
        self.neutral_threshold = neutral_threshold
        self._benchmark_cache: dict[tuple[str, date, date, int], Optional[float]] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run_all(self, as_of: Optional[datetime] = None) -> EvalPipelineResult:
        """Evaluate all eligible runs."""
        as_of = as_of or datetime.now(timezone.utc)
        eligible = repository.get_eligible_runs(self.session, as_of_cutoff=as_of)

        if not eligible:
            logger.info("eval_pipeline_no_eligible_runs")
            return EvalPipelineResult()

        logger.info("eval_pipeline_started", run_count=len(eligible))
        result = EvalPipelineResult()

        for run, output in eligible:
            ticker_result = self._eval_run(run, output)
            result.ticker_results.append(ticker_result)
            if ticker_result.success:
                result.evaluated += 1
            elif ticker_result.error and ticker_result.error.startswith("invalid_time_horizon"):
                result.skipped += 1
            else:
                result.failed += 1

        logger.info(
            "eval_pipeline_finished",
            evaluated=result.evaluated,
            failed=result.failed,
        )
        return result

    def run_single(self, run_id: uuid.UUID) -> EvalTickerResult:
        """Force-evaluate a single run by run_id, bypassing eligibility check."""
        run = self.session.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
        if run is None:
            return EvalTickerResult(run_id=run_id, ticker="unknown", success=False, error="run_not_found")
        output = self.session.query(ResearchOutput).filter(ResearchOutput.run_id == run_id).first()
        if output is None:
            return EvalTickerResult(run_id=run_id, ticker=run.ticker, success=False, error="no_output_row")
        return self._eval_run(run, output)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _eval_run(self, run: ResearchRun, output: ResearchOutput) -> EvalTickerResult:
        try:
            horizon_map = ResearchTimeHorizon.days_mapping()
            horizon_days = horizon_map.get(output.time_horizon)
            if horizon_days is None:
                logger.warning(
                    "eval_pipeline_invalid_horizon",
                    run_id=str(run.run_id),
                    time_horizon=output.time_horizon,
                )
                return EvalTickerResult(
                    run_id=run.run_id,
                    ticker=run.ticker,
                    success=False,
                    error=f"invalid_time_horizon:{output.time_horizon}",
                )

            start_date = run.as_of.date()
            end_date = start_date + timedelta(days=horizon_days)

            realized_return = self._fetch_return(run.ticker, start_date, end_date)
            benchmark_return = self._fetch_benchmark(start_date, end_date, horizon_days)

            outcome_label = apply_rule_v1(
                decision=output.decision,
                realized_return=realized_return,
                benchmark_return=benchmark_return,
                neutral_threshold=self.neutral_threshold,
            )

            repository.upsert_eval_result(
                self.session,
                run_id=run.run_id,
                horizon_days=horizon_days,
                realized_return=realized_return,
                benchmark_return=benchmark_return,
                benchmark_symbol=self.benchmark_symbol,
                evaluation_method=EvaluationMethod.RULE_V1.value,
                evaluation_params=None,
                outcome_label=outcome_label,
            )

            logger.info(
                "eval_pipeline_run_evaluated",
                run_id=str(run.run_id),
                ticker=run.ticker,
                outcome_label=outcome_label,
            )
            return EvalTickerResult(
                run_id=run.run_id,
                ticker=run.ticker,
                success=True,
                outcome_label=outcome_label,
            )

        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                "eval_pipeline_run_failed",
                run_id=str(run.run_id),
                ticker=run.ticker,
                error=error_msg,
                exc_info=True,
            )
            return EvalTickerResult(
                run_id=run.run_id,
                ticker=run.ticker,
                success=False,
                error=error_msg,
            )

    def _fetch_return(self, ticker: str, start_date: date, end_date: date) -> Optional[float]:
        try:
            return fetch_return_over_range(ticker, start_date, end_date, provider=self.provider)
        except Exception as exc:
            logger.warning(
                "eval_pipeline_fetch_return_failed",
                ticker=ticker,
                error=str(exc),
            )
            return None

    def _fetch_benchmark(self, start_date: date, end_date: date, horizon_days: int) -> Optional[float]:
        cache_key = (self.benchmark_symbol, start_date, end_date, horizon_days)
        if cache_key in self._benchmark_cache:
            return self._benchmark_cache[cache_key]
        value = self._fetch_return(self.benchmark_symbol, start_date, end_date)
        self._benchmark_cache[cache_key] = value
        return value
