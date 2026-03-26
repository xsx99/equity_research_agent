"""Smoke tests for scheduler job configuration.

Verifies that job instances have the expected job_id, trigger, trigger_kwargs,
and run_on_startup values without touching the database or any external API.
"""
import pytest
from zoneinfo import ZoneInfoNotFoundError

from src.core.timezones import resolve_timezone
from src.scheduler.jobs.eval_job import EvalJob
from src.scheduler.jobs.research_job import ResearchJob
from src.scheduler.jobs.sec_edgar_job import SECEdgarJob


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
        ]
        ids = [j.config.job_id for j in jobs]
        assert len(ids) == len(set(ids)), f"Duplicate job IDs found: {ids}"


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
