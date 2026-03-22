# FAQ

## PipelineGuard vs Airflow monitoring?
PipelineGuard works with any Python function, not just Airflow DAGs.

## Overhead of @guard decorator?
< 1ms. Use `async_report=True` for fire-and-forget.

## Self-hosted?
```bash
docker compose up
export PIPELINEGUARD_API_URL=http://localhost:8000
```
