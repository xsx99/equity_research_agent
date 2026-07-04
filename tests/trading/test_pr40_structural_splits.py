from __future__ import annotations


def test_decision_package_exports_pipeline_and_option_builder_surfaces():
    from src.trading.decision import (
        TradingDecisionPipeline,
        TradingDecisionPipelineResult,
        TradingDecisionRecord,
    )
    from src.trading.decision.option_strategy_builder import (
        _WINDOWED_EVENT_NEWS_FIELDS,
        _build_option_strategy_payload,
        _build_option_strategy_payloads,
        _classification_instrument_type,
        _decision_action_for_expression,
        _evidence_priority,
        _news_evidence_limit,
        _resolve_expression_fallback_plan,
        _round_nested_floats,
        _select_option_chain_legs,
    )
    from src.trading.decision.option_strategy_builder.chain import _select_option_chain_legs
    from src.trading.decision.option_strategy_builder.evidence import (
        _WINDOWED_EVENT_NEWS_FIELDS,
        _news_evidence_limit,
    )
    from src.trading.decision.option_strategy_builder.payload import (
        _build_option_strategy_payload,
    )
    from src.trading.decision.option_strategy_builder.policy import (
        _decision_action_for_expression,
    )
    from src.trading.decision.pipeline import (
        TradingDecisionPipeline as PipelineFromModule,
    )

    assert PipelineFromModule is TradingDecisionPipeline
    assert TradingDecisionPipelineResult is not None
    assert TradingDecisionRecord is not None
    assert callable(_build_option_strategy_payload)
    assert callable(_build_option_strategy_payloads)
    assert callable(_decision_action_for_expression)
    assert callable(_resolve_expression_fallback_plan)
    assert callable(_classification_instrument_type)
    assert callable(_select_option_chain_legs)
    assert isinstance(_WINDOWED_EVENT_NEWS_FIELDS, tuple)
    assert callable(_news_evidence_limit)
    assert callable(_evidence_priority)
    assert callable(_round_nested_floats)


def test_workflow_shims_preserve_decision_and_builder_identity():
    import src.trading.decision.pipeline as decision_pipeline
    import src.trading.workflows.option_strategy_builder as workflow_builder
    import src.trading.workflows.trading_decision as workflow_decision
    from src.trading.workflows.option_strategy_builder import (
        _build_option_strategy_payload,
        _build_option_strategy_payloads,
        _decision_action_for_expression,
    )
    from src.trading.workflows.trading_decision import (
        TradingDecisionPipeline,
        TradingDecisionPipelineResult,
        TradingDecisionRecord,
        _build_option_strategy_payloads as decision_payloads,
    )

    assert callable(_build_option_strategy_payload)
    assert callable(_build_option_strategy_payloads)
    assert callable(_decision_action_for_expression)
    assert TradingDecisionPipelineResult is decision_pipeline.TradingDecisionPipelineResult
    assert TradingDecisionRecord is decision_pipeline.TradingDecisionRecord
    assert TradingDecisionPipeline is decision_pipeline.TradingDecisionPipeline
    assert decision_payloads is workflow_builder._build_option_strategy_payloads
    assert (
        workflow_decision._build_option_strategy_payloads
        is workflow_builder._build_option_strategy_payloads
    )


def test_pr40_import_smoke_for_runtime_and_repository_entrypoints():
    import src.trading.repositories.sqlalchemy as sqlalchemy_repository
    import src.trading.runtime.preopen_dependencies as preopen_dependencies
    import src.trading.runtime.preopen_risk as preopen_risk
    import src.trading.workflows.paper_execution as paper_execution

    assert sqlalchemy_repository is not None
    assert preopen_dependencies is not None
    assert preopen_risk is not None
    assert paper_execution is not None
