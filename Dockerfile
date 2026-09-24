# ──────────────────────────────────────────────────────────────────────────────
# SkillMesh API — Render Docker Web Service
#
# Single source of truth for the build.  No render.yaml, Procfile, or
# runtime.txt are needed alongside this file.
#
# Build context: repository root
# Python version: 3.11 (satisfies X | None union syntax used throughout)
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# ── System dependencies ──────────────────────────────────────────────────────
# libpq-dev  → psycopg2-binary compile-time headers (even for binary wheel)
# gcc        → needed for some Python package C extensions
# --no-install-recommends keeps the image lean
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ──────────────────────────────────────────────────────
# Copy requirements first so Docker can cache this layer independently of
# application code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Application code ─────────────────────────────────────────────────────────
COPY . .

# ── Non-root user (security best practice) ──────────────────────────────────
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

# ── Port ────────────────────────────────────────────────────────────────────
# Render injects $PORT at runtime.  We expose the default here for
# documentation; the CMD below always reads the actual $PORT env var.
EXPOSE 8000

# ── Migrations + server start ────────────────────────────────────────────────
# Run Alembic migrations before starting uvicorn.
# - Alembic uses psycopg2 (sync) via alembic/env.py → get_sync_database_url()
# - uvicorn binds to $PORT on 0.0.0.0 as required by Render
# - sh -c is needed so $PORT is evaluated at container runtime, not build time
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
