"""Scheduled job for the research pipeline.

Two instances are registered per day (weekdays only):
- ``ResearchJob("open")``  — 9:20 ET (10 min before market open)
- ``ResearchJob("close")`` — 15:50 ET (10 min before market close)
"""
from __future__ import annotations

from src.agents.research import ResearchAgent
from src.core.config import (
    RESEARCH_RUN_ON_STARTUP,
    RESEARCH_SCHEDULE_HOUR_CLOSE,
    RESEARCH_SCHEDULE_HOUR_OPEN,
    RESEARCH_SCHEDULE_MINUTE_CLOSE,
    RESEARCH_SCHEDULE_MINUTE_OPEN,
)
from src.core.logging import get_logger
from src.db.connection import get_session
from src.prompts.registry import PromptRegistry
from src.research.pipeline import ResearchPipeline
from src.scheduler.base import BaseJob, JobConfig
from src.tools import build_research_tool_registry

logger = get_logger(__name__)

_SLOTS = {
    "open": (RESEARCH_SCHEDULE_HOUR_OPEN, RESEARCH_SCHEDULE_MINUTE_OPEN),
    "close": (RESEARCH_SCHEDULE_HOUR_CLOSE, RESEARCH_SCHEDULE_MINUTE_CLOSE),
}


class ResearchJob(BaseJob):
    """
    Scheduled job that runs :class:`~src.research.pipeline.ResearchPipeline`
    for all active watchlist tickers.

    Parameters
    ----------
    slot:
        ``"open"`` (pre-market-open run) or ``"close"`` (pre-market-close run).
        Determines the cron schedule and job_id.
    """

    def __init__(self, slot: str = "open") -> None:
        if slot not in _SLOTS:
            raise ValueError(f"slot must be 'open' or 'close', got {slot!r}")
        self._slot = slot
        self.run_on_startup: bool = RESEARCH_RUN_ON_STARTUP

    @property
    def config(self) -> JobConfig:
        hour, minute = _SLOTS[self._slot]
        return JobConfig(
            job_id=f"research_pipeline_{self._slot}",
            trigger="cron",
            trigger_kwargs={
                "hour": hour,
                "minute": minute,
                "day_of_week": "mon-fri",
            },
        )

    def run(self) -> None:
        """Execute one research pipeline batch run."""
        logger.info("research_job_started", slot=self._slot)
        try:
            with get_session() as session:
                agent = ResearchAgent(
                    tool_registry=build_research_tool_registry(),
                    prompt_registry=PromptRegistry.get_default(),
                )
                pipeline = ResearchPipeline(session=session, agent=agent)
                result = pipeline.run_all()

            logger.info(
                "research_job_completed",
                slot=self._slot,
                succeeded=result.succeeded,
                failed=result.failed,
            )
        except Exception as e:
            logger.error("research_job_failed", slot=self._slot, error=str(e), exc_info=True)
