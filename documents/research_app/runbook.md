# Research App Runbook

## Same-Day Iteration Semantics

- Scheduled research runs once per weekday at `9:20 ET`.
- Scheduled eval runs once per weekday at `16:10 ET`.
- Runtime `time_horizon` is fixed to `1d`; this is a same-day feedback window, not a required holding period.
- Pre-open runs use formal `open_to_close` eval.
- Post-open manual runs use quick `run_time_price_to_close` eval.
- Quick eval uses the persisted `research_runs.input_json.price_snapshot.last_price` as the ticker entry price. It is not reconstructed after the close.

## Manual Agent Run

### Local Smoke Test
```bash
source ~/.venv/bin/activate
python scripts/run_research_agent_once.py
```

This runs a single direct `ResearchAgent` call with a built-in sample payload and prints the validated output JSON. It does not write to Postgres.

### Custom Payload
Create a JSON file that matches the agent input schema, then run:

```bash
source ~/.venv/bin/activate
python scripts/run_research_agent_once.py --payload-file /absolute/path/to/payload.json
```

### Deployed Container
If the `scheduler` service is already running:

```bash
docker compose exec scheduler python scripts/run_research_agent_once.py
```

If you want an ad-hoc container instead:

```bash
docker compose run --rm scheduler python scripts/run_research_agent_once.py
```

## Notes
- The script uses `GOOGLE_API_KEY` from the environment or repo-root `.env`.
- Override the model with `--model-name` if needed.
- This is only a direct agent smoke path. The full batch research pipeline and DB persistence flow are still separate future work.
- The built-in sample payload now includes the richer research input shape used in production: fundamentals, volume context, `technical_signals`, filtered high-signal news metadata, insider-activity summary from the SEC Form 4 collector, plus the representative `global_context` block. `official_updates` remains in schema but is omitted by default until better relevance filters are in place.

## Manual Pipeline Run Order

To test the same-day workflow manually:

```bash
source ~/.venv/bin/activate
python scripts/run_research_once.py --ticker AAPL
python scripts/run_eval_once.py
```

- If the research run happened before `9:30 ET`, eval uses `open_to_close`.
- If the research run happened after `9:30 ET`, eval uses `run_time_price_to_close`.
- For post-open manual runs, confirm `price_snapshot.last_price` is present in the stored input JSON before trusting the quick-eval result.
- Single-ticker manual runs default to reusing the latest same-day `global_context` snapshot. Add `--refresh-global-context` when you explicitly want to fetch fresh macro/global inputs.

## Tool Smoke Test

### Local Live Tool Check
```bash
source ~/.venv/bin/activate
python scripts/run_tool_smoke_test.py --ticker AAPL
```

This runs the real tool registry against live dependencies:
- `get_market_snapshot` against Alpaca/Finnhub market data, including volume, valuation, and technical-signal fields
- `get_recent_news` against the configured news providers, including source/signal metadata after filtering
- `get_global_context` against the macro/global-context providers
- `marketaux_recent_news` as a dedicated direct Marketaux provider check when `MARKETAUX_API_KEY` is set
- all database-backed insider query tools against the live `insider_trades` table
- the repository-level `insider_activity` summary builder that powers research-run input snapshots

### External Tools Only
```bash
source ~/.venv/bin/activate
python scripts/run_tool_smoke_test.py --ticker AAPL --skip-db
```

### Deployed Container
```bash
docker compose exec scheduler python scripts/run_tool_smoke_test.py --ticker AAPL
```

### Failure Semantics
- Missing Alpaca credentials or unreachable market data will fail `get_market_snapshot`.
- Missing news provider credentials or zero returned headlines will fail `get_recent_news`.
- Missing FRED access or unreachable upstream pages can degrade `get_global_context`; the smoke check will fail if macro indicators or filtered geopolitical news come back empty.
- Missing `MARKETAUX_API_KEY` will skip `marketaux_recent_news`; a configured but failing/empty Marketaux response will fail it.
- Unreachable Postgres or an empty `insider_trades` table will fail the DB-backed tool checks unless `--skip-db` is set.

## Trading Scheduler Phases

All trading scheduler phases are defined in `America/New_York` and can be run ad hoc through one shared entrypoint:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_once.py --phase preopen --json
python scripts/run_trading_once.py --phase manual_review --json
python scripts/run_trading_once.py --phase intraday_refresh --json
python scripts/run_trading_once.py --phase reflection --json
python scripts/run_trading_once.py --phase strategy_evolution --json
```

The trading runtime now uses a split package structure: `src/trading/runtime/__init__.py` exposes the stable scheduler/CLI facade, `src/trading/runtime/preopen.py` owns the live preopen path, `src/trading/runtime/manual_review.py` owns the live manual-review path, `src/trading/runtime/intraday_refresh.py` owns the live intraday refresh path, `src/trading/runtime/reflection.py` owns the live post-close reflection path, `src/trading/runtime/strategy_evolution.py` owns the live strategy-evolution path, and fixture-only smoke helpers live under `src/trading/runtime/smoke.py`. Scheduler jobs and `scripts/run_trading_once.py` still keep the same phase strings and public entrypoint.

Signal-family notes for preopen and intraday:
- preopen snapshots now emit five deterministic families: `technical`, `fundamental`, `events_news`, `insider`, and `social_macro`
- intraday refresh targets `technical`, `events_news`, `social_macro`, and `option_chain`; `insider` is carried forward from the baseline unless a newer filing-backed source row is available
- legacy insider/Form 4 rows use a conservative point-in-time rule: `available_for_decision_at` is the later of row ingest time and the next market open after `filing_date`
- trading-side `social_macro` rows come from filtered global-context buckets (`trump_updates`, `official_updates`, `geopolitical_news`) and can tighten risk or trigger review, but they do not create unsupported macro-only single-name bearish trades on their own

Manual review keeps the scheduler/default path dry-run. Use the explicit operator mode when you want the same live manual-review runtime but with an intentional execution policy:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_once.py --mode live-manual-review --phase manual_review --json
python scripts/run_trading_once.py --mode live-manual-review --phase manual_review --execute-paper-orders --json
```

Operator notes:
- `--mode live-manual-review` is only valid with `--phase manual_review`
- omitting `--execute-paper-orders` keeps the run dry-run even in operator mode
- manual-review option execution is still out of scope; `--execute-paper-option-orders` is rejected for this mode
- after a live run, inspect `/today` manual-review rows for `last_evaluated_at`, `latest_signal_snapshot_id`, `latest_trading_decision_id`, `execution_path_state`, `latest_block_reason`, `latest_order_status`, and `latest_execution_status`

## Trading Smoke Test Modes

List the available standalone trading smoke modes:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_smoke_test.py --list-modes
```

Run one mode and print JSON:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_smoke_test.py --mode manual_review_fixture --json
```

PR 12 smoke modes:

- `provider_guardrail_fixture`: fixture-backed universe, source ingestion, and pre-open signal assembly without live API calls
- `universe_signal_db_write`: fixture-backed universe and signal snapshots with real Postgres persistence when the configured database is reachable
- `historical_replay_fixture`: point-in-time replay reconstruction plus outcome evaluation
- `paper_trade_dry_run`: workflow-driven paper-trade dry run using a fake broker
- `manual_review_fixture`: active `review_only` manual ticker request remains active and is re-evaluated
- `manual_review_execution_fixture`: fixture-backed `paper_trade_eligible` manual ticker request that submits one paper stock order
- `paper_option_fixture`: whitelisted paper option decision, leg derivation, and assignment-risk evaluation
- `paper_option_lifecycle_fixture`: end-to-end option open approval, assignment-risk rejection, and assignment-targeted hedge-overlay materialization
- `intraday_refresh_fixture`: hourly intraday signal delta plus deduped alert generation
- `reflection_fixture`: post-close reflection and learning-factor extraction
- `strategy_evolution_fixture`: strategy proposal generation from reflection fixtures

Executable manual-review smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_smoke_test.py --mode manual_review_execution_fixture --json
```

This should return:
- `summary.active_manual_requests=1`
- `summary.latest_result_status="actionable_trade"`
- `summary.orders_submitted=1`
- `summary.latest_order_status="filled"`

Signal-family smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_signal_family_smoke.py --ticker NVDA --fixture --json
```

This fixture-backed smoke seeds one ticker with deterministic `technical`, `fundamental`, `events_news`, `insider`, and `social_macro` rows, builds the resulting preopen snapshot, and prints the top candidate evidence for `insider_accumulation_momentum_v1`.

Live social-macro persistence-only smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_signal_family_smoke.py --ticker NVDA --live-social-macro --json
```

Use this opt-in path when you want one real global-context fetch and a persistence check for trading-side `social_macro` rows without generating any trading decisions or orders. A passing run should return:
- `source_records_by_family.social_macro >= 1`
- `social_macro_items_persisted >= 1`
- `orders_created = 0`

## Option Operator Checks

Live preopen stock order smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_live_preopen_order_smoke.py --ticker NVDA --instrument stock --json
```

This runs the real live preopen runtime with a scoped manual request and should return `runtime.execution.orders_submitted >= 1` plus a populated `order` payload when paper execution is enabled.

Live preopen option order smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_live_preopen_order_smoke.py --ticker QQQ --instrument option --json
```

This uses the same live preopen runtime but forces the smoke override onto the option expression path. A passing run should return `runtime.execution.option_orders_submitted >= 1` plus populated `option_order` and `option_execution` payloads.

The returned `option_order` JSON should now include:
- `client_order_id`
- `broker_order_id`

The returned `option_execution` JSON should now include:
- `broker_order_id`

When this live smoke path passes, verify the same identifiers are mirrored into the local DB rows:
- `paper_option_orders.client_order_id`
- `paper_option_orders.broker_order_id`
- `paper_option_executions.broker_order_id`

Standalone Alpaca option broker smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_option_paper_execution.py --ticker QQQ --contract-symbol <CURRENT_TRADABLE_CONTRACT_SYMBOL> --strategy-type long_call --limit-price 5 --strategy-id manual_option_execution_v1_smoke_$(date +%H%M%S) --json
```

Use this when you want a minimal broker-path check without running the full live preopen chain. Current assumptions:
- `ALPACA_API_KEY` plus `ALPACA_SECRET_KEY` or `ALPACA_API_SECRET` must be present
- `ALPACA_TRADING_BASE_URL` may be overridden, but the script defaults to Alpaca paper
- the target Alpaca paper account is already options-enabled; the repo does not manage approval flows
- use a currently tradable option contract symbol, not a stale historical example
- when rerunning the same smoke on the same trade date, pass a fresh `--strategy-id` so the deterministic `client_order_id` does not collide with the previous run
- for immediate fill verification, prefer a marketable `--limit-price` instead of the low default

A passing standalone run should return:
- `order.broker_order_id`
- `order.client_order_id`
- `execution.broker_order_id`
- `positions[0].metadata.broker_leg_refs`

This standalone script mirrors the option order, execution, and position artifacts inside the workflow result so you can inspect the same contract without waiting for the full scheduler-facing runtime. Use the live preopen option smoke above when you also need persisted Postgres rows for `paper_option_orders` and `paper_option_executions`.

After either smoke path, remember that option-event activities such as assignment, exercise, or expiry can reconcile later than the immediate order/position state. If a broker-side option position disappears before the local mirror closes, the next live portfolio sync is expected to reconcile it from broker state and then backfill the close reason when the relevant option activity becomes visible.

Preopen option approval smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_smoke_test.py --mode paper_option_fixture --json
```

## Macro/Event Backend Contract Smoke

Canonical risk-context DB smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_macro_event_db_smoke.py --json
```

This smoke does not call live providers. It runs migrations, writes one `macro_snapshots` row, two `calendar_events`, two `portfolio_event_risk_assessments`, a linked `portfolio_risk_snapshot`, `portfolio_risk_intent`, and supporting `risk_factor_exposures`, then reloads the same context through `SqlAlchemyTradingRepository` and the `/today` risk/macro presenter. Minimum requirement is `DATABASE_URL` pointing at the target Postgres database.

Expected success signals:
- `status=passed`
- `checks.macro_snapshot_reloaded=true`
- `checks.calendar_events_reloaded=true`
- `checks.event_assessments_reloaded=true`
- `checks.today_payload_uses_canonical_regime=true`
- `checks.today_payload_sees_event_risk=true`

FMP economic-calendar provider smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_fmp_economic_calendar_smoke.py --as-of 2026-07-03 --horizon-days 14
```

This smoke calls FMP only when `FMP_API_KEY` is configured; otherwise it returns `status=skipped` without making an external request.

FRED economic release-calendar provider smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_fred_economic_calendar_smoke.py --as-of 2026-07-03 --horizon-days 14
```

This smoke calls FRED only when `FRED_API_KEY` is configured; otherwise it returns `status=skipped` without making an external request. Live preopen uses the FRED release calendar first, then falls back to FMP if FRED returns no forward macro releases.

## Macro/Event Degraded Mode

- If macro fetch fails during live preopen or intraday refresh, `MacroSnapshotPipeline` persists a canonical `macro_snapshots` row with `regime=unavailable`, `risk_budget_multiplier=0.0`, `invalidators=["global_context_failed"]`, and blocked tactical tags. `/today` then shows an explicit macro availability issue instead of silently falling back to `unavailable` UI heuristics.
- If macro inputs are stale rather than fully missing, the canonical row remains persisted with `source_freshness.status=stale` and a reduced `risk_budget_multiplier`, so RiskManager and `/today` see the same degraded context.
- If company-news providers are unavailable, the runtime still persists deterministic earnings / option-expiry / macro rows when those inputs exist; the event-risk surface becomes narrower, but the backend contract stays auditable instead of disappearing into route-local summaries.

## Macro/Event Provider Environment

The DB smoke above only needs `DATABASE_URL`. Live macro/event enrichment during preopen and intraday runtime reuses the existing provider stack:

- `ALPACA_API_KEY` plus `ALPACA_SECRET_KEY` or `ALPACA_API_SECRET` for Alpaca market data and Alpaca news fallback.
- `FINNHUB_API_KEY` to enable the preferred Finnhub company-news provider.
- `FRED_API_KEY` to enable the forward-looking FRED release calendar used by preopen event risk and for fresher macro indicator reads; without it the global-context provider falls back to public CSV/Yahoo/GLD proxy paths where possible.
- `FMP_API_KEY` to enable the paid FMP economic calendar fallback; when both FRED and FMP are unset or unavailable, scheduled macro events degrade to an empty calendar.
- `ALPACA_DATA_BASE_URL` remains optional when you need to override Alpaca’s default data endpoint.

This should return `decision_status="ready"` and `risk_status="approved"` for the whitelisted long-call fixture.

Option lifecycle and hedge smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_smoke_test.py --mode paper_option_lifecycle_fixture --json
```

This should return:
- `open_risk_status="approved"` for the opening option path
- `rejection_reason_code="event_through_expiry_short_premium_blocked"` for the short-premium assignment-risk rejection path
- `hedge_overlay_action="adjust_hedge"` plus `hedge_overlay_basis="approved_assignment_notional"` for the assignment-targeted overlay path

Intraday option refresh smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_smoke_test.py --mode intraday_refresh_fixture --json
```

Use this to confirm the hourly runtime can refresh option marks/Greeks and still emit rebalance-safe snapshots.

Post-close reflection now loads same-day option and hedge artifacts from the live repository payload:
- `paper_option_decisions`
- `paper_option_positions`
- `option_risk_snapshots`
- `risk_hedge_overlays`
- `hedge_effectiveness`

Use that reflection surface to inspect:
- assignment-risk rejection paths after preopen
- hedge overlay sizing basis and protected notional after intraday or preopen hedge generation

These smoke modes are fixture-only operator checks. Scheduler-facing `preopen`, `manual_review`, `intraday_refresh`, `reflection`, and `strategy_evolution` now use live runtimes, while standalone smoke verification should keep using these isolated fixture paths.

Post-close phases may now return `status="skipped"` when the same-day persisted inputs required for a real live run are not present yet. That is an operational state, not a fake fixture success.

`python scripts/run_trading_once.py --phase ... --json` now preserves `status="skipped"` in its JSON output and exits non-zero only for `status="failed"`. Scheduler jobs log skipped trading phases as explicit `*_job_skipped` warnings with the reported reasons instead of logging them as completed passes.

Ordinary CI should keep using fixture-backed smoke modes only. Live provider/API checks stay opt-in and should use tiny ticker sets plus explicit request budgets.
