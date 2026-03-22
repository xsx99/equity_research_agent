# Research App Deploy Notes

## Secrets
- Keep `GOOGLE_API_KEY` out of tracked source files.
- Put runtime secrets in a repo-root `.env` file on the target host, or export them in the shell before starting services.
- Use `.env.example` as the template for required variables.

## Docker Compose
- `docker-compose.yml` now passes `GOOGLE_API_KEY` and `RESEARCH_MODEL_NAME` into the `scheduler` service via environment variables.
- Docker Compose reads values from the host environment or the repo-root `.env` file when you run `docker compose`.
- The container does not need the `.env` file copied into the image as long as Compose injects the variables at launch.

## Minimum Production Setup
1. Create `/path/to/insider_trading_tracker/.env` on the production host.
2. Set at least:
   - `GOOGLE_API_KEY=...`
   - `RESEARCH_MODEL_NAME=gemini-2.5-flash-lite`
   - `POSTGRES_PASSWORD=...`
3. Start services with `docker compose up -d`.

## Verify Service Env
```bash
docker compose exec scheduler python - <<'PY'
import os
print(bool(os.getenv("GOOGLE_API_KEY")))
print(os.getenv("RESEARCH_MODEL_NAME"))
PY
```

The expected output is `True` on the first line and `gemini-2.5-flash-lite` on the second line unless you intentionally override the model.
