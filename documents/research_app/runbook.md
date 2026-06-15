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
- `paper_option_fixture`: whitelisted paper option decision, leg derivation, and assignment-risk evaluation
- `paper_option_lifecycle_fixture`: end-to-end option open approval, assignment-risk rejection, and assignment-targeted hedge-overlay materialization
- `intraday_refresh_fixture`: hourly intraday signal delta plus deduped alert generation
- `reflection_fixture`: post-close reflection and learning-factor extraction
- `strategy_evolution_fixture`: strategy proposal generation from reflection fixtures

## Option Operator Checks

Preopen option approval smoke:

```bash
source ~/.venv/bin/activate
python scripts/run_trading_smoke_test.py --mode paper_option_fixture --json
```

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
