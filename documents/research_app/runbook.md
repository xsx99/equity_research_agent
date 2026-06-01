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
