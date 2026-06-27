from __future__ import annotations


def test_option_strategy_builder_split_modules_exist_and_export_representative_helpers():
    from src.trading.workflows.option_strategy_builder_chain import _select_option_chain_legs
    from src.trading.workflows.option_strategy_builder_evidence import (
        _WINDOWED_EVENT_NEWS_FIELDS,
        _news_evidence_limit,
    )
    from src.trading.workflows.option_strategy_builder_payload import _build_option_strategy_payload
    from src.trading.workflows.option_strategy_builder_policy import (
        _classification_instrument_type,
        _decision_action_for_expression,
        _resolve_expression_fallback_plan,
    )

    assert callable(_classification_instrument_type)
    assert callable(_decision_action_for_expression)
    assert callable(_resolve_expression_fallback_plan)
    assert callable(_select_option_chain_legs)
    assert callable(_build_option_strategy_payload)
    assert isinstance(_WINDOWED_EVENT_NEWS_FIELDS, tuple)
    assert callable(_news_evidence_limit)


def test_repository_base_split_modules_exist_and_export_representative_helpers():
    from src.trading.repositories._base import _RepositoryBase
    from src.trading.repositories._base_common import _decimal_or_none, _to_uuid
    from src.trading.repositories._base_manual_review import _manual_review_execution_path_state
    from src.trading.repositories._base_payloads import _portfolio_snapshot_payload
    from src.trading.repositories._base_records import (
        _latest_portfolio_risk_snapshot_id,
        _macro_snapshot_record,
    )

    assert _RepositoryBase is not None
    assert callable(_to_uuid)
    assert callable(_decimal_or_none)
    assert callable(_manual_review_execution_path_state)
    assert callable(_portfolio_snapshot_payload)
    assert callable(_macro_snapshot_record)
    assert callable(_latest_portfolio_risk_snapshot_id)


def test_compatibility_hubs_still_reexport_runtime_import_surfaces():
    from src.trading.repositories._base import (
        _RepositoryBase,
        _decimal_or_none,
        _latest_portfolio_risk_snapshot_id,
        _macro_snapshot_record,
        _manual_review_execution_path_state,
        _portfolio_snapshot_payload,
        _to_uuid,
    )
    from src.trading.workflows.option_strategy_builder import (
        _WINDOWED_EVENT_NEWS_FIELDS,
        _build_option_strategy_payload,
        _build_option_strategy_payloads,
        _classification_instrument_type,
        _decision_action_for_expression,
        _evidence_priority,
        _news_evidence_limit,
        _resolve_expression_fallback_plan,
        _round_nested_floats,
    )

    assert _RepositoryBase is not None
    assert callable(_to_uuid)
    assert callable(_decimal_or_none)
    assert callable(_manual_review_execution_path_state)
    assert callable(_portfolio_snapshot_payload)
    assert callable(_macro_snapshot_record)
    assert callable(_latest_portfolio_risk_snapshot_id)
    assert callable(_build_option_strategy_payload)
    assert callable(_build_option_strategy_payloads)
    assert callable(_classification_instrument_type)
    assert callable(_decision_action_for_expression)
    assert callable(_resolve_expression_fallback_plan)
    assert callable(_news_evidence_limit)
    assert callable(_evidence_priority)
    assert callable(_round_nested_floats)
    assert isinstance(_WINDOWED_EVENT_NEWS_FIELDS, tuple)


def test_split_keeps_runtime_import_smoke_clean():
    import src.trading.repositories.sqlalchemy as sqlalchemy_repository
    import src.trading.runtime.preopen_risk as preopen_risk
    import src.trading.workflows.trading_decision as trading_decision

    assert sqlalchemy_repository is not None
    assert preopen_risk is not None
    assert trading_decision is not None
