"""Scheduled job for the pre-open research pipeline."""
from __future__ import annotations

from src.agents.research import ResearchAgent
from src.core.config import (
    RESEARCH_RUN_ON_STARTUP,
    RESEARCH_SCHEDULE_HOUR,
    RESEARCH_SCHEDULE_MINUTE,
)
from src.core.logging import get_logger
from src.db.connection import get_session
from src.prompts.registry import PromptRegistry
from src.research.workflows.batch_research import ResearchPipeline
from src.scheduler.base import BaseJob, JobConfig
from src.tools import build_research_tool_registry

logger = get_logger(__name__)


class ResearchJob(BaseJob):
    """Scheduled job that runs one pre-open research batch for active tickers."""

    def __init__(self) -> None:
        self.run_on_startup: bool = RESEARCH_RUN_ON_STARTUP

    @property
    def config(self) -> JobConfig:
        return JobConfig(
            job_id="research_pipeline",
            trigger="cron",
            trigger_kwargs={
                "hour": RESEARCH_SCHEDULE_HOUR,
                "minute": RESEARCH_SCHEDULE_MINUTE,
                "day_of_week": "mon-fri",
            },
        )

    def run(self) -> None:
        """Execute one research pipeline batch run."""
        logger.info("research_job_started")
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
                succeeded=result.succeeded,
                failed=result.failed,
            )
        except Exception as e:
            logger.error("research_job_failed", error=str(e), exc_info=True)
