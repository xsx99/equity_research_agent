# Implementation Module PR 8: Intraday Refresh and Rebalance

## PR 8: Intraday Signal Refresh + News Alerts + Rebalance

**Goal:** Refresh intraday signals and news hourly during regular trading hours using the pre-open baseline snapshot, source freshness gates, and targeted source refreshes, then trigger risk-gated intraday rebalance actions for material signal changes or high-impact positive/negative events.

**Files:**
- Create: `src/trading/intraday_signals.py`
- Create: `src/trading/news_alerts.py`
- Create: `src/trading/intraday_rebalance.py`
- Modify: `src/trading/repository.py`
- Modify: `src/agents/trading_schemas.py` if rebalance decisions share trading-agent schema
- Modify: `src/core/config.py`
- Add ORM models/migration for `intraday_signal_scans`, `intraday_signal_snapshots`, `news_alerts`, `intraday_rebalance_decisions`
- Test: `tests/trading/test_intraday_signals.py`
- Test: `tests/trading/test_news_alerts.py`
- Test: `tests/trading/test_intraday_rebalance.py`
- Test: `tests/trading/test_news_alert_repository.py`

Implementation notes:

- Scan scope starts with open stock positions, paper option positions, same-day trades, staged orders, top morning candidates, active manual/pinned review tickers, and high-impact market/sector news.
- Refresh intraday price/volume/liquidity signals, VWAP/opening-range/gap signals, relative strength vs benchmarks/peers, option marks, per-leg Greeks, max-loss/margin/buying-power changes, assignment-risk deltas when relevant, news/event signals, target-company earnings release/transcript/guidance updates, peer/sector-leader earnings read-through updates, and freshness checks for low-frequency insider/SEC/fundamental/event sources.
- Persist intraday signal snapshots with deltas vs the morning snapshot and previous hourly snapshot.
- Define material-change thresholds that can trigger rebalance even without a new headline.
- Load the pre-open baseline `signal_snapshot_id` and previous hourly snapshot for every ticker in the intraday scope.
- Before building each intraday snapshot, compute a freshness plan by source family and ticker/event scope. Run inline required refreshes for price/volume, intraday relative strength, scoped news/events, and open option marks; run targeted refreshes for SEC filings, own earnings transcripts, or peer read-through only when relevant.
- Do not rerun the full universe scan or full source-ingestion set during hourly refresh. Carry forward low-frequency baseline fields when they remain inside freshness SLA and mark them as `carried_forward_from_baseline`.
- Persist intraday snapshot fields for `baseline_signal_snapshot_id`, `previous_intraday_snapshot_id`, `refreshed_signals_json`, `carried_forward_signals_json`, `delta_vs_baseline_json`, `delta_vs_previous_json`, and `source_freshness_json`.
- Block or downgrade actions when required source freshness is insufficient: no new add when high-frequency price/news is stale, no option open/roll when option data is stale/missing, and no high-confidence bearish action when direct-negative-catalyst checks are missing.
- Use deterministic dedupe keys so repeated headlines do not trigger repeated rebalances.
- Load intraday classification/rebalance prompts through `PromptRegistry` and persist prompt run/usage records for every LLM call.
- Validate intraday classification and rebalance JSON with Pydantic, retry once on validation failure, and fall back to `classification_failed` or `hold` unless deterministic hard-risk rails require reduce/exit.
- Normalize alert fields: ticker or source ticker, event type, sentiment, severity, source, published time, summary, strategy relevance, affected positions/candidates/themes, read-through relationship when applicable, and action-required flag.
- Severity levels are `critical`, `high`, `medium`, `low`.
- Critical/high alerts can propose `hold`, `reduce`, `exit`, `add`, `close_option_strategy`, `roll_option_strategy`, `adjust_option_strategy`, or `avoid_event_option` for whitelisted paper option strategies.
- `open_new` is disabled by default unless the ticker was already a morning candidate or manual override.
- Every proposed action must pass `PositionSizer`, `RiskManager`, and the relevant paper broker.
- Persist no-action and rejected signal/news triggers so post-close reflection can evaluate missed or noisy signals.

Stop after PR 8 for review/merge.

---

