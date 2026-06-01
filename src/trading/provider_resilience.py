"""Provider guardrails for budget, cache, retry, and circuit state."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol


class ProviderCircuitOpen(RuntimeError):
    """Raised when a provider endpoint circuit is open."""


class ProviderRequestBudgetExceeded(RuntimeError):
    """Raised when a provider endpoint request budget is exhausted."""


@dataclass(frozen=True)
class ProviderRequestRunRecord:
    """Telemetry persisted for every provider attempt or cache decision."""

    provider: str
    endpoint: str
    source_family: str
    scope: str
    cache_status: str
    request_count: int
    budget_remaining: int
    retry_count: int
    backoff_ms: int
    latency_ms: int
    status: str
    error_code: str | None
    circuit_state: str
    degraded_mode: bool
    started_at: datetime
    completed_at: datetime


class ProviderRequestRecorder(Protocol):
    """Storage adapter for provider request telemetry."""

    def record(self, run: ProviderRequestRunRecord) -> None:
        """Persist one provider request run record."""


class InMemoryProviderRequestRecorder:
    """Test recorder for provider request telemetry."""

    def __init__(self) -> None:
        self.runs: list[ProviderRequestRunRecord] = []

    def record(self, run: ProviderRequestRunRecord) -> None:
        self.runs.append(run)


@dataclass
class _CacheEntry:
    value: Any
    stored_at: datetime


class ProviderResiliencePolicy:
    """Synchronous resilience wrapper for provider endpoint calls."""

    def __init__(
        self,
        *,
        provider: str,
        endpoint: str,
        source_family: str | None = None,
        max_requests: int = 100,
        max_retries: int = 2,
        base_backoff: float = 0.05,
        cache_ttl: timedelta = timedelta(minutes=15),
        circuit_failure_threshold: int = 3,
        recorder: ProviderRequestRecorder | None = None,
        now: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.source_family = source_family or endpoint
        self.max_requests = max_requests
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.cache_ttl = cache_ttl
        self.circuit_failure_threshold = circuit_failure_threshold
        self.recorder = recorder or InMemoryProviderRequestRecorder()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper
        self.jitter = jitter or (lambda: 0.0)
        self._cache: dict[str, _CacheEntry] = {}
        self._request_count = 0
        self._failure_count = 0
        self._circuit_state = "closed"

    @property
    def budget_remaining(self) -> int:
        return max(self.max_requests - self._request_count, 0)

    @property
    def circuit_state(self) -> str:
        return self._circuit_state

    def execute(self, scope: str, operation: Callable[[], Any]) -> Any:
        """Execute a provider operation through guardrails and telemetry."""
        started_at = self.now()
        cached = self._cache.get(scope)
        if cached is not None and started_at - cached.stored_at <= self.cache_ttl:
            self._record(
                scope=scope,
                started_at=started_at,
                status="cache_hit",
                cache_status="hit",
                request_count=0,
                retry_count=0,
                backoff_ms=0,
                latency_ms=0,
                error_code=None,
                degraded_mode=False,
            )
            return cached.value

        if self._circuit_state == "open":
            self._record(
                scope=scope,
                started_at=started_at,
                status="circuit_open",
                cache_status="miss",
                request_count=0,
                retry_count=0,
                backoff_ms=0,
                latency_ms=0,
                error_code="circuit_open",
                degraded_mode=True,
            )
            raise ProviderCircuitOpen(f"{self.provider}:{self.endpoint}")

        if self.budget_remaining <= 0:
            self._record(
                scope=scope,
                started_at=started_at,
                status="budget_exceeded",
                cache_status="miss",
                request_count=0,
                retry_count=0,
                backoff_ms=0,
                latency_ms=0,
                error_code="budget_exceeded",
                degraded_mode=True,
            )
            raise ProviderRequestBudgetExceeded(f"{self.provider}:{self.endpoint}")

        retry_count = 0
        backoff_ms = 0
        while True:
            self._request_count += 1
            try:
                result = operation()
                self._cache[scope] = _CacheEntry(result, self.now())
                self._failure_count = 0
                self._record(
                    scope=scope,
                    started_at=started_at,
                    status="succeeded",
                    cache_status="miss",
                    request_count=1,
                    retry_count=retry_count,
                    backoff_ms=backoff_ms,
                    latency_ms=self._latency_ms(started_at),
                    error_code=None,
                    degraded_mode=False,
                )
                return result
            except Exception as exc:
                if retry_count >= self.max_retries or self.budget_remaining <= 0:
                    self._failure_count += 1
                    if self._failure_count >= self.circuit_failure_threshold:
                        self._circuit_state = "open"
                    self._record(
                        scope=scope,
                        started_at=started_at,
                        status="failed",
                        cache_status="miss",
                        request_count=1,
                        retry_count=retry_count,
                        backoff_ms=backoff_ms,
                        latency_ms=self._latency_ms(started_at),
                        error_code=exc.__class__.__name__,
                        degraded_mode=True,
                    )
                    raise
                delay = self.base_backoff * (2 ** retry_count) + self.jitter()
                backoff_ms += int(delay * 1000)
                retry_count += 1
                self.sleeper(delay)

    def _record(
        self,
        *,
        scope: str,
        started_at: datetime,
        status: str,
        cache_status: str,
        request_count: int,
        retry_count: int,
        backoff_ms: int,
        latency_ms: int,
        error_code: str | None,
        degraded_mode: bool,
    ) -> None:
        self.recorder.record(
            ProviderRequestRunRecord(
                provider=self.provider,
                endpoint=self.endpoint,
                source_family=self.source_family,
                scope=scope,
                cache_status=cache_status,
                request_count=request_count,
                budget_remaining=self.budget_remaining,
                retry_count=retry_count,
                backoff_ms=backoff_ms,
                latency_ms=latency_ms,
                status=status,
                error_code=error_code,
                circuit_state=self._circuit_state,
                degraded_mode=degraded_mode,
                started_at=started_at,
                completed_at=self.now(),
            )
        )

    def _latency_ms(self, started_at: datetime) -> int:
        return max(int((self.now() - started_at).total_seconds() * 1000), 0)
