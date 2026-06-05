from __future__ import annotations

import json

from scripts import run_trading_once


def test_main_runs_live_preopen_in_dry_run_mode_by_default(monkeypatch, capsys):
    called: dict[str, object] = {}

    def _fake_live_preopen(*, execute_paper_orders: bool = False) -> dict[str, object]:
        called["execute_paper_orders"] = execute_paper_orders
        return {
            "status": "passed",
            "phase": "preopen",
            "execution": {"mode": "dry_run", "orders_submitted": 0},
        }

    monkeypatch.setattr(run_trading_once, "run_live_preopen_once", _fake_live_preopen)

    exit_code = run_trading_once.main(["--phase", "preopen", "--mode", "live-preopen", "--json"])

    assert exit_code == 0
    assert called == {"execute_paper_orders": False}
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["mode"] == "dry_run"


def test_main_allows_explicit_paper_execution_for_live_preopen(monkeypatch, capsys):
    called: dict[str, object] = {}

    def _fake_live_preopen(*, execute_paper_orders: bool = False) -> dict[str, object]:
        called["execute_paper_orders"] = execute_paper_orders
        return {
            "status": "passed",
            "phase": "preopen",
            "execution": {"mode": "execute", "orders_submitted": 1},
        }

    monkeypatch.setattr(run_trading_once, "run_live_preopen_once", _fake_live_preopen)

    exit_code = run_trading_once.main(
        ["--phase", "preopen", "--mode", "live-preopen", "--execute-paper-orders", "--json"]
    )

    assert exit_code == 0
    assert called == {"execute_paper_orders": True}
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["orders_submitted"] == 1


def test_main_returns_zero_and_prints_json_for_skipped_job_phase(monkeypatch, capsys):
    def _fake_run_job_phase(phase: str) -> dict[str, object]:
        assert phase == "reflection"
        return {
            "status": "skipped",
            "phase": "reflection",
            "summary": {"reasons": ["portfolio_outcome_missing"]},
        }

    monkeypatch.setattr(run_trading_once, "run_job_phase", _fake_run_job_phase)

    exit_code = run_trading_once.main(["--phase", "reflection", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "skipped"
    assert payload["summary"]["reasons"] == ["portfolio_outcome_missing"]
