"""Database connection management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from alembic.config import Config
from alembic import command
import os

from src.core.config import DATABASE_URL
from src.core.logging import get_logger

logger = get_logger(__name__)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Run database migrations to ensure schema is up to date."""
    # Find alembic.ini relative to project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    alembic_ini = os.path.join(project_root, "alembic.ini")
    
    alembic_cfg = Config(alembic_ini)
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    alembic_cfg.set_main_option("script_location", os.path.join(project_root, "alembic"))
    
    logger.info("db_migrations_starting")
    command.upgrade(alembic_cfg, "head")
    # Alembic's fileConfig can override app logging; restore our handlers/level.
    get_logger(__name__, force=True)
    logger.info("db_migrations_complete")


@contextmanager
def get_session() -> Session:
    """Get database session context manager."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
