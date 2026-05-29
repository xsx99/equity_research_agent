# Research App Deploy Guide

This document covers deploying the full research app stack on the Raspberry Pi.

## Stack Overview

| Container    | Purpose                                      |
|-------------|----------------------------------------------|
| `postgres_db` | PostgreSQL database (separate compose file) |
| `scheduler`   | APScheduler: SEC, research, eval jobs        |
| `web`         | FastAPI/uvicorn web app (port 8000 internal) |
| `nginx`       | HTTPS reverse proxy (port 443 exposed)       |

## Required Environment Variables

Create `/home/pi/secrets/trading_agent.env` with:

```env
# Database
POSTGRES_PASSWORD=your_password

# LLM
GOOGLE_API_KEY=your_google_api_key
RESEARCH_MODEL_NAME=gemini-2.5-flash-lite   # optional, this is the default

# Market data (required for research pipeline)
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret

# Optional news enrichment
FINNHUB_API_KEY=your_finnhub_key
MARKETAUX_API_KEY=your_marketaux_key
```

## First-time Setup

1. SSH into the Pi:

```bash
ssh pi@10.0.0.56
```

2. Create data directories (if not already present):

```bash
sudo mkdir -p /data/postgres_data /data/mono_db_logs
sudo chown pi:pi /data/mono_db_logs
```

3. Ensure the external `postgres_network` Docker network exists:

```bash
docker network inspect postgres_network >/dev/null 2>&1 || docker network create postgres_network
```

4. Start Postgres (if not already running):

```bash
docker compose -f docker-compose.db.yml up -d
```

5. Build and start the app stack:

```bash
cd /path/to/equity_research_agent
docker compose up -d --build
```

6. Run database migrations (first deploy only):

```bash
docker exec -w /app scheduler alembic upgrade head
```

## Accessing the Web UI

Open a browser on your phone or any device on the home WiFi:

```
https://10.0.0.56
```

The first visit will show a browser warning about the self-signed certificate. Accept it once — the warning will not appear again on the same device.

The certificate is generated automatically on first nginx startup and stored in the `nginx_certs` Docker volume (persists across restarts and rebuilds).

## Scheduled Jobs

| Job                    | Schedule (ET, weekdays) | Config env vars                                          |
|------------------------|------------------------|----------------------------------------------------------|
| SEC EDGAR collection   | 2:00 AM daily          | `SEC_EDGAR_SCHEDULE_HOUR`, `SEC_EDGAR_SCHEDULE_MINUTE`   |
| Research (pre-open)    | 9:20 AM Mon–Fri        | `RESEARCH_SCHEDULE_HOUR`, `RESEARCH_SCHEDULE_MINUTE` |
| Eval                   | 4:10 PM Mon–Fri        | `EVAL_SCHEDULE_HOUR`, `EVAL_SCHEDULE_MINUTE`             |

Set `RESEARCH_RUN_ON_STARTUP=true` or `EVAL_RUN_ON_STARTUP=true` in the env file to trigger a run immediately when the scheduler container starts.

Evaluation semantics:
- pre-open scheduled or manual runs: `open_to_close`
- post-open manual runs: `run_time_price_to_close`
- post-open quick eval depends on the persisted run-time ticker snapshot price in `research_runs.input_json.price_snapshot.last_price`

## Checking Service Health

```bash
# All containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Expected: postgres_db, scheduler, web, nginx all Up

# Scheduler logs
docker logs --tail 100 scheduler

# Web app logs
docker logs --tail 100 web

# nginx logs
docker logs --tail 100 nginx
```

## Manual Pipeline Triggers

Trigger research or eval inside the running containers without waiting for the schedule:

```bash
# Research pipeline (all active tickers)
docker exec -w /app scheduler python scripts/run_research_once.py

# Eval pipeline
docker exec -w /app scheduler python scripts/run_eval_once.py

# Research agent smoke test (no DB write)
docker exec -w /app scheduler python scripts/run_research_agent_once.py
```

For same-day manual iteration, run research first, then eval after the close. If the manual run happened after `9:30 ET`, the resulting eval row should store `evaluation_params.price_window=run_time_price_to_close`.

## Redeploying After a Code Change

```bash
cd /path/to/equity_research_agent
git pull
docker compose up -d --build
```

The `nginx_certs` volume is preserved across rebuilds, so the TLS certificate is not regenerated.

The GitHub Actions deploy job treats Postgres as a persistent external dependency:

- It creates `postgres_network` if missing.
- It reuses an existing `postgres_db` container instead of trying to recreate it.
- It verifies Postgres is ready with `pg_isready`.
- It verifies `SHOW data_directory;` returns `/var/lib/postgresql/data`.
- It verifies that `/var/lib/postgresql/data` is backed by the host path `/data/postgres_data`.
- It removes and recreates only the stateless app containers: `scheduler`, `web`, and `nginx`.

If deploy fails with a container-name conflict, do not remove the container until you confirm where the data lives:

```bash
docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Source}}{{end}}{{end}}' postgres_db
docker exec postgres_db psql -U postgres -d mono_db -c "SHOW data_directory;"
```

Expected host mount: `/data/postgres_data`.

## Rotating the TLS Certificate

The self-signed cert is valid for 10 years. To force regeneration:

```bash
docker volume rm equity_research_agent_nginx_certs
docker compose up -d nginx
```
