"""Shared SQLAlchemy base and enum helpers for all DB models."""
import enum

from sqlalchemy.orm import declarative_base


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
