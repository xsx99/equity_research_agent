from __future__ import annotations

from datetime import date, datetime, timezone

from src.agents.prompt_registry import PromptRegistry
from src.trading.post_close.reflection import DailyReflectionRecord, LearningFactorRecord
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.replay.outcomes import CandidateOutcomeEvaluationRecord
from src.trading.strategies.matching import StrategyDefinitionRecord
from src.trading.post_close.strategy_evolution import StrategyEvolutionPipeline, StrategyEvolutionRequest


def _write_prompt(tmp_path) -> PromptRegistry:
    prompt_dir = tmp_path / "prompts" / "trading"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "strategy_evolution_v1.yaml"
    prompt_file.write_text(
        "prompt_id: strategy_evolution\n"
        "prompt_version: v1\n"
        "pipeline_name: strategy_evolution\n"
        "output_schema_id: strategy_evolution\n"
        "output_schema_version: v1\n"
        "template: |\n"
        "  Synthesize strategy proposals for trade date {{ trade_date }}.\n"
        "  Input JSON: {{ input_payload_json }}\n",
        encoding="utf-8",
    )
    return PromptRegistry(root=tmp_path / "prompts")


def _request() -> StrategyEvolutionRequest:
    now = datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc)
    return StrategyEvolutionRequest(
        trade_date=date(2026, 6, 2),
        decision_time=now,
        available_for_decision_at=now,
        daily_reflections=(
            DailyReflectionRecord(
                daily_reflection_id="reflection-1",
                trade_date=date(2026, 6, 2),
                status="succeeded",
                prompt_template=object(),
                prompt_run=object(),
                usage_events=[],
                reflection_json={"what_failed": ["missed reclaim follow-through"]},
                strategy_proposal_hints=(
                    {"title": "Post-gap VWAP reclaim continuation"},
                ),
                metadata_json={},
            ),
        ),
        learning_factors=(
            LearningFactorRecord(
                learning_factor_id="lf-1",
                factor_key="lf_2026_06_02_01",
                trade_date=date(2026, 6, 2),
                title="Track VWAP reclaim after early gap fade",
                factor_type="candidate_filter",
                scope="strategy",
                status="candidate",
                strategy_id=None,
                condition="opening_gap_pct > 0.02 and vwap_reclaim",
                recommendation="Score reclaim patterns separately from gap-and-go.",
                confidence=0.64,
                activation_policy="candidate",
                effect_tags=("increase_score",),
                evidence=("Worked on several rejected names.",),
                source_daily_reflection_id="reflection-1",
                metadata_json={},
            ),
            LearningFactorRecord(
                learning_factor_id="lf-2",
                factor_key="lf_2026_06_02_02",
                trade_date=date(2026, 6, 2),
                title="Observation only",
                factor_type="candidate_filter",
                scope="strategy",
                status="observation",
                strategy_id=None,
                condition="sector_rank_percentile > 0.8",
                recommendation="Keep as soft context.",
                confidence=0.55,
                activation_policy="observation",
                effect_tags=(),
                evidence=("Seen in a few winners.",),
                source_daily_reflection_id="reflection-1",
                metadata_json={},
            ),
        ),
        rejected_candidates=(
            {
                "ticker": "PLTR",
                "strategy_id": "gap_and_go_v1",
                "rejection_reason": "no_clean_entry",
                "core_signal_evidence": {"technical.vwap_reclaim": True},
            },
        ),
        candidate_outcome_evaluations=(
            CandidateOutcomeEvaluationRecord(
                candidate_outcome_evaluation_id="outcome-1",
                historical_replay_run_id=None,
                candidate_score_id="candidate-1",
                trade_classification_id=None,
                ticker="PLTR",
                strategy_id="gap_and_go_v1",
                strategy_version="v1",
                expression_bucket_id="long_stock",
                trade_identity="watch_only",
                direction="bullish",
                catalyst_type="earnings",
                confidence_bucket="gap_reclaim",
                decision_time=now,
                horizon_start_at=now,
                horizon_end_at=now,
                evaluation_status="final",
                candidate_return=0.05,
                benchmark_returns={"QQQ": 0.01},
                peer_basket_id=None,
                peer_basket_return=None,
                alpha=0.04,
                max_favorable_excursion=0.06,
                max_adverse_excursion=-0.01,
                regime="neutral",
                sector_theme="software",
                metadata_json={"would_have_worked": True},
            ),
        ),
    )


def test_strategy_evolution_pipeline_creates_shadow_strategy_from_unique_proposal(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    repository.save_strategy_definition(
        StrategyDefinitionRecord(
            strategy_definition_id="existing-1",
            strategy_id="gap_and_go_v1",
            version="v1",
            display_name="Gap-and-Go",
            strategy_layer="tactical_pattern",
            typical_horizon="intraday-3d",
            config_json={
                "required_signals": ["opening_gap_pct", "vwap_hold", "opening_range_high_break"],
                "risk_tags": ["gap_risk"],
                "core_thesis": "Overnight information continues as momentum.",
            },
            lifecycle_status="active",
            is_active=True,
            source="seed",
        )
    )
    pipeline = StrategyEvolutionPipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5",
        agent_runner=lambda prompt, model_name: {
            "content": {
                "proposals": [
                    {
                        "proposed_strategy_id": "post_gap_vwap_reclaim_v1",
                        "display_name": "Post-Gap VWAP Reclaim",
                        "source_reflection_ids": ["reflection-1"],
                        "core_thesis": "Stocks that fade an opening gap and reclaim VWAP with renewed volume often continue.",
                        "typical_horizon": "intraday-3d",
                        "required_signals": [
                            "opening_gap_pct",
                            "vwap_reclaim",
                            "relative_volume",
                            "opening_range_reclaim",
                        ],
                        "optional_signals": ["fresh_catalyst_type", "sector_rank_percentile"],
                        "scoring_rules": {"min_opening_gap_pct": 0.02, "min_relative_volume_after_reclaim": 1.2},
                        "risk_tags": ["gap_risk", "intraday_momentum"],
                        "macro_blocked_regimes": ["stressed"],
                        "invalidators": ["re-loses VWAP", "relative volume fades"],
                        "evidence_summary": "Observed in rejected candidates that later outperformed.",
                    }
                ],
                "schema_version": "v1",
                "generated_at": "2026-06-02T22:00:00+00:00",
            }
        },
    )

    result = pipeline.run(request=_request())

    assert len(result.strategy_proposals) == 1
    assert result.strategy_proposals[0].proposal_status == "accepted"
    assert result.strategy_proposals[0].proposed_lifecycle_status == "shadow"
    assert result.strategy_proposals[0].source_daily_reflection_id == "reflection-1"
    assert len(result.strategy_definitions) == 1
    assert result.strategy_definitions[0].strategy_id == "post_gap_vwap_reclaim_v1"
    assert result.strategy_definitions[0].lifecycle_status == "shadow"
    assert result.strategy_evaluation_results[-1].new_lifecycle_status == "shadow"
    assert len(repository.llm_prompt_runs) == 1


def test_strategy_evolution_pipeline_rejects_duplicates_and_persists_failed_proposals(tmp_path):
    repository = InMemoryTradingRepository()
    registry = _write_prompt(tmp_path)
    repository.save_strategy_definition(
        StrategyDefinitionRecord(
            strategy_definition_id="existing-1",
            strategy_id="gap_and_go_v1",
            version="v1",
            display_name="Gap-and-Go",
            strategy_layer="tactical_pattern",
            typical_horizon="intraday-3d",
            config_json={
                "required_signals": ["opening_gap_pct", "vwap_hold", "opening_range_high_break", "relative_volume"],
                "risk_tags": ["gap_risk", "intraday_momentum"],
                "core_thesis": "Overnight information continues as momentum.",
            },
            lifecycle_status="active",
            is_active=True,
            source="seed",
        )
    )
    duplicate_pipeline = StrategyEvolutionPipeline(
        repository=repository,
        prompt_registry=registry,
        model_name="gpt-5",
        agent_runner=lambda prompt, model_name: {
            "content": {
                "proposals": [
                    {
                        "proposed_strategy_id": "another_gap_and_go_v1",
                        "display_name": "Another Gap-and-Go",
                        "source_reflection_ids": ["reflection-1"],
                        "core_thesis": "Overnight information continues as momentum.",
                        "typical_horizon": "intraday-3d",
                        "required_signals": [
                            "opening_gap_pct",
                            "vwap_hold",
                            "opening_range_high_break",
                            "relative_volume",
                        ],
                        "optional_signals": [],
                        "scoring_rules": {"min_opening_gap_pct": 0.02},
                        "risk_tags": ["gap_risk", "intraday_momentum"],
                        "macro_blocked_regimes": [],
                        "invalidators": ["loses VWAP"],
                        "evidence_summary": "Same pattern restated.",
                    }
                ],
                "schema_version": "v1",
                "generated_at": "2026-06-02T22:00:00+00:00",
            }
        },
    )

    duplicate_result = duplicate_pipeline.run(request=_request())

    assert duplicate_result.strategy_proposals[0].proposal_status == "duplicate_rejected"
    assert duplicate_result.strategy_proposals[0].duplicate_of_strategy_id == "gap_and_go_v1"
    assert duplicate_result.strategy_proposals[0].source_daily_reflection_id == "reflection-1"
    assert duplicate_result.strategy_definitions == ()

    failed_pipeline = StrategyEvolutionPipeline(
        repository=InMemoryTradingRepository(),
        prompt_registry=registry,
        model_name="gpt-5",
        agent_runner=lambda prompt, model_name: {"content": "not-json"},
    )

    failed_result = failed_pipeline.run(request=_request())

    assert failed_result.strategy_proposals[0].proposal_status == "proposal_failed"
    assert failed_result.strategy_proposals[0].source_daily_reflection_id == "reflection-1"
    assert failed_result.strategy_definitions == ()
