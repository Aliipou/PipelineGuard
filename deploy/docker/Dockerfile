# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

# Stage 2: Production
FROM python:3.12-slim AS production

LABEL maintainer="ali" \
      description="EU-Grade Multi-Tenant Cloud Platform" \
      version="1.0.0"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src/ ./src/
COPY config/ ./config/
COPY alembic.ini ./

RUN chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.presentation.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# Stage 3: Celery Worker
FROM production AS worker

CMD ["celery", "-A", "src.application.tasks.celery_app:app", "worker", "--loglevel=info", "--concurrency=4"]

# Stage 4: Celery Beat
FROM production AS beat

CMD ["celery", "-A", "src.application.tasks.celery_app:app", "beat", "--loglevel=info"]
