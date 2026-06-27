# PR 34 Residual Helper Hub Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lower the remaining local reasoning cost in `option_strategy_builder.py` and `repositories/_base.py` by splitting unrelated helper clusters into focused sibling modules while preserving all current behavior and import paths.

**Architecture:** Keep both original modules as thin compatibility hubs. Move helper families into sibling files grouped by reasoning concern, re-export them through the original module, and add structural regression tests that lock the compatibility contract. No business logic, repository query behavior, or workflow behavior changes are in scope.

**Tech Stack:** Python, pytest, existing SQLAlchemy repository mixins, existing trading workflow modules.

---

## Required Pre-Read

1. `documents/general_instructions.md`
2. `plan/module_contracts.md`
3. `plan/design/2026-06-26-residual-helper-hub-split.md`
4. `plan/implementation/PR_32_refactor-split-god-files.md`
5. `plan/implementation/PR_33_refactor-split-god-files-round2.md`
6. `plan/progress_tracker.md` Recent section only

## Guardrails

- Pure structural refactor only. Move code verbatim unless a tiny import-fix is required to keep the
  same behavior.
- Do not change public or semi-private import paths currently used by runtime code or tests.
- Do not change repository mixin call sites unless verification proves a name must be imported back
  differently.
- Do not combine this slice with query cleanup, dead-code deletion, naming cleanup, or doc-driven
  behavior changes.

## File Map

- Create: `src/trading/workflows/option_strategy_builder_policy.py`
- Create: `src/trading/workflows/option_strategy_builder_chain.py`
- Create: `src/trading/workflows/option_strategy_builder_payload.py`
- Create: `src/trading/workflows/option_strategy_builder_evidence.py`
- Modify: `src/trading/workflows/option_strategy_builder.py`
- Create: `src/trading/repositories/_base_common.py`
- Create: `src/trading/repositories/_base_manual_review.py`
- Create: `src/trading/repositories/_base_payloads.py`
- Create: `src/trading/repositories/_base_records.py`
- Modify: `src/trading/repositories/_base.py`
- Create: `tests/trading/test_pr34_structural_splits.py`
- Modify: `documents/repo_overview.md` if the file exists; otherwise create it only if this slice is
  treated as a major refactor per `documents/general_instructions.md`
- Modify: `plan/progress_tracker.md`

## Task 1: Lock The Compatibility Surface First

**Files:**

- Create: `tests/trading/test_pr34_structural_splits.py`
- Test: `tests/trading/test_pr32_structural_splits.py`

- [ ] Step 1: Write a failing structural test that imports these names from `src.trading.workflows.option_strategy_builder`:
  `_build_option_strategy_payload`, `_build_option_strategy_payloads`,
  `_decision_action_for_expression`, `_classification_instrument_type`,
  `_resolve_expression_fallback_plan`, `_WINDOWED_EVENT_NEWS_FIELDS`,
  `_news_evidence_limit`, `_evidence_priority`, `_round_nested_floats`.

- [ ] Step 2: In the same test file, write a failing structural test that imports these names from
  `src.trading.repositories._base`:
  `_RepositoryBase`, `_to_uuid`, `_decimal_or_none`, `_manual_review_execution_path_state`,
  `_portfolio_snapshot_payload`, `_macro_snapshot_record`, `_latest_portfolio_risk_snapshot_id`.

- [ ] Step 3: Add one import-smoke test that imports `src.trading.repositories.sqlalchemy`,
  `src.trading.runtime.preopen_risk`, and `src.trading.workflows.trading_decision`.

- [ ] Step 4: Run:
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr34_structural_splits.py tests/trading/test_pr32_structural_splits.py -q`

Expected result: the new test file exists and fails only because the post-split compatibility
surface is not implemented yet.

## Task 2: Split `option_strategy_builder.py` Into Focused Helper Modules

**Files:**

- Create: `src/trading/workflows/option_strategy_builder_policy.py`
- Create: `src/trading/workflows/option_strategy_builder_chain.py`
- Create: `src/trading/workflows/option_strategy_builder_payload.py`
- Create: `src/trading/workflows/option_strategy_builder_evidence.py`
- Modify: `src/trading/workflows/option_strategy_builder.py`
- Test: `tests/trading/test_pr34_structural_splits.py`
- Test: `tests/trading/test_pr32_structural_splits.py`
- Test: `tests/trading/test_runtime_live.py`

- [ ] Step 1: Re-run `grep -nE '^(def |class )' src/trading/workflows/option_strategy_builder.py`
  and confirm the live function list still matches the design split before editing.

- [ ] Step 2: Move the policy/fallback helpers into
  `src/trading/workflows/option_strategy_builder_policy.py`:
  `_classification_instrument_type`, `_resolve_expression_fallback_plan`,
  `_instrument_type_for_expression_definition`, `_instrument_type_from_trade_identity`,
  `_decision_action_for_expression`, `_choose_option_strategy_type`,
  `_apply_expression_policy_to_option_payload`, `_expression_earnings_policy`,
  `_expression_option_policy`, `_expression_requires_implied_volatility`,
  `_option_days_to_expiry`, `_option_profit_target_pct`, `_event_through_expiry`,
  `_option_max_loss_rule`, `_option_roll_conditions`, `_option_close_conditions`,
  `_option_strategy_pairing_method`, `_option_assignment_plan`.

- [ ] Step 3: Move the leg/chain helpers into
  `src/trading/workflows/option_strategy_builder_chain.py`:
  `_infer_option_underlying_price`, `_build_option_leg_definitions`, `_policy_float`,
  `_select_option_chain_legs`, `_option_iv_context`, `_flatten_option_chain_contracts`,
  `_is_viable_option_chain_contract`, `_option_chain_contract_score`,
  `_option_leg_from_chain_contract`, `_contract_expiry`.

- [ ] Step 4: Move the payload orchestration helpers into
  `src/trading/workflows/option_strategy_builder_payload.py`:
  `_build_option_strategy_payloads`, `_build_option_strategy_payload`,
  `_reject_option_payload`, `_serialize_option_strategy_payload`.

- [ ] Step 5: Move the evidence/support helpers into
  `src/trading/workflows/option_strategy_builder_evidence.py`:
  `_render_news_source_text`, `_WINDOWED_EVENT_NEWS_FIELDS`,
  `_EVIDENCE_IMPORTANCE_PRIORITY`, `_news_evidence_limit`, `_evidence_priority`,
  `_round_nested_floats`.

- [ ] Step 6: Rewrite `src/trading/workflows/option_strategy_builder.py` as the compatibility hub:
  keep the module docstring and `from __future__ import annotations`, import the moved names back
  from the new sibling modules, and expose them through one stable module namespace.

- [ ] Step 7: Run:
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr34_structural_splits.py tests/trading/test_pr32_structural_splits.py tests/trading/test_runtime_live.py -q`

Expected result: runtime callers and structural tests keep importing from
`src.trading.workflows.option_strategy_builder`, but readers can inspect policy, chain, payload, and
evidence concerns independently.

## Task 3: Split `repositories/_base.py` While Keeping It As The Shared Import Hub

**Files:**

- Create: `src/trading/repositories/_base_common.py`
- Create: `src/trading/repositories/_base_manual_review.py`
- Create: `src/trading/repositories/_base_payloads.py`
- Create: `src/trading/repositories/_base_records.py`
- Modify: `src/trading/repositories/_base.py`
- Test: `tests/trading/test_pr34_structural_splits.py`
- Test: `tests/trading/test_sqlalchemy_repository_structure.py`
- Test: `tests/trading/test_sqlalchemy_repository.py`

- [ ] Step 1: Re-run `grep -nE '^(class |def )' src/trading/repositories/_base.py` and confirm the
  live function list before moving anything.

- [ ] Step 2: Move scalar/common helpers into `src/trading/repositories/_base_common.py`:
  `_to_uuid`, `_to_uuid_or_none`, `_decimal_or_none`, `_datetime_value`, `_decimal_to_float`,
  `_legacy_option_client_order_id`, `_format_option_contract_symbol`, `_latest_row_sort_key`,
  `_string_or_none`.

- [ ] Step 3: Move manual-review helpers into `src/trading/repositories/_base_manual_review.py`:
  `_manual_request_payload`, `_manual_review_execution_path_state`,
  `_manual_review_linkage_state`, `_manual_review_actionable_decision`,
  `_intraday_context_metadata`.

- [ ] Step 4: Move dict payload builders into `src/trading/repositories/_base_payloads.py`:
  `_portfolio_snapshot_payload`, `_portfolio_outcome_payload`, `_candidate_score_payload`,
  `_rejected_candidate_payload`, `_trading_decision_payload`, `_news_alert_payload`,
  `_intraday_rebalance_payload`, `_paper_order_payload`, `_paper_execution_payload`,
  `_portfolio_risk_snapshot_payload`, `_position_risk_action_payload`, `_hedge_action_payload`,
  `_risk_factor_exposure_payload`, `_candidate_outcome_payload`, `_paper_option_decision_payload`,
  `_paper_option_position_payload`, `_option_risk_snapshot_payload`,
  `_risk_hedge_overlay_payload`, `_hedge_effectiveness_payload`.

- [ ] Step 5: Move row-to-record and repository-only helpers into
  `src/trading/repositories/_base_records.py`:
  `_position_risk_action_record`, `_hedge_action_record`, `_macro_snapshot_record`,
  `_calendar_event_record`, `_portfolio_event_risk_assessment_record`,
  `_portfolio_risk_intent_record`, `_portfolio_event_risk_assessment_storage_key`,
  `_daily_reflection_record`, `_learning_factor_record`, `_candidate_outcome_record`,
  `_latest_portfolio_risk_snapshot_id`.

- [ ] Step 6: Keep `_RepositoryBase` and its `_to_event_news_item_record(...)` method in
  `src/trading/repositories/_base.py`, and rewrite the rest of `_base.py` as a compatibility hub
  that imports `*` from the new sibling modules and continues exporting one consolidated `__all__`.

- [ ] Step 7: Run:
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr34_structural_splits.py tests/trading/test_sqlalchemy_repository_structure.py tests/trading/test_sqlalchemy_repository.py -q`

Expected result: repository mixins continue importing from `_base.py` unchanged, but the helper
surface becomes readable in domain-sized files.

## Task 4: Full Slice Verification And Documentation

**Files:**

- Modify: `documents/repo_overview.md` when required
- Modify: `plan/progress_tracker.md`

- [ ] Step 1: Run `source ~/.venv/bin/activate && python -m compileall -q src`.

- [ ] Step 2: Run import smoke:
  `source ~/.venv/bin/activate && python -c "import src.trading.workflows.option_strategy_builder, src.trading.workflows.trading_decision, src.trading.runtime.preopen_risk, src.trading.repositories._base, src.trading.repositories.sqlalchemy"`

- [ ] Step 3: Run the focused regression suite:
  `source ~/.venv/bin/activate && pytest tests/trading/test_pr34_structural_splits.py tests/trading/test_pr32_structural_splits.py tests/trading/test_sqlalchemy_repository_structure.py tests/trading/test_sqlalchemy_repository.py tests/trading/test_runtime_live.py -q`

- [ ] Step 4: If the slice changed the architecture readers should know about, update
  `documents/repo_overview.md` with the new helper-module boundaries.

- [ ] Step 5: Prepend a dated entry to `plan/progress_tracker.md` summarizing the PR 34 split,
  touched files, and verification commands/results.

- [ ] Step 6: Run `git diff --check`.

Expected result: the structural split is documented, verified, and safe to hand off without any
behavioral delta.
