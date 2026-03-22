# Raspberry Pi Service Checks

This note shows how to verify the Docker services running on the Raspberry Pi from your local computer.

## 1. Log in to the Raspberry Pi

From your local computer:

```bash
ssh pi@10.0.0.56
```

After login, confirm the containers are up:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected container names in this project:

- `postgres_db`
- `scheduler`

If you need to run `docker compose ...` commands, first go to the project directory (or pass `-f` explicitly), otherwise you may see `no configuration file provided: not found`:

```bash
cd /path/to/insider_trading_tracker
docker compose -f docker-compose.yml ps
```

## 2. Check health of Postgres

Check whether the Postgres container is running:

```bash
docker inspect --format='{{.State.Status}}' postgres_db
```

Check whether Postgres inside the container is accepting connections:

```bash
docker exec postgres_db pg_isready -U postgres -d mono_db
```

Optional: connect and run a simple query:

```bash
docker exec -it postgres_db psql -U postgres -d mono_db -c "SELECT now();"
```

View recent Postgres logs:

```bash
docker logs --tail 100 postgres_db
```

Verify Postgres data directory is on disk (not tmpfs):

```bash
docker exec -it postgres_db psql -U postgres -d postgres -c "SHOW data_directory;"
```

The value should map to the host volume path `/data/postgres_data`.

## 3. Check health of the scheduler service

Check whether the scheduler container is running:

```bash
docker inspect --format='{{.State.Status}}' scheduler
```

View recent scheduler logs:

```bash
docker logs --tail 100 scheduler
```

Follow logs live:

```bash
docker logs -f scheduler
```

Scheduler log files are mounted to host path `/data/mono_db_logs`.

Healthy startup should include log lines like:

- `initializing_database`
- `database_ready`
- `scheduler_service_starting`
- `scheduler_started`

If the container is restarting, inspect the restart count:

```bash
docker inspect --format='status={{.State.Status}} restart_count={{.RestartCount}}' scheduler
```

## 4. Trigger the SEC collector manually

Run the SEC collector job once inside the live scheduler container:

```bash
docker exec -w /app scheduler python -c "from datetime import date; from src.scheduler.jobs.sec_edgar_job import SECEdgarJob; SECEdgarJob().run(target_date=date(2026, 3, 20))"
```

Replace `2026, 3, 20` with the filing date you want to test. Use a business day if you want a predictable smoke test; weekends and market holidays may legitimately return few or no filings.

Watch the result in scheduler logs:

```bash
docker logs --tail 200 scheduler | grep -E 'sec_edgar_job_(started|completed|failed)|Collection complete'
```

You can also trigger the same run directly from your local computer without opening an interactive SSH session:

```bash
ssh pi@10.0.0.56 'docker exec -w /app scheduler python -c "from datetime import date; from src.scheduler.jobs.sec_edgar_job import SECEdgarJob; SECEdgarJob().run(target_date=date(2026, 3, 20))"'
```

## 5. Run checks directly from your local computer

You can run the same checks without first opening an interactive SSH session:

```bash
ssh pi@10.0.0.56 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
ssh pi@10.0.0.56 'docker exec postgres_db pg_isready -U postgres -d mono_db'
ssh pi@10.0.0.56 'docker logs --tail 100 scheduler'
```
