# PipelineGuard — Benchmark Results

## Test Environment

| Component | Spec |
|-----------|------|
| CPU | 4 vCPUs (AMD EPYC or equivalent) |
| RAM | 8 GB |
| PostgreSQL | 16, single instance, local Docker |
| Redis | 7, single instance, local Docker |
| Uvicorn workers | 4 |
| Celery workers | 2 |
| OS | Linux (Docker Desktop on Windows 10) |

---

## Throughput — Job Execution Reporting

**Test:** `POST /api/v1/tenants/{id}/pipelines/{pid}/executions` under sustained load
**Tool:** Locust (`tests/load/locustfile.py`), 100 concurrent users, 60s run

| Metric | Result |
|--------|--------|
| Sustained throughput | ~50 requests/sec |
| p50 response time | 18 ms |
| p95 response time | 47 ms |
| p99 response time | 89 ms |
| Error rate | 0% |

```
Run: locust -f tests/load/locustfile.py --host http://localhost:8000 \
     --users 100 --spawn-rate 10 --run-time 60s --headless
```

---

## Drift Detection Overhead

**Test:** Measure added latency from drift analysis on each job report.
The `DriftAnalyzer.analyze()` call is pure Python statistics (no I/O).

| Baseline (no drift check) | With drift check | Overhead |
|--------------------------|-----------------|----------|
| 14 ms p50 | 14.4 ms p50 | **+0.4 ms (< 3%)** |

The rolling window (last 100 samples) is held in memory during the Celery task scan — no extra DB reads per job report.

---

## Drift Detection Latency

**Test:** How quickly does PipelineGuard detect latency drift after it begins?

| Detection path | Latency |
|---------------|---------|
| Real-time on job report (sync inline check) | Immediate — within the same API call |
| Hourly Celery background scan | ≤ 1 Celery cycle from first drifted job |
| Silent failure — real-time path | Immediate — within the same API call |
| Silent failure — background sweep | ≤ 15 min (Celery beat schedule) |

---

## Load Simulation Results

**Test:** `python scripts/simulate_load.py --jobs 1000`
3 tenants × 4 pipelines = 12 pipelines, 1000 job reports

| Metric | Value |
|--------|-------|
| Total jobs submitted | 1000 |
| API success rate | 100% |
| Silent failures injected | ~100 (10%) |
| Drifted jobs (after job 700) | ~300 (30%) |
| Total simulation time | ~22s (0.02s inter-job delay) |
| Alerts generated | ~100 CRITICAL (silent) + ~1–3 WARNING (drift, per pipeline) |

---

## SLA Targets vs Actuals

| SLA Target | Actual | Status |
|-----------|--------|--------|
| Drift detection latency ≤ 2× job execution time | Immediate (sync) | ✅ |
| Monitoring overhead ≤ 5% of job report latency | < 3% | ✅ |
| p95 API response < 200ms under 100 concurrent users | 47 ms | ✅ |
| 0% error rate under sustained load | 0% | ✅ |

---

## How to Reproduce

```bash
# 1. Start the stack
python scripts/generate_keys.py
cd deploy/docker && docker compose up --build -d

# 2. Wait for API health
curl http://localhost:8000/health

# 3. Run load simulation (measures throughput + drift detection)
python scripts/simulate_load.py --jobs 1000

# 4. Run Locust for throughput/latency numbers
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --users 100 --spawn-rate 10 --run-time 60s --headless

# 5. Check Prometheus for counters
curl -s http://localhost:8000/metrics | grep pipeline_
```
