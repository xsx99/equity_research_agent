# PR 57 - Intraday Event Window And Reduce Rationale

## Goal

Fix the GH-shaped intraday close issue where a future earnings alert could be treated as an immediate own-event risk, forcing a tactical reduce while the saved decision thesis still described bullish evidence.

## Context

- `src/trading/risk/lookahead_risk.py` converted intraday own-event alerts to planner assessments with `days_until_event=0`, even when the alert headline or metadata contained a later earnings date.
- `src/trading/phases/intraday/rebalance.py` applied `force_reduce` / `reduce` portfolio risk intent overrides by changing only `action` and `target_weight`, leaving the LLM thesis/rationale unchanged.
- `/today?tab=trades` then displayed the final action as `Reduce` / `Closed` while the Evidence tab showed the stale bullish thesis from the overridden decision.

## Implementation

- [x] Add RED coverage for future earnings outside the 1-5 day lookahead window not forcing a reduce.
- [x] Add RED coverage for forced reduce decisions replacing the agent thesis/rationale with the lookahead risk reason.
- [x] Parse event dates from intraday alert metadata (`known_event_date`, `earnings_date`, `event_date`) and ISO dates in headline/summary text.
- [x] Preserve alert `metadata_json` when building rebalance request alert payloads.
- [x] Replace forced-reduce thesis/rationale with deterministic lookahead-risk copy.
- [x] Add a `/today?tab=trades` display fallback for already-persisted zero-weight reduce/exit rows with lookahead force-reduce audit fields, so deployed historical rows no longer show stale bullish Evidence copy.
- [x] Preserve the display-corrected Trade Plan thesis during selected-trade audit merge, so the audit detail row cannot reintroduce the old persisted bullish thesis.

## Verification

- `source ~/.venv/bin/activate && pytest tests/trading/test_intraday_rebalance.py::test_intraday_rebalance_pipeline_forces_reduce_from_portfolio_risk_intent tests/trading/test_runtime_intraday_live.py::test_intraday_helper_does_not_force_reduce_future_earnings_outside_lookahead_window -q`
- `source ~/.venv/bin/activate && pytest tests/trading/test_intraday_rebalance.py tests/trading/test_runtime_intraday_live.py -q`
- `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py::test_build_ticker_workspace_replaces_stale_bullish_thesis_for_forced_reduce -q`
- `source ~/.venv/bin/activate && pytest tests/web/test_today.py::TestTodayDashboard::test_merge_audit_detail_preserves_corrected_trade_plan_thesis -q`
- `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py tests/web/test_today.py -q`
- `source ~/.venv/bin/activate && pytest tests/web/test_today_workspace.py -q`
- `source ~/.venv/bin/activate && python -m compileall -q src`
- `git diff --check`
