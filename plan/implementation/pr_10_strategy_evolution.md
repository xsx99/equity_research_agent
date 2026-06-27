# Implementation Module PR 10: Strategy Evolution

## PR 10: Strategy Evolution + Dynamic Strategy Catalog

**Goal:** Let the system summarize repeated learning into new strategy proposals and add validated candidates to the strategy list without being limited to the initial seed strategies.

**Files:**
- Create: `src/trading/strategy_evolution.py`
- Modify: `src/trading/repository.py`
- Modify: `src/db/models/trading.py`
- Add Alembic migration for `strategy_proposals` and `strategy_evaluation_results`
- Test: `tests/trading/test_strategy_evolution.py`
- Test: `tests/trading/test_strategy_lifecycle.py`

Implementation notes:

- Consume reflection `strategy_proposal_hints`, candidate/observation learning factors, rejected candidate evidence, and historical replay/outcome performance summaries.
- Load strategy proposal synthesis prompts through `PromptRegistry` and persist prompt run/usage records.
- Validate proposal synthesis output with Pydantic, retry once on validation failure, and persist `proposal_failed` without creating definitions when validation still fails.
- Generate `StrategyProposal` records with proposed `strategy_id`, display name, thesis, required/optional signals, horizon, scoring rules, risk tags, invalidators, and evidence summary.
- Detect duplicates against existing strategy definitions by overlap in required signals, horizon, thesis, and risk tags.
- Create new `StrategyDefinition` rows only in `candidate` or `shadow` lifecycle status.
- Shadow strategies can be scored during scans but cannot create paper orders.
- Experimental strategies can create paper orders only with small capped budget and stricter risk limits.
- Persist every lifecycle transition and promotion/rejection reason.

Stop after PR 10 for review/merge.

---

