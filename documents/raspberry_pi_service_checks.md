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

- `insider_trading_db`
- `insider_trading_collector`

## 2. Check health of Postgres

Check whether the Postgres container is running:

```bash
docker inspect --format='{{.State.Status}}' insider_trading_db
```

Check whether Postgres inside the container is accepting connections:

```bash
docker exec insider_trading_db pg_isready -U postgres -d insider_trading
```

Optional: connect and run a simple query:

```bash
docker exec -it insider_trading_db psql -U postgres -d insider_trading -c "SELECT now();"
```

View recent Postgres logs:

```bash
docker logs --tail 100 insider_trading_db
```

## 3. Check health of the scheduler service

Check whether the scheduler container is running:

```bash
docker inspect --format='{{.State.Status}}' insider_trading_collector
```

View recent scheduler logs:

```bash
docker logs --tail 100 insider_trading_collector
```

Follow logs live:

```bash
docker logs -f insider_trading_collector
```

Healthy startup should include log lines like:

- `initializing_database`
- `database_ready`
- `scheduler_service_starting`
- `scheduler_started`

If the container is restarting, inspect the restart count:

```bash
docker inspect --format='status={{.State.Status}} restart_count={{.RestartCount}}' insider_trading_collector
```

## 4. Run checks directly from your local computer

You can run the same checks without first opening an interactive SSH session:

```bash
ssh pi@10.0.0.56 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
ssh pi@10.0.0.56 'docker exec insider_trading_db pg_isready -U postgres -d insider_trading'
ssh pi@10.0.0.56 'docker logs --tail 100 insider_trading_collector'
```
