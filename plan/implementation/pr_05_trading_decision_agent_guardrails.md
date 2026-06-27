# Implementation Module PR 5: Trading Decision Agent Guardrails

## PR 5: Trading Decision Agent Guardrails

**Goal:** Add bounded trading-agent decisions after candidate scoring and risk context, with Pydantic validation, retry, safe fallback, and full prompt/schema persistence. No paper orders or portfolio mutation yet.

**Files:**
- Create: `src/agents/trading.py`
- Create: `src/agents/trading_schemas.py`
- Modify: `src/core/config.py`
- Modify: `src/trading/pipeline.py`
- Add ORM models/migration for `trading_decisions`
- Test: `tests/agents/test_trading_agent.py`
- Test: `tests/agents/test_trading_schemas.py`
- Test: `tests/trading/test_trading_decision_repository.py`

Implementation notes:

- Use `TRADING_MODEL_NAME` defaulting to `DEFAULT_FAST_MODEL_NAME`.
- Load trading prompts through `PromptRegistry`; no inline prompt strings.
- Define Pydantic schemas for every trading-agent output, including explicit `decision`, `trade_identity`, `strategy_id`, `expression_bucket_id`, `instrument_type`, confidence fields, thesis, invalidators, and fallback metadata.
- Validate every LLM response through Pydantic before persisting parsed decisions.
- Retry once with the validation error and compact repair prompt when parsing or validation fails.
- If retry fails, persist raw output, validation error, retry count, and fallback `no_trade` for new exposure or `hold` for existing positions.
- Persist `LlmPromptTemplate`, `LlmPromptRun`, and `LlmUsageEvent` records for every trading-agent call, including rendered prompt hash/redacted prompt, input context, raw output, parsed output, validation errors, fallback action, prompt/schema version, model, token usage, cost, latency, retries, and errors.
- Persist the full decision context snapshot, including trade identity, expression bucket, benchmark/peer context, historical replay outcome references, confidence basis, source availability metadata, `selection_source`, and `manual_request_id`.
- Enforce long-only common-stock decisions in V2. Bearish evidence may reduce/reject/downgrade, but direct short-stock decisions should be downgraded before later paper order creation.
- Enforce manual request mode: `review_only` can produce an actionable explanation but must never authorize a later paper order; `paper_trade_eligible` can proceed only after normal risk approval.
- Update linked manual request `result_status` to `actionable_trade`, `blocked_by_risk`, `no_trade`, `catalyst_watch`, or `ordinary_watch`.
- Do not create paper orders in PR 5. Persist proposed decisions and safe fallbacks only.

Stop after PR 5 for review/merge.

---

