FROM python:3.12-slim-bookworm

# Install PostgreSQL 18 client and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && install -d /etc/apt/keyrings \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main 18" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Download pinned models into /opt/models
ENV HF_HOME=/opt/models
RUN pip install --no-cache-dir huggingface-hub \
    && python -c "from huggingface_hub import snapshot_download; \
snapshot_download('BAAI/bge-small-en-v1.5', revision='5c38ec7c405ec4b44b94cc5a9bb96e735b38267a'); \
snapshot_download('cross-encoder/ms-marco-MiniLM-L12-v2', revision='7b0235231ca2674cb8ca8f022859a6eba2b1c968')"

# Lock Hugging Face and Transformers to offline mode
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# Install runtime dependencies
RUN pip install --no-cache-dir \
    "httpx>=0.28.1" \
    "pgvector>=0.5.0" \
    "psycopg[binary]>=3.3.6" \
    "sentence-transformers>=6.1.0"

# Default environment variables for database connection
ENV DATABASE_URL=postgresql://kb:kb@postgres:5432/kb
ENV PGHOST=postgres
ENV PGPORT=5432
ENV PGUSER=kb
ENV PGPASSWORD=kb
ENV PGDATABASE=kb
ENV PYTHONPATH=/app

# Copy application files
COPY . .

# Create entrypoint script
RUN printf '%s\n' \
    '#!/bin/sh' \
    'set -e' \
    'DUMP_FILE="${DUMP_FILE:-db/seed.dump}"' \
    'if [ ! -f "$DUMP_FILE" ]; then' \
    '    echo "Error: Database dump $DUMP_FILE is absent. Operator must run the build: python -m db.init.build" >&2' \
    '    exit 1' \
    'fi' \
    'HOST="${PGHOST:-postgres}"' \
    'PORT="${PGPORT:-5432}"' \
    'USER="${PGUSER:-kb}"' \
    'DB="${PGDATABASE:-kb}"' \
    'echo "Waiting for postgres at $HOST:$PORT..."' \
    'RETRIES=60' \
    'while ! pg_isready -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" > /dev/null 2>&1; do' \
    '    RETRIES=$((RETRIES - 1))' \
    '    if [ "$RETRIES" -le 0 ]; then' \
    '        echo "Error: Timed out waiting for Postgres at $HOST:$PORT" >&2' \
    '        exit 1' \
    '    fi' \
    '    sleep 0.5' \
    'done' \
    'echo "Postgres is ready."' \
    'echo "Restoring database from $DUMP_FILE..."' \
    'pg_restore --clean --if-exists --no-owner -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" "$DUMP_FILE"' \
    'echo "Running startup checks..."' \
    'python -m db.init.startup' \
    'echo "Startup finished successfully."' \
    'if [ $# -gt 0 ]; then' \
    '    exec "$@"' \
    'fi' \
    > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
