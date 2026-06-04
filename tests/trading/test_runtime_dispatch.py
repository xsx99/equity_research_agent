from __future__ import annotations

from src.trading import runtime, runtime_dispatch


def test_run_job_phase_delegates_through_runtime_dispatch(monkeypatch):
    expected = {"status": "passed", "phase": "preopen"}

    def _fake_get_job_phase_handler(phase: str):
        assert phase == "preopen"
        return lambda: expected

    monkeypatch.setattr(runtime_dispatch, "get_job_phase_handler", _fake_get_job_phase_handler)

    result = runtime.run_job_phase("preopen")

    assert result is expected


def test_run_job_phase_raises_for_unsupported_phase(monkeypatch):
    def _fake_get_job_phase_handler(phase: str):
        raise ValueError(f"unsupported_trading_job_phase:{phase}")

    monkeypatch.setattr(runtime_dispatch, "get_job_phase_handler", _fake_get_job_phase_handler)

    try:
        runtime.run_job_phase("unsupported")
    except ValueError as exc:
        assert str(exc) == "unsupported_trading_job_phase:unsupported"
    else:
        raise AssertionError("expected unsupported phase to raise")


def test_run_smoke_mode_delegates_through_runtime_dispatch(monkeypatch):
    expected = {"status": "passed", "mode": "manual_review_fixture"}

    def _fake_get_smoke_mode_handler(mode: str):
        assert mode == "manual_review_fixture"
        return lambda: expected

    monkeypatch.setattr(runtime_dispatch, "get_smoke_mode_handler", _fake_get_smoke_mode_handler)

    result = runtime.run_smoke_mode("manual_review_fixture")

    assert result is expected
