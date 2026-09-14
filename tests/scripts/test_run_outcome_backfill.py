from datetime import date

from scripts import run_outcome_backfill


class _Session:
    def __init__(self):
        self.commit_count = 0
        self.rollback_count = 0

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


class _Pipeline:
    def __init__(self, completed_dates=None, fail_date=None):
        self.completed_dates = set(completed_dates or ())
        self.fail_date = fail_date
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        source_date = kwargs["source_decision_date"]
        if source_date == self.fail_date:
            raise RuntimeError("fixture failure")
        due = 0 if source_date in self.completed_dates else 1
        if kwargs["persist"]:
            self.completed_dates.add(source_date)
        return type(
            "Result",
            (),
            {
                "due_checkpoint_count": due,
                "created_interim_count": 0,
                "created_final_count": due,
                "pending_count": 0,
                "unsupported_horizon_count": 0,
                "provider_error_count": 0,
            },
        )()


def test_backfill_is_dry_run_by_default_and_never_commits_or_persists():
    session = _Session()
    pipeline = _Pipeline()

    report = run_outcome_backfill.run_backfill(
        session=session,
        pipeline=pipeline,
        start_date=date(2026, 7, 6),
        end_date=date(2026, 7, 7),
    )

    assert report["status"] == "dry_run"
    assert session.commit_count == 0
    assert session.rollback_count == 2
    assert pipeline.completed_dates == set()
    assert all(call["persist"] is False for call in pipeline.calls)


def test_backfill_apply_is_per_date_idempotent_and_resume_continues_after_completed_dates():
    session = _Session()
    pipeline = _Pipeline(fail_date=date(2026, 7, 7))

    first = run_outcome_backfill.run_backfill(
        session=session,
        pipeline=pipeline,
        start_date=date(2026, 7, 6),
        end_date=date(2026, 7, 8),
        apply=True,
    )

    assert first["completed_dates"] == ["2026-07-06", "2026-07-08"]
    assert first["failed_dates"] == ["2026-07-07"]
    assert session.commit_count == 2
    assert session.rollback_count == 1

    pipeline.fail_date = None
    resumed = run_outcome_backfill.run_backfill(
        session=session,
        pipeline=pipeline,
        start_date=date(2026, 7, 6),
        end_date=date(2026, 7, 8),
        apply=True,
        resume=True,
    )

    assert resumed["already_evaluated_dates"] == ["2026-07-06", "2026-07-08"]
    assert resumed["completed_dates"] == ["2026-07-07"]
    assert pipeline.completed_dates == {
        date(2026, 7, 6),
        date(2026, 7, 7),
        date(2026, 7, 8),
    }


def test_main_requires_explicit_date_range_and_apply_opt_in():
    parser = run_outcome_backfill.build_parser()

    try:
        parser.parse_args([])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("date range should be required")

    args = parser.parse_args(["--start-date", "2026-07-06", "--end-date", "2026-07-07"])
    assert args.apply is False
