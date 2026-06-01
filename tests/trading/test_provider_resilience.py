from datetime import datetime, timedelta, timezone

import pytest

from src.trading.provider_resilience import (
    InMemoryProviderRequestRecorder,
    ProviderCircuitOpen,
    ProviderRequestBudgetExceeded,
    ProviderResiliencePolicy,
)


def test_provider_resilience_records_cache_hit_without_provider_call():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    recorder = InMemoryProviderRequestRecorder()
    policy = ProviderResiliencePolicy(
        provider="fake",
        endpoint="bars",
        max_requests=2,
        cache_ttl=timedelta(minutes=5),
        recorder=recorder,
        now=lambda: now,
    )
    calls = 0

    def fetch():
        nonlocal calls
        calls += 1
        return {"ok": calls}

    assert policy.execute("AAPL", fetch) == {"ok": 1}
    assert policy.execute("AAPL", fetch) == {"ok": 1}

    assert calls == 1
    assert [run.status for run in recorder.runs] == ["succeeded", "cache_hit"]
    assert recorder.runs[-1].request_count == 0
    assert recorder.runs[-1].budget_remaining == 1


def test_provider_resilience_retries_then_opens_circuit_after_failures():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    recorder = InMemoryProviderRequestRecorder()
    policy = ProviderResiliencePolicy(
        provider="fake",
        endpoint="fundamentals",
        max_requests=5,
        max_retries=1,
        circuit_failure_threshold=1,
        recorder=recorder,
        now=lambda: now,
        sleeper=lambda seconds: None,
        jitter=lambda: 0.0,
    )

    with pytest.raises(RuntimeError, match="temporary"):
        policy.execute("AAPL", lambda: (_ for _ in ()).throw(RuntimeError("temporary")))

    assert recorder.runs[-1].status == "failed"
    assert recorder.runs[-1].retry_count == 1
    assert recorder.runs[-1].circuit_state == "open"
    assert recorder.runs[-1].degraded_mode is True

    with pytest.raises(ProviderCircuitOpen):
        policy.execute("MSFT", lambda: {"never": "called"})
    assert recorder.runs[-1].status == "circuit_open"
    assert recorder.runs[-1].request_count == 0


def test_provider_resilience_enforces_request_budget():
    recorder = InMemoryProviderRequestRecorder()
    policy = ProviderResiliencePolicy(
        provider="fake",
        endpoint="events",
        max_requests=1,
        cache_ttl=timedelta(0),
        recorder=recorder,
        now=lambda: datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
    )

    assert policy.execute("AAPL", lambda: {"ticker": "AAPL"}) == {"ticker": "AAPL"}
    with pytest.raises(ProviderRequestBudgetExceeded):
        policy.execute("MSFT", lambda: {"ticker": "MSFT"})

    assert recorder.runs[-1].status == "budget_exceeded"
    assert recorder.runs[-1].budget_remaining == 0
