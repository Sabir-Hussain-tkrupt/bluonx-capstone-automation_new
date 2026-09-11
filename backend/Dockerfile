# ── Stage 1: Install dependencies ─────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code and scripts
COPY app/ ./app/
COPY scripts/ ./scripts/

# Ensure entrypoint script is executable
RUN chmod +x ./scripts/entrypoint.sh

# Switch to non-root user
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# Single worker is required, not an untuned default: APScheduler runs in-process,
# so --workers N runs every scheduled job N times.
# See docs/adr/0001-scheduler-single-instance.md.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
