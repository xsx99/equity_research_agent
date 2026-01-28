FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic/ ./alembic/
COPY alembic.ini .
COPY src/ ./src/
COPY scripts/ ./scripts/

CMD ["python", "scripts/run_collector.py"]
