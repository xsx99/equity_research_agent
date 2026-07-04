from __future__ import annotations


def test_strategy_policy_moves_to_strategy_capability_with_old_path_shim():
    import src.trading.post_close.strategy_policy as post_close_policy
    import src.trading.strategies.policy as canonical_policy

    assert (
        canonical_policy.experimental_strategy_weight_cap
        is post_close_policy.experimental_strategy_weight_cap
    )


def test_reflection_phase_exports_and_old_paths_preserve_identity():
    import src.trading.phases.reflection as canonical_reflection
    import src.trading.phases.reflection.pipeline as canonical_pipeline
    import src.trading.runtime.reflection as runtime_reflection
    import src.trading.post_close.reflection as post_close_reflection

    assert (
        canonical_reflection.run_reflection_once
        is runtime_reflection.run_reflection_once
    )
    assert (
        canonical_reflection.run_live_reflection_once
        is runtime_reflection.run_live_reflection_once
    )
    assert (
        canonical_reflection.LiveReflectionRuntime
        is runtime_reflection.LiveReflectionRuntime
    )
    assert (
        canonical_pipeline.ReflectionPipeline
        is post_close_reflection.ReflectionPipeline
    )
    assert (
        canonical_pipeline.DailyReflectionRecord
        is post_close_reflection.DailyReflectionRecord
    )
    assert (
        canonical_pipeline.LearningFactorRecord
        is post_close_reflection.LearningFactorRecord
    )


def test_strategy_evolution_phase_exports_and_old_paths_preserve_identity():
    import src.trading.phases.strategy_evolution as canonical_strategy_evolution
    import src.trading.phases.strategy_evolution.pipeline as canonical_pipeline
    import src.trading.runtime.strategy_evolution as runtime_strategy_evolution
    import src.trading.post_close.strategy_evolution as post_close_strategy_evolution

    assert (
        canonical_strategy_evolution.run_strategy_evolution_once
        is runtime_strategy_evolution.run_strategy_evolution_once
    )
    assert (
        canonical_strategy_evolution.run_live_strategy_evolution_once
        is runtime_strategy_evolution.run_live_strategy_evolution_once
    )
    assert (
        canonical_strategy_evolution.LiveStrategyEvolutionRuntime
        is runtime_strategy_evolution.LiveStrategyEvolutionRuntime
    )
    assert (
        canonical_pipeline.StrategyEvolutionPipeline
        is post_close_strategy_evolution.StrategyEvolutionPipeline
    )
    assert (
        canonical_pipeline.StrategyProposalRecord
        is post_close_strategy_evolution.StrategyProposalRecord
    )
    assert (
        canonical_pipeline.StrategyEvaluationResultRecord
        is post_close_strategy_evolution.StrategyEvaluationResultRecord
    )


def test_replay_phase_exports_and_old_paths_preserve_identity():
    import src.trading.phases.replay as canonical_replay
    import src.trading.phases.replay.historical as canonical_historical
    import src.trading.phases.replay.outcomes as canonical_outcomes
    import src.trading.replay.historical as replay_historical
    import src.trading.replay.outcomes as replay_outcomes

    assert (
        canonical_replay.HistoricalReplayRunner
        is canonical_historical.HistoricalReplayRunner
    )
    assert (
        canonical_historical.HistoricalReplayRunner
        is replay_historical.HistoricalReplayRunner
    )
    assert canonical_outcomes.OutcomeEvaluator is replay_outcomes.OutcomeEvaluator
    assert canonical_outcomes.PricePoint is replay_outcomes.PricePoint
    assert (
        canonical_outcomes.CandidateOutcomeEvaluationRecord
        is replay_outcomes.CandidateOutcomeEvaluationRecord
    )


def test_shell_exports_and_runtime_facade_preserve_identity():
    import src.trading.phases._shell.dispatch as canonical_dispatch
    import src.trading.phases._shell.facade as canonical_facade
    import src.trading.phases._shell.smoke as canonical_smoke
    import src.trading.runtime as runtime
    import src.trading.runtime.dispatch as runtime_dispatch
    import src.trading.runtime.facade as runtime_facade
    import src.trading.runtime.smoke as runtime_smoke

    from src.trading.runtime import (
        AVAILABLE_SMOKE_MODES,
        TRADING_JOB_PHASES,
        run_job_phase,
        run_smoke_mode,
    )

    assert canonical_facade.TRADING_JOB_PHASES is runtime_facade.TRADING_JOB_PHASES
    assert canonical_facade.run_job_phase is runtime_facade.run_job_phase
    assert canonical_facade.run_smoke_mode is runtime_facade.run_smoke_mode
    assert canonical_dispatch.get_job_phase_handler is runtime_dispatch.get_job_phase_handler
    assert canonical_smoke.AVAILABLE_SMOKE_MODES is runtime_smoke.AVAILABLE_SMOKE_MODES
    assert TRADING_JOB_PHASES is canonical_facade.TRADING_JOB_PHASES
    assert AVAILABLE_SMOKE_MODES is canonical_smoke.AVAILABLE_SMOKE_MODES
    assert run_job_phase is canonical_facade.run_job_phase
    assert run_smoke_mode is canonical_facade.run_smoke_mode
    assert runtime.TRADING_JOB_PHASES is canonical_facade.TRADING_JOB_PHASES
    assert runtime.AVAILABLE_SMOKE_MODES is canonical_smoke.AVAILABLE_SMOKE_MODES


def test_pr43_import_smoke_for_entrypoints_phases_and_repository_layer():
    import src.scheduler.jobs.strategy_evolution_job as strategy_evolution_job
    import src.scheduler.jobs.trading_reflection_job as reflection_job
    import src.trading.phases._shell.smoke_entrypoints as smoke_entrypoints
    import src.trading.phases._shell.smoke_fixture_modes as smoke_fixture_modes
    import src.trading.phases._shell.smoke_post_close_modes as smoke_post_close_modes
    import src.trading.phases._shell.smoke_support as smoke_support
    import src.trading.phases.reflection as reflection
    import src.trading.phases.replay as replay
    import src.trading.phases.strategy_evolution as strategy_evolution
    import src.trading.repositories.in_memory as in_memory
    import src.trading.repositories.sqlalchemy as sqlalchemy

    assert reflection_job is not None
    assert strategy_evolution_job is not None
    assert smoke_entrypoints is not None
    assert smoke_fixture_modes is not None
    assert smoke_post_close_modes is not None
    assert smoke_support is not None
    assert reflection is not None
    assert strategy_evolution is not None
    assert replay is not None
    assert in_memory is not None
    assert sqlalchemy is not None
