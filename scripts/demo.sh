#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# PipelineGuard — 2-Minute Demo Script
#
# This script automates the full demo sequence:
#   1. Generate JWT keys
#   2. Start the full Docker stack
#   3. Wait for health
#   4. Run load simulation (1000 jobs)
#   5. Show alerts triggered
#   6. Generate weekly summary
#
# Record with: OBS / QuickTime / ffmpeg — target: 2 minutes
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="http://localhost:8000"
COMPOSE_DIR="$REPO_ROOT/deploy/docker"

banner() {
  echo ""
  echo "══════════════════════════════════════════════════════"
  echo "  $1"
  echo "══════════════════════════════════════════════════════"
}

wait_healthy() {
  local max=60
  local i=0
  echo -n "Waiting for API"
  while ! curl -sf "$API/health" > /dev/null 2>&1; do
    sleep 2
    i=$((i+1))
    echo -n "."
    if [ $i -ge $max ]; then
      echo ""
      echo "ERROR: API did not become healthy within $((max*2))s"
      exit 1
    fi
  done
  echo " ready!"
}

# ── Step 1: Generate JWT Keys ────────────────────────────────────────────────
banner "Step 1/5 — Generate JWT Keys"
cd "$REPO_ROOT"
if [ ! -f "$COMPOSE_DIR/.env" ]; then
  python scripts/generate_keys.py <<< "y" || python scripts/generate_keys.py
else
  echo ".env already exists, skipping key generation."
fi

# ── Step 2: Start Docker stack ───────────────────────────────────────────────
banner "Step 2/5 — Docker Compose Up"
cd "$COMPOSE_DIR"
docker compose up --build -d
echo "Services starting..."

# ── Step 3: Wait for healthy API ─────────────────────────────────────────────
banner "Step 3/5 — Wait for API Health"
wait_healthy
curl -s "$API/health" | python3 -m json.tool

# ── Step 4: Run Load Simulation ──────────────────────────────────────────────
banner "Step 4/5 — Simulate 1000 Jobs (10% silent failures + drift)"
cd "$REPO_ROOT"
python scripts/simulate_load.py --host "$API" --jobs 1000

# ── Step 5: Show Prometheus Metrics ──────────────────────────────────────────
banner "Step 5/6 — Check Drift & Alerts"
echo "Giving Celery worker 30s to process drift checks..."
sleep 30

echo ""
echo "── Prometheus Metrics ───────────────────────────────────"
curl -s "$API/metrics" | grep -E "^(pipeline_silent|pipeline_latency|pipeline_alerts)" || true

# ── Step 6: Generate & display weekly summary ────────────────────────────────
banner "Step 6/6 — Weekly CTO Summary"

# Extract first tenant ID from the API
TENANT_ID=$(curl -s "$API/api/v1/tenants?page_size=1" | python3 -c "
import sys, json
data = json.load(sys.stdin)
items = data.get('items', [])
if items:
    print(items[0]['id'])
" 2>/dev/null || true)

if [ -n "$TENANT_ID" ]; then
  echo "Generating summary for tenant: $TENANT_ID"
  curl -s -X POST "$API/api/v1/tenants/$TENANT_ID/summary/generate" > /dev/null 2>&1 || true
  sleep 2
  SUMMARY=$(curl -s "$API/api/v1/tenants/$TENANT_ID/summary" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('plain_english_summary', 'Summary not yet available.'))
" 2>/dev/null || true)
  echo ""
  echo "────────────────────────────────────────────────────────"
  echo "$SUMMARY"
  echo "────────────────────────────────────────────────────────"
else
  echo "No tenants found — skipping summary (run simulate_load.py first)."
fi

echo ""
echo "── Open in browser ──────────────────────────────────────"
echo "  Grafana:    http://localhost:3000  (admin / admin)"
echo "  Prometheus: http://localhost:9090"
echo "  API Docs:   http://localhost:8000/docs"
echo ""
echo "Demo complete! Stop stack with:"
echo "  cd deploy/docker && docker compose down"
