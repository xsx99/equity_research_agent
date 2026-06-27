# Implementation Module PR 9: Reflection and Learning Factors

## PR 9: Reflection + Learning Factors

**Goal:** Add post-close reflection using the highest-quality configured model and persist learning factors plus strategy proposal hints.

**Files:**
- Create: `src/agents/reflection.py`
- Create: `src/agents/reflection_schemas.py`
- Create: `src/trading/reflection_pipeline.py`
- Modify: `src/core/config.py`
- Add ORM models/migration for `daily_reflections`, `learning_factors`, `learning_factor_applications`
- Test: `tests/agents/test_reflection_agent.py`
- Test: `tests/trading/test_reflection_pipeline.py`
- Test: `tests/trading/test_learning_factors.py`

Implementation notes:

- Add `REFLECTION_MODEL_NAME`; production should warn if absent.
- Load reflection prompts through `PromptRegistry`; no inline prompt strings.
- Persist prompt run and usage records for reflection, including raw output, parsed output, Pydantic validation errors, retry count, and fallback status. Reflection failure must not mutate learning factors.
- Reflection input includes portfolio outcome, candidates, manual ticker requests, accepted/rejected trades, intraday news alerts, intraday rebalance decisions, risk snapshots, factor concentration, historical replay/outcome evaluator rows, benchmark/peer-basket returns, paper option decisions, worst-case assignment snapshots, and learning factors used.
- Attribute trades from `candidate_outcome_evaluations` against benchmarks and decision-time peer baskets over each selected strategy's configured holding horizon. Daily reflection should record interim mark-to-market for open trades and final horizon outcome when the trade closes or the intended horizon expires.
- Analyze bullish catalyst trades separately from bearish/risk-off calls.
- Evaluate confidence calibration by strategy, expression bucket, trade identity, direction, catalyst type, sector/theme, and market regime.
- Evaluate whether `catalyst_watch` would have been more useful than ordinary neutral/watch.
- Evaluate whether user-pinned tickers exposed scanner misses or mostly confirmed no-trade discipline.
- Learning factors start as `candidate`, `observation`, `shadow`, `active`, `suppressed`, or `retired`.
- New learning factors default to `candidate` or `observation`.
- Risk-tightening factors may become `active` automatically only when they reduce exposure, add required confirmation, block stale-data scenarios, lower confidence, or tighten exit rules.
- Any factor that increases score, expands eligibility, increases size, weakens hard safety rails, broadens universe filters, or increases risk budget must remain candidate/shadow/test and should become a strategy/config proposal if it needs behavior changes.
- Reflection may emit `strategy_proposal_hints`, but PR 9 should not add them to the strategy catalog directly.

Stop after PR 9 for review/merge.

---

