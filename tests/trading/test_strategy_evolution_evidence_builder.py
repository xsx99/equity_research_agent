from datetime import datetime, timezone

from src.trading.phases.strategy_evolution.evidence_builder import StrategyEvolutionEvidenceBuilder


def test_builder_caps_rejected_examples_before_prompt_rendering():
    builder = StrategyEvolutionEvidenceBuilder()
    rejected = tuple(
        {
            "candidate_score_id": f"candidate-{index}",
            "ticker": f"T{index:03}",
            "strategy_id": f"strategy-{index % 55}",
            "rejection_reason": f"reason-{index % 55}",
            "decision_time": datetime(2026, 7, 1, tzinfo=timezone.utc).isoformat(),
            "core_signal_evidence": {"unbounded": "x" * 2000},
        }
        for index in range(140)
    )

    result = builder.build(
        trade_date="2026-07-31",
        decision_time="2026-07-31T20:50:00+00:00",
        reflections=(),
        learning_factors=(),
        rejected_candidates=rejected,
        outcomes=(),
        existing_strategies=(),
    )

    assert result.skip_reason is None
    assert len(result.payload["rejected_candidate_groups"]) == 50
    assert len(result.payload["rejected_candidate_examples"]) <= 40
    assert len(result.rendered_json.encode("utf-8")) <= 120 * 1024


def test_builder_returns_budget_skip_without_truncating_json():
    builder = StrategyEvolutionEvidenceBuilder(max_prompt_bytes=100)

    result = builder.build(
        trade_date="2026-07-31",
        decision_time="2026-07-31T20:50:00+00:00",
        reflections=(),
        learning_factors=(),
        rejected_candidates=(),
        outcomes=(),
        existing_strategies=({"strategy_id": "x", "display_name": "x" * 200},),
    )

    assert result.skip_reason == "input_budget_exceeded"
    assert result.rendered_json is None
