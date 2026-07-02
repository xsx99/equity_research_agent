"""Smoke tests for scheduler job configuration.

Verifies that job instances have the expected job_id, trigger, trigger_kwargs,
and run_on_startup values without touching the database or any external API.
"""
from datetime import date, datetime, timezone

import pytest
from zoneinfo import ZoneInfoNotFoundError

from src.core.timezones import resolve_timezone
from src.scheduler.jobs.eval_job import EvalJob
from src.scheduler.jobs.intraday_signal_refresh_job import IntradaySignalRefreshJob
from src.scheduler.jobs.manual_ticker_review_job import ManualTickerReviewJob
from src.scheduler.jobs.research_job import ResearchJob
from src.scheduler.jobs.sec_edgar_job import SECEdgarJob
from src.scheduler.jobs.strategy_evolution_job import StrategyEvolutionJob
from src.scheduler.jobs.trading_preopen_job import TradingPreopenJob
from src.scheduler.jobs.trading_reflection_job import TradingReflectionJob
from src.scheduler.service import build_scheduler_jobs


@pytest.mark.parametrize(
    ("module_path", "job_cls", "phase"),
    [
        ("src.scheduler.jobs.trading_preopen_job", TradingPreopenJob, "preopen"),
        ("src.scheduler.jobs.manual_ticker_review_job", ManualTickerReviewJob, "manual_review"),
        ("src.scheduler.jobs.intraday_signal_refresh_job", IntradaySignalRefreshJob, "intraday_refresh"),
        ("src.scheduler.jobs.trading_reflection_job", TradingReflectionJob, "reflection"),
        ("src.scheduler.jobs.strategy_evolution_job", StrategyEvolutionJob, "strategy_evolution"),
    ],
)
def test_trading_scheduler_jobs_call_run_job_phase(monkeypatch, module_path, job_cls, phase):
    called: list[str] = []
    events: list[tuple[str, str, dict[str, object]]] = []

    monkeypatch.setattr(
        f"{module_path}.run_job_phase",
        lambda requested_phase, **kwargs: called.append(requested_phase)
        or {"status": "passed", "phase": requested_phase},
    )
    monkeypatch.setattr(
        f"{module_path}.logger",
        type(
            "LoggerStub",
            (),
            {
                "info": staticmethod(lambda event, **kwargs: events.append(("info", event, kwargs))),
                "warning": staticmethod(lambda event, **kwargs: events.append(("warning", event, kwargs))),
                "error": staticmethod(lambda event, **kwargs: events.append(("error", event, kwargs))),
            },
        )(),
    )

    job_cls().run()

    assert called == [phase]
    assert any(level == "info" and event.endswith("_job_started") for level, event, _kwargs in events)
    assert any(
        level == "info" and event.endswith("_job_completed") and kwargs.get("status") == "passed"
        for level, event, kwargs in events
    )


@pytest.mark.parametrize(
    ("module_path", "job_cls", "phase"),
    [
        ("src.scheduler.jobs.trading_preopen_job", TradingPreopenJob, "preopen"),
        ("src.scheduler.jobs.manual_ticker_review_job", ManualTickerReviewJob, "manual_review"),
        ("src.scheduler.jobs.intraday_signal_refresh_job", IntradaySignalRefreshJob, "intraday_refresh"),
    ],
)
def test_live_trading_jobs_forward_execution_policy(monkeypatch, module_path, job_cls, phase):
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(f"{module_path}.app_config.TRADING_EXECUTE_PAPER_ORDERS", True)
    monkeypatch.setattr(f"{module_path}.app_config.TRADING_EXECUTE_PAPER_OPTION_ORDERS", False)
    monkeypatch.setattr(
        f"{module_path}.run_job_phase",
        lambda requested_phase, **kwargs: calls.append((requested_phase, kwargs))
        or {"status": "passed", "phase": requested_phase},
    )
    monkeypatch.setattr(
        f"{module_path}.logger",
        type(
            "LoggerStub",
            (),
            {
                "info": staticmethod(lambda *args, **kwargs: None),
                "warning": staticmethod(lambda *args, **kwargs: None),
                "error": staticmethod(lambda *args, **kwargs: None),
            },
        )(),
    )

    job_cls().run()

    assert calls == [
        (
            phase,
            {
                "execute_paper_orders": True,
                "execute_paper_option_orders": False,
            },
        )
    ]


def test_post_close_trading_job_logs_skipped_status_with_reasons(monkeypatch):
    events: list[tuple[str, str, dict[str, object]]] = []

    monkeypatch.setattr(
        "src.scheduler.jobs.trading_reflection_job.run_job_phase",
        lambda _phase: {
            "status": "skipped",
            "phase": "reflection",
            "summary": {"reasons": ["portfolio_outcome_missing"]},
        },
    )
    monkeypatch.setattr(
        "src.scheduler.jobs.trading_reflection_job.logger",
        type(
            "LoggerStub",
            (),
            {
                "info": staticmethod(lambda event, **kwargs: events.append(("info", event, kwargs))),
                "warning": staticmethod(lambda event, **kwargs: events.append(("warning", event, kwargs))),
                "error": staticmethod(lambda event, **kwargs: events.append(("error", event, kwargs))),
            },
        )(),
    )

    TradingReflectionJob().run()

    assert ("warning", "trading_reflection_job_skipped", {"status": "skipped", "reasons": ["portfolio_outcome_missing"]}) in events


class TestResearchJob:
    def test_job_id(self):
        job = ResearchJob()
        assert job.config.job_id == "research_pipeline"

    def test_trigger_is_pre_open_only(self):
        job = ResearchJob()
        cfg = job.config
        assert cfg.trigger == "cron"
        assert cfg.trigger_kwargs["hour"] == 9
        assert cfg.trigger_kwargs["minute"] == 20
        assert cfg.trigger_kwargs["day_of_week"] == "mon-fri"

    def test_run_on_startup_default_false(self):
        assert ResearchJob().run_on_startup is False


class TestEvalJob:
    def test_job_id(self):
        assert EvalJob().config.job_id == "eval_pipeline"

    def test_trigger(self):
        cfg = EvalJob().config
        assert cfg.trigger == "cron"
        assert cfg.trigger_kwargs["hour"] == 16
        assert cfg.trigger_kwargs["minute"] == 10

    def test_run_on_startup_default_false(self):
        assert EvalJob().run_on_startup is False


class TestAllJobIdsDistinct:
    def test_no_duplicate_job_ids(self):
        jobs = [
            SECEdgarJob(),
            ResearchJob(),
            EvalJob(),
            TradingPreopenJob(),
            ManualTickerReviewJob(),
            IntradaySignalRefreshJob(),
            TradingReflectionJob(),
            StrategyEvolutionJob(),
        ]
        ids = [j.config.job_id for j in jobs]
        assert len(ids) == len(set(ids)), f"Duplicate job IDs found: {ids}"


class TestSECEdgarJob:
    def test_target_date_defaults_to_previous_scheduler_day(self):
        job = SECEdgarJob()

        target_date = job._get_target_date(
            datetime(2026, 7, 2, 2, 0, tzinfo=timezone.utc)
        )

        assert target_date == date(2026, 7, 1)


class TestTradingPreopenJob:
    def test_trigger_is_pre_open_weekday(self):
        cfg = TradingPreopenJob().config

        assert cfg.job_id == "trading_preopen"
        assert cfg.trigger == "cron"
        assert cfg.trigger_kwargs == {
            "hour": 8,
            "minute": 45,
            "day_of_week": "mon-fri",
        }


class TestManualTickerReviewJob:
    def test_trigger_is_pre_open_weekday(self):
        cfg = ManualTickerReviewJob().config

        assert cfg.job_id == "manual_ticker_review"
        assert cfg.trigger == "cron"
        assert cfg.trigger_kwargs == {
            "hour": 8,
            "minute": 50,
            "day_of_week": "mon-fri",
        }


class TestIntradaySignalRefreshJob:
    def test_trigger_is_hourly_during_cash_session(self):
        cfg = IntradaySignalRefreshJob().config

        assert cfg.job_id == "intraday_signal_refresh"
        assert cfg.trigger == "cron"
        assert cfg.trigger_kwargs == {
            "hour": "10-15",
            "minute": 0,
            "day_of_week": "mon-fri",
        }


class TestTradingReflectionJob:
    def test_trigger_is_post_close_weekday(self):
        cfg = TradingReflectionJob().config

        assert cfg.job_id == "trading_reflection"
        assert cfg.trigger == "cron"
        assert cfg.trigger_kwargs == {
            "hour": 16,
            "minute": 20,
            "day_of_week": "mon-fri",
        }


class TestStrategyEvolutionJob:
    def test_trigger_is_after_reflection_weekday(self):
        cfg = StrategyEvolutionJob().config

        assert cfg.job_id == "strategy_evolution"
        assert cfg.trigger == "cron"
        assert cfg.trigger_kwargs == {
            "hour": 16,
            "minute": 50,
            "day_of_week": "mon-fri",
        }


class TestBuildSchedulerJobs:
    def test_includes_legacy_and_trading_jobs(self):
        jobs = build_scheduler_jobs()

        assert [job.config.job_id for job in jobs] == [
            "sec_edgar_form4",
            "research_pipeline",
            "eval_pipeline",
            "trading_preopen",
            "manual_ticker_review",
            "intraday_signal_refresh",
            "trading_reflection",
            "strategy_evolution",
        ]


class TestSchedulerTimezoneResolution:
    def test_resolves_us_eastern_alias_when_platform_lacks_legacy_name(self, monkeypatch):
        def _fake_zoneinfo(name: str):
            if name == "US/Eastern":
                raise ZoneInfoNotFoundError(name)
            if name == "America/New_York":
                return object()
            if name == "UTC":
                raise AssertionError("should not fall back to UTC when alias exists")
            raise AssertionError(f"unexpected timezone lookup: {name}")

        monkeypatch.setattr("src.core.timezones.ZoneInfo", _fake_zoneinfo)

        resolved = resolve_timezone("US/Eastern", fallback="UTC")

        assert resolved is not None
