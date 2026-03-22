"""Abstract base class for all data collectors."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class CollectionResult:
    """Standardized summary returned by any collector run."""

    upserted: int = 0
    skipped: int = 0
    errors: int = 0

    @property
    def total(self) -> int:
        return self.upserted + self.skipped + self.errors


class BaseCollector(abc.ABC):
    """
    Abstract base for all periodic data collectors.

    Subclasses must implement ``collect()``, which fetches data from an
    external source and persists it to the database.  The scheduler calls
    ``collect()`` on a configured schedule.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique collector identifier used in logging and scheduling."""
        ...

    @abc.abstractmethod
    def collect(self, target_date: Optional[date] = None) -> CollectionResult:
        """
        Fetch data for *target_date* and persist it to the database.

        If *target_date* is ``None``, implementations should default to today
        in their configured timezone.  Returns a :class:`CollectionResult`
        summary.
        """
        ...
