from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.trading.runtime.outcomes import LiveOutcomeDependencies, LiveOutcomeRuntime


class _Pipeline:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def test_live_outcome_runtime_returns_passed_and_skipped_reports_from_injected_pipeline():
    now = datetime(2026, 7, 7, 21, tzinfo=timezone.utc)
    passed_pipeline = _Pipeline(_result(created_final_count=2, due_checkpoint_count=2))
    skipped_pipeline = _Pipeline(_result(due_checkpoint_count=0))

    passed = LiveOutcomeRuntime(
        dependencies=LiveOutcomeDependencies(outcome_pipeline=passed_pipeline),
        now=lambda: now,
    ).run()
    skipped = LiveOutcomeRuntime(
        dependencies=LiveOutcomeDependencies(outcome_pipeline=skipped_pipeline),
        now=lambda: now,
    ).run()

    assert passed["status"] == "passed"
    assert passed["summary"]["result_status"] == "passed"
    assert passed["summary"]["created_final_count"] == 2
    assert passed_pipeline.calls == [{"evaluation_as_of_session": date(2026, 7, 7)}]
    assert skipped["status"] == "skipped"
    assert skipped["summary"]["reasons"] == ["no_due_checkpoints"]


def test_live_outcome_runtime_normalizes_degraded_and_failed_reports():
    now = datetime(2026, 7, 7, 21, tzinfo=timezone.utc)
    degraded_pipeline = _Pipeline(
        _result(
            due_checkpoint_count=2,
            pending_count=1,
            provider_error_count=1,
            reason_codes=("missing_required_price", "provider_error"),
            missing_symbols=("IWM",),
            provider_errors={"batch": "TimeoutError"},
            comparator_coverage={"available": ["QQQ"], "missing": ["IWM"]},
        )
    )
    failed_pipeline = _Pipeline(error=RuntimeError("provider unavailable"))

    degraded = LiveOutcomeRuntime(
        dependencies=LiveOutcomeDependencies(outcome_pipeline=degraded_pipeline),
        now=lambda: now,
    ).run()
    failed = LiveOutcomeRuntime(
        dependencies=LiveOutcomeDependencies(outcome_pipeline=failed_pipeline),
        now=lambda: now,
    ).run()

    assert degraded["status"] == "passed"
    assert degraded["summary"]["result_status"] == "degraded"
    assert degraded["summary"]["reason_codes"] == [
        "missing_required_price", "provider_error"
    ]
    assert degraded["summary"]["missing_symbols"] == ["IWM"]
    assert degraded["summary"]["provider_errors"] == {"batch": "TimeoutError"}
    assert degraded["summary"]["comparator_coverage"]["missing"] == ["IWM"]
    assert failed["status"] == "failed"
    assert failed["summary"] == {
        "reasons": ["outcome_evaluation_failed"],
        "error_type": "RuntimeError",
        "error_message": "provider unavailable",
    }


def test_live_outcome_runtime_isolates_each_source_date_transaction():
    now = datetime(2026, 7, 7, 21, tzinfo=timezone.utc)
    first = date(2026, 7, 2)
    second = date(2026, 7, 3)
    transactions = []

    class _PerDatePipeline:
        def run(self, **kwargs):
            source_date = kwargs["source_decision_date"]
            if source_date == second:
                raise RuntimeError("bad source date")
            return _result(created_final_count=1, due_checkpoint_count=1)

    runtime = LiveOutcomeRuntime(
        dependencies=LiveOutcomeDependencies(
            outcome_pipeline=_PerDatePipeline(),
            source_date_loader=lambda evaluation_session: (first, second),
            commit_source_date=lambda source_date: transactions.append(("commit", source_date)),
            rollback_source_date=lambda source_date: transactions.append(("rollback", source_date)),
        ),
        now=lambda: now,
    )

    report = runtime.run()

    assert transactions == [("commit", first), ("rollback", second)]
    assert report["status"] == "passed"
    assert report["summary"]["result_status"] == "degraded"
    assert report["summary"]["created_final_count"] == 1
    assert report["summary"]["failed_source_dates"] == ["2026-07-03"]


def _result(**overrides):
    values = {
        "created_interim_count": 0,
        "created_final_count": 0,
        "pending_count": 0,
        "unsupported_horizon_count": 0,
        "provider_error_count": 0,
        "due_candidate_count": 0,
        "due_checkpoint_count": 0,
        "already_evaluated_count": 0,
        "reason_codes": (),
        "missing_symbols": (),
        "provider_errors": {},
        "comparator_coverage": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)
