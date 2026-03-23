# Research App Runbook

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

## Tool Smoke Test

### Local Live Tool Check
```bash
source ~/.venv/bin/activate
python scripts/run_tool_smoke_test.py --ticker AAPL
```

This runs the real tool registry against live dependencies:
- `get_market_snapshot` against Alpaca market data
- `get_recent_news` against the configured news providers
- all database-backed insider query tools against the live `insider_trades` table

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
- Unreachable Postgres or an empty `insider_trades` table will fail the DB-backed tool checks unless `--skip-db` is set.
