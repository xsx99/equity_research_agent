from __future__ import annotations

from src.trading import runtime
from src.trading.runtime import dispatch


def test_run_job_phase_delegates_through_runtime_dispatch(monkeypatch):
    expected = {"status": "passed", "phase": "preopen"}
    seen: dict[str, object] = {}

    def _fake_get_job_phase_handler(phase: str):
        assert phase == "preopen"

        def _handler(**kwargs):
            seen.update(kwargs)
            return expected

        return _handler

    monkeypatch.setattr(dispatch, "get_job_phase_handler", _fake_get_job_phase_handler)

    result = runtime.run_job_phase(
        "preopen",
        execute_paper_orders=True,
        execute_paper_option_orders=False,
    )

    assert result is expected
    assert seen == {
        "execute_paper_orders": True,
        "execute_paper_option_orders": False,
    }


def test_run_job_phase_raises_for_unsupported_phase(monkeypatch):
    def _fake_get_job_phase_handler(phase: str):
        raise ValueError(f"unsupported_trading_job_phase:{phase}")

    monkeypatch.setattr(dispatch, "get_job_phase_handler", _fake_get_job_phase_handler)

    try:
        runtime.run_job_phase("unsupported")
    except ValueError as exc:
        assert str(exc) == "unsupported_trading_job_phase:unsupported"
    else:
        raise AssertionError("expected unsupported phase to raise")


def test_get_job_phase_handler_filters_unsupported_execution_kwargs(monkeypatch):
    calls: list[dict[str, object]] = []

    def _reflection_handler() -> dict[str, object]:
        calls.append({})
        return {"status": "passed", "phase": "reflection"}

    monkeypatch.setitem(dispatch.JOB_PHASE_HANDLERS, "reflection", _reflection_handler)

    result = dispatch.get_job_phase_handler("reflection")(
        execute_paper_orders=True,
        execute_paper_option_orders=False,
    )

    assert result == {"status": "passed", "phase": "reflection"}
    assert calls == [{}]


def test_run_smoke_mode_delegates_through_runtime_dispatch(monkeypatch):
    expected = {"status": "passed", "mode": "manual_review_fixture"}

    def _fake_get_smoke_mode_handler(mode: str):
        assert mode == "manual_review_fixture"
        return lambda: expected

    monkeypatch.setattr(dispatch, "get_smoke_mode_handler", _fake_get_smoke_mode_handler)

    result = runtime.run_smoke_mode("manual_review_fixture")

    assert result is expected
