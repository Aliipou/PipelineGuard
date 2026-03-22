# Dashboard Guide

## Accessing the Dashboard

```bash
open http://localhost:3000
# Default credentials: admin / pipelineguard
```

## Overview Page

The overview shows:
- **Pipeline health score** — weighted average of all pipelines
- **Recent failures** — last 10 failed executions with one-click replay
- **Latency trends** — p50/p95/p99 charts for the last 24 hours
- **Alert feed** — recent alerts with status (firing/resolved)

## Pipeline Detail Page

Click any pipeline to see:
- **Execution history** — scrollable list of all runs with duration and status
- **Metric charts** — throughput, latency, error rate over configurable time windows
- **Job breakdown** — which jobs within the pipeline are slowest or most error-prone
- **Active alerts** — current firing alerts with suppress option

## Alert Configuration UI

Navigate to **Settings > Alerts** to:
1. Create new alert rules (no YAML required)
2. Test rules against historical data
3. Configure notification channels
4. Set maintenance windows (suppress alerts during deploys)

## API Explorer

**Settings > API Explorer** provides an interactive OpenAPI UI to:
- Query pipeline metrics
- Trigger manual executions
- Manage alert rules programmatically
