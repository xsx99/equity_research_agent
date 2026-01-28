FROM python:3.11-slim

WORKDIR /app

# uses the official python:3.11-slim base image 
# which has Python and pip already properly installed and in the PATH.
# it is a good practice to use the official base image 
# and install dependencies in a single RUN statement to avoid caching issues.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic/ ./alembic/
COPY alembic.ini .
COPY src/ ./src/
COPY scripts/ ./scripts/

CMD ["python", "scripts/run_collector.py"]
