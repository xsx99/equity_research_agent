"""SQLAlchemy database models."""
import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    CheckConstraint,
    Column,
    Integer,
    String,
    Boolean,
    Date,
    Numeric,
    BigInteger,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class ChoiceEnum(str, enum.Enum):
    """Shared enum helper with common convenience methods."""

    @classmethod
    def choices(cls) -> tuple[str, ...]:
        return tuple(item.value for item in cls)

    @classmethod
    def check_in_sql(cls) -> str:
        values = ", ".join(f"'{value}'" for value in cls.choices())
        return f"({values})"


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


class EvalOutcomeLabel(ChoiceEnum):
    CORRECT = "correct"
    PARTIALLY_CORRECT = "partially_correct"
    WRONG_DIRECTION = "wrong_direction"
    UNINFORMATIVE = "uninformative"


class EvaluationMethod(ChoiceEnum):
    RULE_V1 = "rule_v1"


class InsiderTrade(Base):
    """Insider trading transaction record."""

    __tablename__ = "insider_trades"

    id = Column(Integer, primary_key=True)

    # SEC identifiers
    accession_number = Column(String(25), nullable=False)
    transaction_index = Column(Integer, nullable=False, default=0)

    # Company
    ticker = Column(String(10), nullable=False, index=True)
    company_name = Column(String(255))
    company_cik = Column(String(10))

    # Insider
    insider_name = Column(String(255), nullable=False, index=True)
    insider_title = Column(String(100))
    insider_cik = Column(String(10))
    is_director = Column(Boolean)
    is_officer = Column(Boolean)
    is_ten_percent_owner = Column(Boolean)

    # Transaction
    transaction_type = Column(String(5), nullable=False, index=True)
    transaction_date = Column(Date, nullable=False, index=True)
    shares = Column(Integer)
    price_per_share = Column(Numeric(12, 4))
    total_value = Column(Numeric(15, 2))

    # Holdings after transaction
    shares_owned_after = Column(BigInteger)

    # Metadata
    filing_date = Column(Date, nullable=False, index=True)
    filing_url = Column(Text)
    raw_data = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "accession_number",
            "transaction_index",
            name="uq_insider_trades_accession_txn_index",
        ),
    )

    def __repr__(self):
        return f"<InsiderTrade {self.ticker} {self.insider_name} {self.transaction_type} {self.shares}>"


class Watchlist(Base):
    """Tracked ticker list for research runs."""

    __tablename__ = "watchlists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<Watchlist {self.ticker} active={self.is_active}>"


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


class EvalResult(Base):
    """Evaluation closure for a research run."""

    __tablename__ = "eval_results"

    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    horizon_days = Column(Integer, nullable=False)
    realized_return = Column(Numeric, nullable=True)
    benchmark_return = Column(Numeric, nullable=True)
    benchmark_symbol = Column(
        String(16),
        nullable=False,
        default="SPY",
        server_default="SPY",
    )
    evaluation_method = Column(
        String(32),
        nullable=False,
        default=EvaluationMethod.RULE_V1.value,
        server_default=EvaluationMethod.RULE_V1.value,
        index=True,
    )
    evaluation_params = Column(JSONB, nullable=True)
    outcome_label = Column(String(32), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run = relationship("ResearchRun", back_populates="eval_result")

    __table_args__ = (
        CheckConstraint("horizon_days > 0", name="ck_eval_results_horizon_days"),
        CheckConstraint(
            f"evaluation_method IN {EvaluationMethod.check_in_sql()}",
            name="ck_eval_results_evaluation_method",
        ),
        CheckConstraint(
            f"outcome_label IS NULL OR outcome_label IN {EvalOutcomeLabel.check_in_sql()}",
            name="ck_eval_results_outcome_label",
        ),
    )

    def __repr__(self):
        return f"<EvalResult {self.run_id} outcome={self.outcome_label}>"
