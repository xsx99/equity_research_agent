from src.scheduler.jobs.market_daily_bars_job import MarketDailyBarsJob
from src.scheduler.service import build_scheduler_jobs


def test_market_daily_bars_job_runs_once_after_close_on_weekdays():
    config = MarketDailyBarsJob().config

    assert config.job_id == "market_daily_bars"
    assert config.trigger == "cron"
    assert config.trigger_kwargs == {
        "hour": 16,
        "minute": 5,
        "day_of_week": "mon-fri",
    }


def test_default_scheduler_registers_market_daily_bars_job():
    assert any(isinstance(job, MarketDailyBarsJob) for job in build_scheduler_jobs())
