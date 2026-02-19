#!/usr/bin/env python3
"""PipelineGuard Load Simulator.

Simulates 1000 job executions across 3 tenants:
- 10% silent failures  (SUCCEEDED + 0 records)
- Latency drift after job #700 (+40% duration increase)
- Random pipeline assignment

Usage:
    python scripts/simulate_load.py [--host http://localhost:8000] [--jobs 1000]

Requires: pip install requests
"""

from __future__ import annotations

import argparse
import random
import sys
import time
import uuid
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    print("Error: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────────

NUM_TENANTS = 3
PIPELINES_PER_TENANT = 4
SILENT_FAILURE_RATE = 0.10   # 10%
DRIFT_START_RATIO = 0.70     # drift begins at 70% of total jobs
DRIFT_MULTIPLIER = 1.45      # 45% latency increase (above 25% alert threshold)
BASE_DURATION_SECONDS = 60.0
INTER_JOB_DELAY = 0.02       # seconds between requests


def create_tenant(host: str, index: int) -> str | None:
    slug = f"sim-{uuid.uuid4().hex[:8]}"
    payload = {
        "name": f"Simulation Tenant {index}",
        "slug": slug,
        "admin_email": f"admin@{slug}.example",
        "tier": "STANDARD",
    }
    try:
        resp = requests.post(f"{host}/api/v1/tenants", json=payload, timeout=10)
        if resp.status_code == 201:
            tenant_id = resp.json()["id"]
            print(f"  ✓ Tenant {index}: {slug} ({tenant_id[:8]}...)")
            return tenant_id
        print(f"  ✗ Tenant {index}: HTTP {resp.status_code} — {resp.text[:100]}")
    except requests.RequestException as exc:
        print(f"  ✗ Tenant {index}: {exc}")
    return None


def create_pipeline(host: str, tenant_id: str, index: int) -> str | None:
    base_duration = BASE_DURATION_SECONDS + random.uniform(-10, 10)
    payload = {
        "name": f"ETL Pipeline {index}",
        "schedule": "*/15 * * * *",
        "expected_duration_seconds": base_duration,
    }
    try:
        resp = requests.post(
            f"{host}/api/v1/tenants/{tenant_id}/pipelines",
            json=payload,
            timeout=10,
        )
        if resp.status_code == 201:
            return resp.json()["id"]
    except requests.RequestException:
        pass
    return None


def report_execution(
    host: str,
    tenant_id: str,
    pipeline_id: str,
    duration: float,
    records: int,
) -> bool:
    now = datetime.utcnow()
    payload = {
        "status": "SUCCEEDED",
        "started_at": (now - timedelta(seconds=duration)).isoformat() + "Z",
        "finished_at": now.isoformat() + "Z",
        "duration_seconds": round(duration, 2),
        "records_processed": records,
        "error_message": None,
    }
    try:
        resp = requests.post(
            f"{host}/api/v1/tenants/{tenant_id}/pipelines/{pipeline_id}/executions",
            json=payload,
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except requests.RequestException:
        return False


def run_simulation(host: str, total_jobs: int) -> None:
    print(f"\nPipelineGuard Load Simulator")
    print(f"Target: {host}")
    print(f"Jobs: {total_jobs} | Silent failure rate: {SILENT_FAILURE_RATE*100:.0f}%")
    print(f"Drift starts at job: {int(total_jobs * DRIFT_START_RATIO)}")
    print("─" * 60)

    # ── Step 1: Create tenants ──────────────────────────────────────────────
    print(f"\n[1/3] Creating {NUM_TENANTS} tenants...")
    tenant_ids: list[str] = []
    for i in range(1, NUM_TENANTS + 1):
        tid = create_tenant(host, i)
        if tid:
            tenant_ids.append(tid)

    if not tenant_ids:
        print("\nError: No tenants created. Is the API running?")
        sys.exit(1)

    # ── Step 2: Create pipelines ────────────────────────────────────────────
    print(f"\n[2/3] Creating {PIPELINES_PER_TENANT} pipelines per tenant...")
    pipeline_map: dict[str, list[str]] = {}
    for tenant_id in tenant_ids:
        pipeline_map[tenant_id] = []
        for i in range(1, PIPELINES_PER_TENANT + 1):
            pid = create_pipeline(host, tenant_id, i)
            if pid:
                pipeline_map[tenant_id].append(pid)
        print(f"  Tenant {tenant_id[:8]}: {len(pipeline_map[tenant_id])} pipelines")

    # ── Step 3: Simulate job executions ────────────────────────────────────
    print(f"\n[3/3] Simulating {total_jobs} job executions...")
    drift_start = int(total_jobs * DRIFT_START_RATIO)
    success_count = 0
    silent_failure_count = 0
    drift_count = 0

    for job_num in range(1, total_jobs + 1):
        tenant_id = random.choice(tenant_ids)
        pipelines = pipeline_map.get(tenant_id, [])
        if not pipelines:
            continue
        pipeline_id = random.choice(pipelines)

        is_drifting = job_num >= drift_start
        is_silent_failure = random.random() < SILENT_FAILURE_RATE

        # Duration: normal ±10%, or drifted by DRIFT_MULTIPLIER
        if is_drifting:
            duration = BASE_DURATION_SECONDS * DRIFT_MULTIPLIER * (1 + random.uniform(-0.05, 0.1))
            drift_count += 1
        else:
            duration = BASE_DURATION_SECONDS * (1 + random.uniform(-0.1, 0.1))

        records = 0 if is_silent_failure else random.randint(500, 50_000)
        if is_silent_failure:
            silent_failure_count += 1

        ok = report_execution(host, tenant_id, pipeline_id, duration, records)
        if ok:
            success_count += 1

        if job_num % 100 == 0 or job_num == total_jobs:
            drift_marker = " [DRIFT ACTIVE]" if is_drifting else ""
            print(
                f"  Job {job_num:>4}/{total_jobs} | "
                f"ok={success_count} silent={silent_failure_count} "
                f"drift={drift_count}{drift_marker}"
            )

        time.sleep(INTER_JOB_DELAY)

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("Simulation complete.")
    print(f"  Total jobs:       {total_jobs}")
    print(f"  Successful API:   {success_count}")
    print(f"  Silent failures:  {silent_failure_count} ({silent_failure_count/total_jobs*100:.1f}%)")
    print(f"  Drifted jobs:     {drift_count} ({drift_count/total_jobs*100:.1f}%)")
    print()
    print("Expected results (after Celery worker processes):")
    print(f"  • pipeline_silent_failures_total  counter should be ≥ {silent_failure_count}")
    print(f"  • pipeline_latency_drift_detected counter should be > 0")
    print(f"  • Check http://localhost:3000 → PipelineGuard dashboard")
    print(f"  • Check http://localhost:9090 → query: pipeline_latency_drift_detected")


def main() -> None:
    parser = argparse.ArgumentParser(description="PipelineGuard load simulator")
    parser.add_argument("--host", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--jobs", type=int, default=1000, help="Total jobs to simulate")
    args = parser.parse_args()

    run_simulation(args.host, args.jobs)


if __name__ == "__main__":
    main()
