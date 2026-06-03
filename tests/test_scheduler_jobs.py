"""Smoke tests for scheduler job configuration.

Verifies that job instances have the expected job_id, trigger, trigger_kwargs,
and run_on_startup values without touching the database or any external API.
"""
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
