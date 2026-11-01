FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency requirements
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy backend source code
COPY backend/ /app/

# Expose HTTP port (Render / cloud providers provide PORT env var)
ENV PORT=8000
EXPOSE 8000

# Run orchestrator (executes alembic migrations then spawns API, worker, outbox, reaper, scheduler)
CMD ["python", "run_all.py"]
