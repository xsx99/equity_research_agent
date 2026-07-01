from datetime import date, datetime, timezone

from src.agents.prompt_registry import PromptRegistry
from src.agents.reflection import ReflectionAgent, _default_agent_runner


def _write_prompt(tmp_path):
    prompt_dir = tmp_path / "prompts" / "trading"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "reflection_v1.yaml"
    prompt_file.write_text(
        "prompt_id: reflection\n"
        "prompt_version: v1\n"
        "pipeline_name: reflection\n"
        "output_schema_id: reflection\n"
        "output_schema_version: v1\n"
        "template: |\n"
        "  Reflect on trade date {{ trade_date }}.\n"
        "  Input JSON: {{ input_payload_json }}\n",
        encoding="utf-8",
    )
    return PromptRegistry(root=tmp_path / "prompts")


def _payload():
    now = datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc)
    return {
        "trade_date": date(2026, 6, 2).isoformat(),
        "decision_time": now.isoformat(),
        "available_for_decision_at": now.isoformat(),
        "portfolio_outcome": {"realized_pnl": 120.0, "unrealized_pnl": -10.0},
        "morning_macro_snapshot": {"regime": "neutral"},
        "strategy_candidates": [],
        "manual_ticker_requests": [],
        "trading_decisions": [],
        "rejected_decisions": [],
        "intraday_news_alerts": [],
        "intraday_rebalance_decisions": [],
        "paper_orders": [],
        "paper_executions": [],
        "risk_snapshots": [],
        "risk_factor_exposures": [],
        "portfolio_snapshots": [],
        "candidate_outcome_evaluations": [],
        "benchmark_peer_returns": {"QQQ": 0.01, "SOXX": 0.02},
        "paper_option_decisions": [],
        "paper_option_positions": [],
        "option_risk_snapshots": [],
        "worst_case_assignment_snapshots": [],
        "learning_factors_used": [],
    }


def test_reflection_agent_retries_once_and_returns_validated_output(tmp_path):
    registry = _write_prompt(tmp_path)
    calls: list[str] = []

    def runner(prompt: str, model_name: str):
        calls.append(prompt)
        if len(calls) == 1:
            return {"content": "not-json"}
        return {
            "content": {
                "trade_date": "2026-06-02",
                "portfolio_summary": {
                    "realized_pnl": 120.0,
                    "unrealized_pnl": -10.0,
                    "benchmark_return": 0.01,
                },
                "what_worked": ["Waited for confirmation before chasing momentum."],
                "what_failed": ["Missed a catalyst watch escalation."],
                "attribution": [
                    {
                        "strategy_id": "gap_reversal_v1",
                        "result": "negative",
                        "root_cause": "entry_too_early",
                        "evidence": ["MAE exceeded planned risk before confirmation."],
                    }
                ],
                "learning_factors": [
                    {
                        "factor_type": "candidate_filter",
                        "scope": "strategy",
                        "title": "Require volume confirmation for large opening gaps",
                        "strategy_id": "gap_reversal_v1",
                        "condition": "opening_gap_pct > 0.04 and relative_volume < 1.5",
                        "recommendation": "Downgrade candidate unless volume confirms in first 30 minutes.",
                        "confidence": 0.66,
                        "activation_policy": "auto_risk_tightening",
                        "effect_tags": ["require_confirmation", "lower_confidence"],
                        "evidence": ["Large gaps without volume reversed more often than expected."],
                    }
                ],
                "strategy_proposal_hints": [
                    {"title": "Consider catalyst_watch escalation for earnings drifts."}
                ],
                "schema_version": "v1",
                "generated_at": "2026-06-02T22:00:00+00:00",
            }
        }

    agent = ReflectionAgent(
        tool_registry=None,
        prompt_registry=registry,
        model_name="gpt-5",
        agent_runner=runner,
    )

    result = agent.run(_payload(), context=None)

    assert result.success is True
    assert result.output_data["portfolio_summary"]["realized_pnl"] == 120.0
    assert result.metadata["retry_count"] == 1
    assert "previous validation error" in calls[1].lower()


def test_reflection_agent_accepts_prompted_analysis_sections(tmp_path):
    registry = _write_prompt(tmp_path)

    agent = ReflectionAgent(
        tool_registry=None,
        prompt_registry=registry,
        model_name="gpt-5",
        agent_runner=lambda prompt, model_name: {
            "content": {
                "trade_date": "2026-06-02",
                "portfolio_summary": {
                    "realized_pnl": 120.0,
                    "unrealized_pnl": -10.0,
                    "benchmark_return": 0.01,
                },
                "portfolio_analysis": {
                    "bullish_catalyst_trades": [],
                    "bearish_or_risk_off_calls": [],
                    "replay_outcome_rows": [],
                },
                "confidence_calibration": {
                    "overall_confidence": 0.5,
                    "bullish_confidence": None,
                    "bearish_confidence": None,
                },
                "factor_concentration": {"factors": {}},
                "candidate_misses": {"missed_candidates": []},
                "manual_ticker_requests_evaluation": {
                    "AAPL": {
                        "was_catalyst_watch_appropriate": True,
                    }
                },
                "what_worked": ["Waited for confirmation before chasing momentum."],
                "what_failed": ["Missed a catalyst watch escalation."],
                "attribution": [],
                "learning_factors": [],
                "strategy_proposal_hints": [],
                "schema_version": "v1",
                "generated_at": "2026-06-02T22:00:00+00:00",
            }
        },
    )

    result = agent.run(_payload(), context=None)

    assert result.success is True
    assert result.output_data["portfolio_analysis"]["replay_outcome_rows"] == []
    assert result.output_data["manual_ticker_requests_evaluation"]["AAPL"][
        "was_catalyst_watch_appropriate"
    ] is True


def test_reflection_agent_normalizes_loose_production_sections(tmp_path):
    registry = _write_prompt(tmp_path)

    agent = ReflectionAgent(
        tool_registry=None,
        prompt_registry=registry,
        model_name="gpt-5",
        agent_runner=lambda prompt, model_name: {
            "content": {
                "trade_date": "2026-06-02",
                "portfolio_summary": {"realized_pnl": 120.0},
                "portfolio_analysis": {},
                "confidence_calibration": {},
                "factor_concentration": {},
                "candidate_misses": [],
                "manual_ticker_requests_evaluation": {},
                "what_worked": [
                    {
                        "ticker": "APP",
                        "analysis": "Entry discipline improved the trade outcome.",
                    }
                ],
                "what_failed": [
                    {
                        "ticker": "MRVL",
                        "analysis": "Scanner signal acquisition missed follow-through.",
                    }
                ],
                "attribution": {
                    "portfolio_pnl": 120.0,
                    "drivers": ["APP carried the session."],
                },
                "learning_factors": [
                    {
                        "factor_type": "data_completeness",
                        "scope": "scanner_signal_acquisition",
                        "title": "Improve scanner signal coverage",
                        "description": "Rejected candidates lacked enough quantitative signals.",
                        "application": "Refine signal acquisition before scoring.",
                        "confidence": "high",
                    }
                ],
                "strategy_proposal_hints": [],
                "schema_version": "v1",
                "generated_at": "2026-06-02T22:00:00+00:00",
            }
        },
    )

    result = agent.run(_payload(), context=None)

    assert result.success is True
    assert isinstance(result.output_data["what_worked"][0], str)
    assert result.output_data["attribution"][0]["strategy_id"] == "portfolio"
    assert result.output_data["learning_factors"][0]["scope"] == "portfolio"
    assert result.output_data["learning_factors"][0]["activation_policy"] == "observation"
    assert result.output_data["learning_factors"][0]["confidence"] == 0.8


def test_reflection_agent_returns_safe_fallback_after_retry_failure(tmp_path):
    registry = _write_prompt(tmp_path)

    agent = ReflectionAgent(
        tool_registry=None,
        prompt_registry=registry,
        model_name="gpt-5",
        agent_runner=lambda prompt, model_name: {"content": "still-not-json"},
    )

    result = agent.run(_payload(), context=None)

    assert result.success is False
    assert result.output_data["reflection_status"] == "reflection_failed"
    assert result.output_data["fallback_action"] == "reflection_failed"
    assert result.metadata["retry_count"] == 1


def test_default_reflection_agent_runner_delegates_to_trading_runner(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_runner(prompt: str, model_name: str):
        calls.append((prompt, model_name))
        return {"content": '{"ok": true}'}

    monkeypatch.setattr("src.agents.reflection._trading_default_agent_runner", fake_runner, raising=False)

    response = _default_agent_runner("reflection prompt", "gpt-5-mini")

    assert response == {"content": '{"ok": true}'}
    assert calls == [("reflection prompt", "gpt-5-mini")]
