from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.agents.prompt_registry import PromptRegistry
from src.trading.post_close.reflection import ReflectionPipeline, ReflectionPipelineRequest
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.agents.trading import PromptRunRecord


def _write_prompt(tmp_path) -> PromptRegistry:
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


def _request() -> ReflectionPipelineRequest:
    now = datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc)
    return ReflectionPipelineRequest(
        trade_date=date(2026, 6, 2),
        decision_time=now,
        available_for_decision_at=now,
        portfolio_outcome={"realized_pnl": 120.0, "unrealized_pnl": -10.0},
        morning_macro_snapshot={"regime": "neutral"},
        strategy_candidates=(),
        manual_ticker_requests=(),
        trading_decisions=(),
        rejected_decisions=(),
        intraday_news_alerts=(),
        intraday_rebalance_decisions=(),
        paper_orders=(),
        paper_executions=(),
        risk_snapshots=(),
        risk_factor_exposures=(),
        portfolio_snapshots=(),
        candidate_outcome_evaluations=(),
        benchmark_peer_returns={"QQQ": 0.01, "SOXX": 0.02},
        paper_option_decisions=(),
        paper_option_positions=(),
        option_risk_snapshots=(),
        worst_case_assignment_snapshots=(),
        risk_hedge_overlays=(),
        hedge_effectiveness={},
        learning_factors_used=(),
    )


def test_reflection_pipeline_persists_reflection_and_learning_factors(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)

    pipeline = ReflectionPipeline(
        repository=repository,
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
                "what_worked": ["Waited for confirmation before chasing momentum."],
                "what_failed": ["Missed a catalyst watch escalation."],
                "attribution": [],
                "learning_factors": [
                    {
                        "factor_type": "candidate_filter",
                        "scope": "strategy",
                        "title": "Require confirmation for risky gaps",
                        "strategy_id": "gap_reversal_v1",
                        "condition": "opening_gap_pct > 0.04 and relative_volume < 1.5",
                        "recommendation": "Require first-30-minute confirmation.",
                        "confidence": 0.70,
                        "activation_policy": "auto_risk_tightening",
                        "effect_tags": ["require_confirmation", "lower_confidence"],
                        "evidence": ["Reduced false starts in replay rows."],
                    },
                    {
                        "factor_type": "score_boost",
                        "scope": "strategy",
                        "title": "Increase score for low-float breakouts",
                        "strategy_id": "gap_reversal_v1",
                        "condition": "low_float and fresh_news",
                        "recommendation": "Add score boost when float is tight.",
                        "confidence": 0.61,
                        "activation_policy": "candidate",
                        "effect_tags": ["increase_score"],
                        "evidence": ["Some winners came from low-float names."],
                    },
                ],
                "strategy_proposal_hints": [{"title": "Potential catalyst-watch sub-strategy"}],
                "schema_version": "v1",
                "generated_at": "2026-06-02T22:00:00+00:00",
            }
        },
    )

    result = pipeline.run(request=_request())

    assert len(result.daily_reflections) == 1
    assert result.daily_reflections[0].status == "succeeded"
    assert len(result.learning_factors) == 2
    assert {factor.status for factor in result.learning_factors} == {"active", "candidate"}
    assert repository.daily_reflections == list(result.daily_reflections)
    assert repository.learning_factors == list(result.learning_factors)
    assert len(repository.llm_prompt_runs) == 1


def test_reflection_pipeline_does_not_mutate_learning_factors_on_fallback(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    pipeline = ReflectionPipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5",
        agent_runner=lambda prompt, model_name: {"content": "not-json"},
    )

    result = pipeline.run(request=_request())

    assert len(result.daily_reflections) == 1
    assert result.daily_reflections[0].status == "fallback"
    assert result.daily_reflections[0].metadata_json["fallback_action"] == "reflection_failed"
    assert result.learning_factors == ()
    assert repository.learning_factors == []


def test_reflection_pipeline_passes_option_and_hedge_payloads_to_agent(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    pipeline = ReflectionPipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5",
        agent_runner=lambda prompt, model_name: {"content": "unused"},
    )
    captured: dict[str, object] = {}

    def _run(payload, context):
        captured.update(payload)
        return SimpleNamespace(
            success=True,
            output_data={
                "trade_date": "2026-06-02",
                "portfolio_summary": {},
                "what_worked": [],
                "what_failed": [],
                "attribution": [],
                "learning_factors": [],
                "strategy_proposal_hints": [],
                "schema_version": "v1",
                "generated_at": "2026-06-02T22:00:00+00:00",
            },
            metadata={
                "prompt_template": object(),
                "prompt_run": PromptRunRecord(
                    pipeline_name="reflection",
                    rendered_prompt_hash="hash",
                    rendered_prompt_redacted="prompt",
                    input_context_json={},
                    raw_output_text="{}",
                    parsed_output_json={},
                    parse_status="succeeded",
                    validation_errors_json=[],
                    fallback_action=None,
                    error_message=None,
                ),
                "usage_events": [],
            },
        )

    pipeline.agent = SimpleNamespace(run=_run)
    request = _request()
    request = ReflectionPipelineRequest(
        **{
            **request.__dict__,
            "paper_option_decisions": ({"ticker": "NVDA", "option_strategy_type": "long_call"},),
            "option_risk_snapshots": ({"ticker": "NVDA", "risk_status": "rejected"},),
            "risk_hedge_overlays": ({"ticker": "QQQ", "action": "open_hedge"},),
            "hedge_effectiveness": {"overlay_count": 1, "protected_notional": 12000.0},
        }
    )

    pipeline.run(request=request)

    assert captured["paper_option_decisions"] == [{"ticker": "NVDA", "option_strategy_type": "long_call"}]
    assert captured["option_risk_snapshots"] == [{"ticker": "NVDA", "risk_status": "rejected"}]
    assert captured["risk_hedge_overlays"] == [{"ticker": "QQQ", "action": "open_hedge"}]
    assert captured["hedge_effectiveness"] == {"overlay_count": 1, "protected_notional": 12000.0}
