"""Evaluation ORM model and enums."""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .base import Base, ChoiceEnum


class EvalOutcomeLabel(ChoiceEnum):
    CORRECT = "correct"
    PARTIALLY_CORRECT = "partially_correct"
    WRONG_DIRECTION = "wrong_direction"
    UNINFORMATIVE = "uninformative"


class EvaluationMethod(ChoiceEnum):
    RULE_V1 = "rule_v1"


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
