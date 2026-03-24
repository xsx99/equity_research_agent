"""Evaluation pipeline — batch orchestration for scoring same-day research runs.

Responsible for:
- Querying same-day succeeded runs that are eligible for evaluation.
- Fetching realized return (ticker) and benchmark return (SPY by default).
- Applying rule_v1 labeling.
- Upserting EvalResult rows via the repository layer.

Does not commit; callers own transaction boundaries.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.models.evaluation import EvalOutcomeLabel, EvaluationMethod
from src.db.models.research import ResearchOutput, ResearchRun, ResearchTimeHorizon
from src.research import repository
from src.tools.market_data import (
    AlpacaMarketDataProvider,
    MARKET_TIMEZONE,
    MarketDataProvider,
    REGULAR_MARKET_OPEN,
    fetch_close_price_on_date,
    fetch_open_to_close_return,
    fetch_price_at_or_before,
)

logger = get_logger(__name__)


def apply_rule_v1(
    decision: str,
    realized_return: Optional[float],
    benchmark_return: Optional[float],
    neutral_threshold: float = 0.01,
) -> Optional[str]:
    """Apply rule_v1 label matrix."""
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

    if abs(realized_return) > neutral_threshold:
        return EvalOutcomeLabel.WRONG_DIRECTION.value
    return EvalOutcomeLabel.UNINFORMATIVE.value


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


class EvalPipeline:
    """Orchestrates the full evaluation batch pipeline."""

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

    def run_all(self, as_of: Optional[datetime] = None) -> EvalPipelineResult:
        """Evaluate all eligible same-day runs."""
        as_of = as_of or datetime.now(timezone.utc)
        trade_date = self._trade_date(as_of)
        eligible = repository.get_same_day_eval_candidates(self.session, trade_date=trade_date)

        if not eligible:
            logger.info("eval_pipeline_no_eligible_runs", trade_date=trade_date.isoformat())
            return EvalPipelineResult()

        logger.info(
            "eval_pipeline_started",
            run_count=len(eligible),
            trade_date=trade_date.isoformat(),
        )
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
        """Force-evaluate a single run by run_id."""
        run = self.session.query(ResearchRun).filter(ResearchRun.run_id == run_id).first()
        if run is None:
            return EvalTickerResult(run_id=run_id, ticker="unknown", success=False, error="run_not_found")
        output = self.session.query(ResearchOutput).filter(ResearchOutput.run_id == run_id).first()
        if output is None:
            return EvalTickerResult(run_id=run_id, ticker=run.ticker, success=False, error="no_output_row")
        return self._eval_run(run, output)

    def _trade_date(self, as_of: datetime) -> date:
        normalized = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
        return normalized.astimezone(MARKET_TIMEZONE).date()

    def _is_pre_open_run(self, as_of: datetime) -> bool:
        normalized = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
        return normalized.astimezone(MARKET_TIMEZONE).time() < REGULAR_MARKET_OPEN

    def _compute_return_from_prices(
        self,
        entry_price: Optional[float],
        exit_price: Optional[float],
    ) -> Optional[float]:
        if entry_price in (None, 0) or exit_price is None:
            return None
        return (exit_price / entry_price) - 1

    def _extract_run_snapshot_price(self, run: ResearchRun) -> Optional[float]:
        input_json = run.input_json or {}
        if not isinstance(input_json, dict):
            return None
        price_snapshot = input_json.get("price_snapshot") or {}
        if not isinstance(price_snapshot, dict):
            return None
        price = price_snapshot.get("last_price")
        if price is None:
            return None
        try:
            return float(price)
        except (TypeError, ValueError):
            return None

    def _open_to_close_params(self) -> dict[str, Any]:
        return {
            "price_window": "open_to_close",
            "entry_price_source": "session_open",
            "exit_price_source": "session_close",
            "benchmark_entry_price_source": "session_open",
            "benchmark_exit_price_source": "session_close",
        }

    def _run_time_to_close_params(self) -> dict[str, Any]:
        return {
            "price_window": "run_time_price_to_close",
            "entry_price_source": "research_input_last_price",
            "exit_price_source": "session_close",
            "benchmark_entry_price_source": "market_price_at_or_before_run_time",
            "benchmark_exit_price_source": "session_close",
        }

    def _eval_run(self, run: ResearchRun, output: ResearchOutput) -> EvalTickerResult:
        try:
            if output.time_horizon != ResearchTimeHorizon.ONE_DAY.value:
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

            trade_date = self._trade_date(run.as_of)
            if self._is_pre_open_run(run.as_of):
                realized_return = fetch_open_to_close_return(
                    run.ticker,
                    trade_date,
                    provider=self.provider,
                )
                benchmark_return = fetch_open_to_close_return(
                    self.benchmark_symbol,
                    trade_date,
                    provider=self.provider,
                )
                evaluation_params = self._open_to_close_params()
            else:
                entry_price = self._extract_run_snapshot_price(run)
                exit_price = fetch_close_price_on_date(
                    run.ticker,
                    trade_date,
                    provider=self.provider,
                )
                benchmark_entry = fetch_price_at_or_before(
                    self.benchmark_symbol,
                    run.as_of,
                    provider=self.provider,
                )
                benchmark_exit = fetch_close_price_on_date(
                    self.benchmark_symbol,
                    trade_date,
                    provider=self.provider,
                )
                realized_return = self._compute_return_from_prices(entry_price, exit_price)
                benchmark_return = self._compute_return_from_prices(benchmark_entry, benchmark_exit)
                evaluation_params = self._run_time_to_close_params()

            outcome_label = apply_rule_v1(
                decision=output.decision,
                realized_return=realized_return,
                benchmark_return=benchmark_return,
                neutral_threshold=self.neutral_threshold,
            )

            repository.upsert_eval_result(
                self.session,
                run_id=run.run_id,
                horizon_days=1,
                realized_return=realized_return,
                benchmark_return=benchmark_return,
                benchmark_symbol=self.benchmark_symbol,
                evaluation_method=EvaluationMethod.RULE_V1.value,
                evaluation_params=evaluation_params,
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
