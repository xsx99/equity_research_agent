"""Abstract base class for all scheduled jobs."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JobConfig:
    """
    APScheduler configuration for a scheduled job.

    Attributes:
        job_id:              Unique identifier used by APScheduler.
        trigger:             Trigger type: ``"cron"``, ``"interval"``, or ``"date"``.
        trigger_kwargs:      Keyword arguments forwarded to the APScheduler trigger
                             (e.g. ``{"hour": 2, "minute": 0}`` for a cron trigger).
        coalesce:            If ``True``, run only once when catching up on missed fires.
        max_instances:       Maximum concurrent instances of this job.
        misfire_grace_time:  Seconds after the scheduled time that the job is still
                             allowed to run if it missed its window.
    """

    job_id: str
    trigger: str
    trigger_kwargs: dict[str, Any] = field(default_factory=dict)
    coalesce: bool = True
    max_instances: int = 1
    misfire_grace_time: int = 3600


class BaseJob(abc.ABC):
    """
    Abstract base for all scheduled jobs.

    Subclasses must implement:

    * :attr:`config` — returns the :class:`JobConfig` for APScheduler registration.
    * :meth:`run`    — the job body.  **Must catch and log all exceptions** so the
      scheduler continues unaffected after a failure.

    Set the ``run_on_startup`` class attribute to ``True`` if the job should
    execute immediately when the scheduler starts, in addition to its regular
    schedule.
    """

    run_on_startup: bool = False

    @property
    @abc.abstractmethod
    def config(self) -> JobConfig:
        """Return the APScheduler configuration for this job."""
        ...

    @abc.abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> None:
        """
        Execute the job body.

        Implementations must handle their own exception logging and must not
        let exceptions propagate — APScheduler will log uncaught exceptions
        but the scheduler itself keeps running regardless.
        """
        ...
