from __future__ import annotations

import json

from scripts import run_trading_smoke_test


def test_run_smoke_mode_returns_fixture_report():
    result = run_trading_smoke_test.run_smoke_mode("manual_review_fixture")

    assert result["status"] == "passed"
    assert result["mode"] == "manual_review_fixture"
    assert result["summary"]["active_manual_requests"] == 1
    assert result["summary"]["latest_result_status"] == "ordinary_watch"


def test_run_smoke_mode_supports_replay_fixture():
    result = run_trading_smoke_test.run_smoke_mode("historical_replay_fixture")

    assert result["status"] == "passed"
    assert result["mode"] == "historical_replay_fixture"
    assert result["summary"]["candidate_count"] >= 1
    assert result["summary"]["outcome_count"] >= 1


def test_run_smoke_mode_covers_option_open_rejection_and_hedge_overlay():
    result = run_trading_smoke_test.run_smoke_mode("paper_option_lifecycle_fixture")

    assert result["status"] == "passed"
    assert result["mode"] == "paper_option_lifecycle_fixture"
    assert result["summary"]["open_risk_status"] == "approved"
    assert result["summary"]["rejection_reason_code"] == "event_through_expiry_short_premium_blocked"
    assert result["summary"]["hedge_overlay_action"] == "adjust_hedge"
    assert result["summary"]["hedge_overlay_basis"] == "approved_assignment_notional"


def test_main_prints_json_report(capsys):
    exit_code = run_trading_smoke_test.main(["--mode", "strategy_evolution_fixture", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["mode"] == "strategy_evolution_fixture"


def test_main_lists_available_modes(capsys):
    exit_code = run_trading_smoke_test.main(["--list-modes"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "manual_review_fixture" in output
    assert "intraday_refresh_fixture" in output
    assert "paper_option_lifecycle_fixture" in output
    assert "paper_trade_dry_run" in output
