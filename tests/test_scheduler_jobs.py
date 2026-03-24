"""Smoke tests for scheduler job configuration.

Verifies that job instances have the expected job_id, trigger, trigger_kwargs,
and run_on_startup values without touching the database or any external API.
"""
import pytest

from src.scheduler.jobs.eval_job import EvalJob
from src.scheduler.jobs.research_job import ResearchJob
from src.scheduler.jobs.sec_edgar_job import SECEdgarJob


class TestResearchJob:
    def test_open_slot_job_id(self):
        job = ResearchJob("open")
        assert job.config.job_id == "research_pipeline_open"

    def test_close_slot_job_id(self):
        job = ResearchJob("close")
        assert job.config.job_id == "research_pipeline_close"

    def test_open_slot_trigger(self):
        job = ResearchJob("open")
        cfg = job.config
        assert cfg.trigger == "cron"
        assert cfg.trigger_kwargs["hour"] == 9
        assert cfg.trigger_kwargs["minute"] == 20
        assert cfg.trigger_kwargs["day_of_week"] == "mon-fri"

    def test_close_slot_trigger(self):
        job = ResearchJob("close")
        cfg = job.config
        assert cfg.trigger == "cron"
        assert cfg.trigger_kwargs["hour"] == 15
        assert cfg.trigger_kwargs["minute"] == 50
        assert cfg.trigger_kwargs["day_of_week"] == "mon-fri"

    def test_invalid_slot_raises(self):
        with pytest.raises(ValueError):
            ResearchJob("noon")

    def test_run_on_startup_default_false(self):
        assert ResearchJob("open").run_on_startup is False
        assert ResearchJob("close").run_on_startup is False

    def test_open_and_close_have_distinct_job_ids(self):
        open_id = ResearchJob("open").config.job_id
        close_id = ResearchJob("close").config.job_id
        assert open_id != close_id


class TestEvalJob:
    def test_job_id(self):
        assert EvalJob().config.job_id == "eval_pipeline"

    def test_trigger(self):
        cfg = EvalJob().config
        assert cfg.trigger == "cron"
        assert cfg.trigger_kwargs["hour"] == 18
        assert cfg.trigger_kwargs["minute"] == 0

    def test_run_on_startup_default_false(self):
        assert EvalJob().run_on_startup is False


class TestAllJobIdsDistinct:
    def test_no_duplicate_job_ids(self):
        jobs = [
            SECEdgarJob(),
            ResearchJob("open"),
            ResearchJob("close"),
            EvalJob(),
        ]
        ids = [j.config.job_id for j in jobs]
        assert len(ids) == len(set(ids)), f"Duplicate job IDs found: {ids}"
