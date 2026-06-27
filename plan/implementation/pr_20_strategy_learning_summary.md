# Prompt 06 — Write a human-readable learning summary per strategy

You are editing the equity_research_agent repo. Make ONLY the changes described. Run
the matching tests.

## Goal
The strategy learning view (System tab) currently dumps raw tables and `win_rate` is
not even populated. Produce a human-readable "learning summary" for each strategy
plus a top-of-section overview paragraph.

## Context (verified facts)
- Presenter `src/web/presenters/today_learning_strategies.py` returns raw rows; there
  is NO narrative/summary field anywhere.
- `_load_strategy_performance` in `src/web/routers/today.py` (~lines 610-625) sets
  `"win_rate": None` — never computed, though `CandidateOutcomeEvaluation.alpha` is
  available per row.
- `LearningFactor` rows carry `title`, `condition`, `recommendation`, `confidence`,
  `effect_tags_json`, `scope`, `strategy_id` — the material for a narrative.
- Template `src/templates/today.html:1069-1127` renders raw tables only.

## Changes
1. **Populate `win_rate`** in `_load_strategy_performance` (`src/web/routers/today.py`):
   for each strategy group, compute
   `win_rate = (# evaluations with alpha > 0) / (total evaluations with non-null alpha)`,
   expressed as a percentage (one decimal). Keep `total_pnl` as is.
2. **Synthesize summaries** in `src/web/presenters/today_learning_strategies.py`: add
   `_synthesize_strategy_summary(perf_row, learning_factors)` returning one readable
   sentence per strategy combining lifecycle status, win_rate, total_pnl, and the
   highest-confidence active `LearningFactor` scoped to that `strategy_id` (its
   `title` + `recommendation` + `confidence`). Example:
   > "earnings_drift_v1 — active, 62.0% win rate (+$3,240 total P&L). Latest learning:
   > post-earnings volatility mean-reversion (confidence 0.78); recommendation:
   > increase put-spread allocation in elevated-vol regimes."
   Attach `learning_summary` to each `strategy_performance` row in the returned
   payload. Also add a top-level `learning_summary_text` paragraph summarizing the day
   (how many strategies active, top performer, key new learning). If a strategy has no
   learning factor, produce a performance-only sentence — never an empty string.
3. **Render** in `src/templates/today.html` (System tab, ~lines 1069-1095): show
   `learning_summary_text` as an intro paragraph above the Strategy Performance table,
   and add the per-strategy `learning_summary` (new column or a sentence under each
   row). Keep it prose, not a table of raw numbers.

## Acceptance criteria
- Each strategy shows a readable summary sentence; `win_rate` is a real percentage,
  not blank.
- A top-of-section paragraph summarizes the day's learning.
- Add a test asserting `learning_summary` is non-empty for a strategy with
  performance data. `pytest tests/web/ -q` passes.
