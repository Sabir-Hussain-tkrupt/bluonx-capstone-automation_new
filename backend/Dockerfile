# Base image pinned to an exact patch release (3.11.17, security fixes) instead
# of the floating 3.11-slim tag, so every build gets the same patched Python.
# Bump this line when a new 3.11.x security release ships.

# ── Stage 1: Install dependencies ─────────────────────────────────────────
FROM python:3.11.17-slim-trixie AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────────
FROM python:3.11.17-slim-trixie AS runtime

WORKDIR /app

# Pull in Debian security updates released after the base image was built.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/

# Create secrets folder and set permissions for appuser
RUN mkdir -p /app/secrets && chown -R appuser:appuser /app/secrets

# Switch to non-root user
USER appuser

EXPOSE 8000

# Write secret file if present, then start Uvicorn.
#   --limit-concurrency: past this many in-flight requests uvicorn answers 503
#     instead of accepting more, so a flood cannot exhaust the single task's
#     memory. Far above normal traffic.
#   --timeout-keep-alive: longer than the ALB's 60s idle timeout (AWS guidance),
#     so uvicorn never closes a connection the ALB is about to reuse (a 502).
CMD sh -c 'if [ -n "$DOCUSIGN_PRIVATE_KEY_SECRET" ]; then printf "%s\n" "$DOCUSIGN_PRIVATE_KEY_SECRET" > /app/secrets/docusign_private_key.pem; fi && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --limit-concurrency 200 --timeout-keep-alive 65'
