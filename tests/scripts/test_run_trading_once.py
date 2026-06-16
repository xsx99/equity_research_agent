from __future__ import annotations

import json

from scripts import run_trading_once


def test_main_runs_live_preopen_in_dry_run_mode_by_default(monkeypatch, capsys):
    called: dict[str, object] = {}

    def _fake_live_preopen(
        *,
        execute_paper_orders: bool = False,
        execute_paper_option_orders: bool = False,
    ) -> dict[str, object]:
        called["execute_paper_orders"] = execute_paper_orders
        called["execute_paper_option_orders"] = execute_paper_option_orders
        return {
            "status": "passed",
            "phase": "preopen",
            "execution": {"mode": "dry_run", "orders_submitted": 0, "option_orders_submitted": 0},
        }

    monkeypatch.setattr(run_trading_once, "run_live_preopen_once", _fake_live_preopen)

    exit_code = run_trading_once.main(["--phase", "preopen", "--mode", "live-preopen", "--json"])

    assert exit_code == 0
    assert called == {"execute_paper_orders": False, "execute_paper_option_orders": False}
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["mode"] == "dry_run"


def test_main_allows_explicit_paper_execution_for_live_preopen(monkeypatch, capsys):
    called: dict[str, object] = {}

    def _fake_live_preopen(
        *,
        execute_paper_orders: bool = False,
        execute_paper_option_orders: bool = False,
    ) -> dict[str, object]:
        called["execute_paper_orders"] = execute_paper_orders
        called["execute_paper_option_orders"] = execute_paper_option_orders
        return {
            "status": "passed",
            "phase": "preopen",
            "execution": {"mode": "execute", "orders_submitted": 1, "option_orders_submitted": 1},
        }

    monkeypatch.setattr(run_trading_once, "run_live_preopen_once", _fake_live_preopen)

    exit_code = run_trading_once.main(
        [
            "--phase",
            "preopen",
            "--mode",
            "live-preopen",
            "--execute-paper-orders",
            "--execute-paper-option-orders",
            "--json",
        ]
    )

    assert exit_code == 0
    assert called == {"execute_paper_orders": True, "execute_paper_option_orders": True}
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["orders_submitted"] == 1
    assert payload["execution"]["option_orders_submitted"] == 1


def test_main_runs_live_manual_review_in_dry_run_mode_by_default(monkeypatch, capsys):
    called: dict[str, object] = {}

    def _fake_live_manual_review(
        *,
        execute_paper_orders: bool = False,
    ) -> dict[str, object]:
        called["execute_paper_orders"] = execute_paper_orders
        return {
            "status": "passed",
            "phase": "manual_review",
            "execution": {"mode": "dry_run", "orders_submitted": 0, "option_orders_submitted": 0},
        }

    monkeypatch.setattr(run_trading_once, "run_live_manual_review_once", _fake_live_manual_review)

    exit_code = run_trading_once.main(["--phase", "manual_review", "--mode", "live-manual-review", "--json"])

    assert exit_code == 0
    assert called == {"execute_paper_orders": False}
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["mode"] == "dry_run"


def test_main_allows_explicit_paper_execution_for_live_manual_review(monkeypatch, capsys):
    called: dict[str, object] = {}

    def _fake_live_manual_review(
        *,
        execute_paper_orders: bool = False,
    ) -> dict[str, object]:
        called["execute_paper_orders"] = execute_paper_orders
        return {
            "status": "passed",
            "phase": "manual_review",
            "execution": {"mode": "execute", "orders_submitted": 1, "option_orders_submitted": 0},
        }

    monkeypatch.setattr(run_trading_once, "run_live_manual_review_once", _fake_live_manual_review)

    exit_code = run_trading_once.main(
        [
            "--phase",
            "manual_review",
            "--mode",
            "live-manual-review",
            "--execute-paper-orders",
            "--json",
        ]
    )

    assert exit_code == 0
    assert called == {"execute_paper_orders": True}
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["orders_submitted"] == 1
    assert payload["execution"]["option_orders_submitted"] == 0


def test_main_rejects_live_manual_review_option_execution(monkeypatch):
    monkeypatch.setattr(
        run_trading_once,
        "run_live_manual_review_once",
        lambda **kwargs: {"status": "passed", "phase": "manual_review"},
    )

    try:
        run_trading_once.main(
            [
                "--phase",
                "manual_review",
                "--mode",
                "live-manual-review",
                "--execute-paper-orders",
                "--execute-paper-option-orders",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse failure for manual-review option execution")


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
