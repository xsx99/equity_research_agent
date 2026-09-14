"""Live persisted-candidate outcome evaluation runtime."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from src.core import config as app_config
from src.trading.phases._shell.support import build_runtime_report
from src.trading.trade_day import trade_date_for


@dataclass(frozen=True)
class LiveOutcomeDependencies:
    outcome_pipeline: Any
    source_date_loader: Callable[[object], tuple[object, ...]] | None = None
    commit_source_date: Callable[[object], None] | None = None
    rollback_source_date: Callable[[object], None] | None = None


class LiveOutcomeRuntime:
    """Run all candidate checkpoints due as of the current trade session."""

    def __init__(
        self,
        *,
        dependencies: LiveOutcomeDependencies,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.dependencies = dependencies
        self.now = now or (lambda: datetime.now(timezone.utc))

    def run(self) -> dict[str, Any]:
        decision_time = self.now()
        evaluation_session = trade_date_for(decision_time, app_config.SCHEDULER_TIMEZONE)
        failed_source_dates: list[str] = []
        if self.dependencies.source_date_loader is None:
            try:
                results = (
                    self.dependencies.outcome_pipeline.run(
                        evaluation_as_of_session=evaluation_session
                    ),
                )
            except Exception as exc:
                return _failed_report(decision_time, exc)
        else:
            results_list = []
            source_dates = tuple(
                self.dependencies.source_date_loader(evaluation_session)
            )
            for source_date in source_dates:
                try:
                    results_list.append(
                        self.dependencies.outcome_pipeline.run(
                            evaluation_as_of_session=evaluation_session,
                            source_decision_date=source_date,
                        )
                    )
                    if self.dependencies.commit_source_date is not None:
                        self.dependencies.commit_source_date(source_date)
                except Exception:
                    if self.dependencies.rollback_source_date is not None:
                        self.dependencies.rollback_source_date(source_date)
                    failed_source_dates.append(str(source_date))
            results = tuple(results_list)

        summary = _results_summary(results)
        summary["failed_source_dates"] = failed_source_dates
        if summary["due_checkpoint_count"] == 0:
            if failed_source_dates:
                return build_runtime_report(
                    phase="outcome_evaluation",
                    as_of=decision_time,
                    status="failed",
                    summary={
                        **summary,
                        "reasons": ["all_source_dates_failed"],
                    },
                )
            summary.update({"result_status": "skipped", "reasons": ["no_due_checkpoints"]})
            return build_runtime_report(
                phase="outcome_evaluation",
                as_of=decision_time,
                status="skipped",
                summary=summary,
            )
        degraded = (
            summary["pending_count"] > 0
            or summary["provider_error_count"] > 0
            or bool(failed_source_dates)
        )
        summary["result_status"] = "degraded" if degraded else "passed"
        return build_runtime_report(
            phase="outcome_evaluation",
            as_of=decision_time,
            summary=summary,
        )


def build_live_outcome_dependencies(session: Any | None = None) -> LiveOutcomeDependencies:
    """Build the production repository/provider dependency graph."""
    if session is None:
        raise RuntimeError("db_session_required_for_live_outcome_dependencies")
    from src.providers.market_data import AlpacaMarketDataProvider
    from src.trading.outcomes.pipeline import OutcomeEvaluationPipeline
    from src.trading.outcomes.prices import OutcomePriceLoader
    from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository

    repository = SqlAlchemyTradingRepository(session)
    return LiveOutcomeDependencies(
        outcome_pipeline=OutcomeEvaluationPipeline(
            repository=repository,
            price_loader=OutcomePriceLoader(provider=AlpacaMarketDataProvider()),
        ),
        source_date_loader=repository.load_due_candidate_outcome_source_dates,
        commit_source_date=lambda _source_date: session.commit(),
        rollback_source_date=lambda _source_date: session.rollback(),
    )


def run_live_outcomes_once(
    *,
    dependencies: LiveOutcomeDependencies | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Execute one live outcome maturation run with injectable dependencies."""
    if dependencies is not None:
        return LiveOutcomeRuntime(dependencies=dependencies, now=now).run()
    from src.db.connection import get_session

    with get_session() as session:
        return LiveOutcomeRuntime(
            dependencies=build_live_outcome_dependencies(session),
            now=now,
        ).run()


def _result_summary(result: Any) -> dict[str, Any]:
    names = (
        "created_interim_count",
        "created_final_count",
        "pending_count",
        "unsupported_horizon_count",
        "provider_error_count",
        "due_candidate_count",
        "due_checkpoint_count",
        "already_evaluated_count",
    )
    summary = {name: int(getattr(result, name, 0) or 0) for name in names}
    summary.update(
        {
            "reason_codes": list(getattr(result, "reason_codes", ()) or ()),
            "missing_symbols": list(getattr(result, "missing_symbols", ()) or ()),
            "provider_errors": dict(getattr(result, "provider_errors", {}) or {}),
            "comparator_coverage": dict(
                getattr(result, "comparator_coverage", {}) or {}
            ),
        }
    )
    return summary


def _results_summary(results: tuple[Any, ...]) -> dict[str, Any]:
    if not results:
        return _result_summary(None)
    summaries = tuple(_result_summary(result) for result in results)
    numeric_names = (
        "created_interim_count",
        "created_final_count",
        "pending_count",
        "unsupported_horizon_count",
        "provider_error_count",
        "due_candidate_count",
        "due_checkpoint_count",
        "already_evaluated_count",
    )
    return {
        **{name: sum(item[name] for item in summaries) for name in numeric_names},
        "reason_codes": sorted(
            {code for item in summaries for code in item["reason_codes"]}
        ),
        "missing_symbols": sorted(
            {symbol for item in summaries for symbol in item["missing_symbols"]}
        ),
        "provider_errors": {
            key: value
            for item in summaries
            for key, value in item["provider_errors"].items()
        },
        "comparator_coverage": {
            key: sorted(
                {
                    value
                    for item in summaries
                    for value in item["comparator_coverage"].get(key, ())
                }
            )
            for key in ("available", "missing")
        },
    }


def _failed_report(decision_time: datetime, exc: Exception) -> dict[str, Any]:
    return build_runtime_report(
        phase="outcome_evaluation",
        as_of=decision_time,
        status="failed",
        summary={
            "reasons": ["outcome_evaluation_failed"],
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:256],
        },
    )


__all__ = [
    "LiveOutcomeDependencies",
    "LiveOutcomeRuntime",
    "build_live_outcome_dependencies",
    "run_live_outcomes_once",
]
