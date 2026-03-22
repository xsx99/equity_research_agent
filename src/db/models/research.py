"""Research run and output ORM models."""
import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .base import Base, ChoiceEnum


class RunStatus(ChoiceEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ResearchDecision(ChoiceEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    ABSTAIN = "abstain"


class ResearchTimeHorizon(ChoiceEnum):
    ONE_DAY = "1d"
    THREE_DAYS = "3d"
    FIVE_DAYS = "5d"

    @classmethod
    def days_mapping(cls) -> dict[str, int]:
        return {
            cls.ONE_DAY.value: 1,
            cls.THREE_DAYS.value: 3,
            cls.FIVE_DAYS.value: 5,
        }


class ResearchActionability(ChoiceEnum):
    ABSTAIN = "abstain"
    WATCH = "watch"
    ACTIONABLE = "actionable"


class ResearchRun(Base):
    """Research run metadata and input snapshot."""

    __tablename__ = "research_runs"

    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    as_of = Column(DateTime(timezone=True), nullable=False, index=True)
    prompt_version = Column(String(64), nullable=False)
    model_name = Column(String(128), nullable=False)
    input_json = Column(JSONB, nullable=False)
    status = Column(
        String(16),
        nullable=False,
        default=RunStatus.QUEUED.value,
        server_default=RunStatus.QUEUED.value,
        index=True,
    )
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    output = relationship("ResearchOutput", back_populates="run", uselist=False)
    eval_result = relationship("EvalResult", back_populates="run", uselist=False)

    __table_args__ = (
        CheckConstraint(
            f"status IN {RunStatus.check_in_sql()}",
            name="ck_research_runs_status",
        ),
        Index("ix_research_runs_ticker_as_of", "ticker", "as_of"),
    )

    def __repr__(self):
        return f"<ResearchRun {self.run_id} {self.ticker} status={self.status}>"


class ResearchOutput(Base):
    """Structured model output for a research run."""

    __tablename__ = "research_outputs"

    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    output_json = Column(JSONB, nullable=False)
    decision = Column(String(16), nullable=False, index=True)
    confidence = Column(Numeric, nullable=False)
    time_horizon = Column(String(8), nullable=False, index=True)
    actionability = Column(String(16), nullable=False, index=True)
    thesis_summary = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run = relationship("ResearchRun", back_populates="output")

    __table_args__ = (
        CheckConstraint(
            f"decision IN {ResearchDecision.check_in_sql()}",
            name="ck_research_outputs_decision",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_research_outputs_confidence"),
        CheckConstraint(
            f"time_horizon IN {ResearchTimeHorizon.check_in_sql()}",
            name="ck_research_outputs_time_horizon",
        ),
        CheckConstraint(
            f"actionability IN {ResearchActionability.check_in_sql()}",
            name="ck_research_outputs_actionability",
        ),
    )

    def __repr__(self):
        return f"<ResearchOutput {self.run_id} {self.decision} conf={self.confidence}>"
