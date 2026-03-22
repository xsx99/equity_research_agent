"""Integration tests for research-app schema migration and ORM models."""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from src.config import DATABASE_URL
from src.db.models import (
    EvalOutcomeLabel,
    EvalResult,
    EvaluationMethod,
    ResearchActionability,
    ResearchDecision,
    ResearchOutput,
    ResearchRun,
    ResearchTimeHorizon,
    RunStatus,
    Watchlist,
)


def _build_admin_url() -> URL:
    """Build an admin URL that can create/drop temporary test databases."""
    override = os.getenv("TEST_DATABASE_ADMIN_URL")
    if override:
        return make_url(override)

    source_url = make_url(os.getenv("TEST_DATABASE_URL", DATABASE_URL))
    admin_db_name = os.getenv("TEST_DATABASE_ADMIN_DB", "postgres")
    return source_url.set(database=admin_db_name)


@pytest.fixture()
def postgres_test_db_url() -> str:
    """Create and destroy an isolated temporary Postgres database for tests."""
    admin_url = _build_admin_url()
    admin_engine = create_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )

    try:
        with admin_engine.connect():
            pass
    except OperationalError as exc:
        pytest.skip(f"Postgres not available for migration tests: {exc}")

    db_name = f"insider_research_test_{uuid.uuid4().hex[:10]}"

    try:
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except SQLAlchemyError as exc:
        admin_engine.dispose()
        pytest.skip(f"Cannot create temporary database for tests: {exc}")

    test_url = str(admin_url.set(database=db_name))

    try:
        yield test_url
    finally:
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :db_name AND pid <> pg_backend_pid()"
                ),
                {"db_name": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))

        admin_engine.dispose()


@pytest.fixture()
def alembic_cfg(postgres_test_db_url: str) -> Config:
    """Build Alembic config bound to the temporary database."""
    project_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", postgres_test_db_url)
    return cfg


def test_migration_upgrade_and_downgrade_smoke(
    postgres_test_db_url: str,
    alembic_cfg: Config,
) -> None:
    """Ensure the new research schema migrates up/down cleanly."""
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(postgres_test_db_url, poolclass=NullPool)
    inspector = inspect(engine)

    tables = set(inspector.get_table_names())
    assert "insider_trades" in tables
    assert "watchlists" in tables
    assert "research_runs" in tables
    assert "research_outputs" in tables
    assert "eval_results" in tables
    engine.dispose()

    command.downgrade(alembic_cfg, "002")

    engine = create_engine(postgres_test_db_url, poolclass=NullPool)
    inspector = inspect(engine)
    tables_after_downgrade = set(inspector.get_table_names())
    assert "insider_trades" in tables_after_downgrade
    assert "watchlists" not in tables_after_downgrade
    assert "research_runs" not in tables_after_downgrade
    assert "research_outputs" not in tables_after_downgrade
    assert "eval_results" not in tables_after_downgrade
    engine.dispose()


def test_research_models_round_trip(
    postgres_test_db_url: str,
    alembic_cfg: Config,
) -> None:
    """Insert and read all research entities through ORM relationships."""
    command.upgrade(alembic_cfg, "head")

    assert RunStatus.choices() == ("queued", "running", "succeeded", "failed")
    assert ResearchDecision.choices() == ("bullish", "bearish", "neutral", "abstain")
    assert ResearchTimeHorizon.days_mapping()["3d"] == 3
    assert EvaluationMethod.choices() == ("rule_v1",)

    engine = create_engine(postgres_test_db_url, poolclass=NullPool)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as session:
        watchlist = Watchlist(ticker="AAPL")
        session.add(watchlist)

        run = ResearchRun(
            ticker="AAPL",
            as_of=datetime.now(timezone.utc),
            prompt_version="v1",
            model_name="gpt-4.1-mini",
            input_json={
                "ticker": "AAPL",
                "as_of": "2026-03-21T12:00:00Z",
                "price_snapshot": {"last_price": 220.0, "return_1d": 0.01, "return_5d": 0.02},
                "context": {"sector": "Technology", "earnings_in_days": 12},
                "news": [{"title": "Sample headline", "summary": "Sample summary"}],
            },
            status=RunStatus.QUEUED.value,
        )
        session.add(run)
        session.flush()

        output = ResearchOutput(
            run_id=run.run_id,
            output_json={
                "decision": "bullish",
                "confidence": 0.73,
                "time_horizon": "3d",
                "actionability": "watch",
                "thesis_summary": "Momentum improving.",
                "key_drivers": ["Relative strength"],
                "counterarguments": ["Valuation stretched"],
                "invalidators": ["Break below support"],
            },
            decision=ResearchDecision.BULLISH.value,
            confidence=0.73,
            time_horizon=ResearchTimeHorizon.THREE_DAYS.value,
            actionability=ResearchActionability.WATCH.value,
            thesis_summary="Momentum improving.",
        )
        session.add(output)

        eval_result = EvalResult(
            run_id=run.run_id,
            horizon_days=ResearchTimeHorizon.days_mapping()[ResearchTimeHorizon.THREE_DAYS.value],
            realized_return=0.021,
            benchmark_return=0.013,
            benchmark_symbol="SPY",
            evaluation_method=EvaluationMethod.RULE_V1.value,
            evaluation_params={"market_data": {"ticker_start": 100, "ticker_end": 102.1}},
            outcome_label=EvalOutcomeLabel.CORRECT.value,
        )
        session.add(eval_result)
        session.commit()

        fetched_run = session.query(ResearchRun).filter_by(run_id=run.run_id).one()
        assert fetched_run.status == RunStatus.QUEUED.value
        assert fetched_run.output is not None
        assert fetched_run.output.decision == ResearchDecision.BULLISH.value
        assert fetched_run.output.time_horizon == ResearchTimeHorizon.THREE_DAYS.value
        assert fetched_run.eval_result is not None
        assert fetched_run.eval_result.evaluation_method == EvaluationMethod.RULE_V1.value
        assert fetched_run.eval_result.outcome_label == EvalOutcomeLabel.CORRECT.value
        assert fetched_run.eval_result.horizon_days == 3

    engine.dispose()
