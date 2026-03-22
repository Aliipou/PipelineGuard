"""
Resource-usage metrics collection for tenant cost accounting.

Provides both a real Prometheus-backed collector and a mock implementation
suitable for testing and local development.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

# ======================================================================
# Data structures
# ======================================================================


@dataclass(frozen=True)
class DataPoint:
    """A single timestamped metric value."""

    timestamp: datetime
    value: float


# ======================================================================
# Abstract interface
# ======================================================================


class MetricsCollector(ABC):
    """
    Contract for collecting tenant resource-usage metrics.

    Every concrete collector must implement these four methods.
    """

    @abstractmethod
    async def get_cpu_usage(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> list[DataPoint]: ...

    @abstractmethod
    async def get_memory_usage(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> list[DataPoint]: ...

    @abstractmethod
    async def get_storage_usage(self, tenant_id: str) -> int:
        """Return current storage consumption in bytes."""
        ...

    @abstractmethod
    async def get_api_call_count(self, tenant_id: str, start: datetime, end: datetime) -> int: ...


# ======================================================================
# Prometheus client wrapper
# ======================================================================


class PrometheusClient:
    """Thin wrapper around the Prometheus HTTP query API."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "60s",
    ) -> list[DataPoint]:
        """Execute a range query and return a list of ``DataPoint``."""

        params = {
            "query": query,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "step": step,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/api/v1/query_range", params=params)
            resp.raise_for_status()
            data = resp.json()

        points: list[DataPoint] = []
        for result in data.get("data", {}).get("result", []):
            for ts, val in result.get("values", []):
                points.append(
                    DataPoint(
                        timestamp=datetime.fromtimestamp(float(ts), tz=UTC),
                        value=float(val),
                    )
                )
        return points

    async def query_instant(self, query: str) -> float:
        """Execute an instant query and return a single scalar value."""

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/api/v1/query", params={"query": query})
            resp.raise_for_status()
            data = resp.json()

        results = data.get("data", {}).get("result", [])
        if not results:
            return 0.0
        # Take the first result's latest value.
        value_pair = results[0].get("value", [0, "0"])
        return float(value_pair[1])


# ======================================================================
# Prometheus-backed collector
# ======================================================================


class PrometheusMetricsCollector(MetricsCollector):
    """Production collector backed by a live Prometheus instance."""

    def __init__(self, prometheus_url: str) -> None:
        self._client = PrometheusClient(prometheus_url)

    async def get_cpu_usage(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> list[DataPoint]:
        query = (
            f"sum(rate(container_cpu_usage_seconds_total"
            f'{{tenant_id="{tenant_id}"}}[5m])) by (tenant_id)'
        )
        return await self._client.query_range(query, start, end)

    async def get_memory_usage(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> list[DataPoint]:
        query = f'sum(container_memory_usage_bytes{{tenant_id="{tenant_id}"}}) by (tenant_id)'
        return await self._client.query_range(query, start, end)

    async def get_storage_usage(self, tenant_id: str) -> int:
        query = f'sum(tenant_storage_bytes{{tenant_id="{tenant_id}"}})'
        value = await self._client.query_instant(query)
        return int(value)

    async def get_api_call_count(self, tenant_id: str, start: datetime, end: datetime) -> int:
        query = (
            f"sum(increase(api_requests_total"
            f'{{tenant_id="{tenant_id}"}}[{_range_seconds(start, end)}s]))'
        )
        value = await self._client.query_instant(query)
        return int(value)


# ======================================================================
# Mock collector (development / testing)
# ======================================================================


class MockMetricsCollector(MetricsCollector):
    """Deterministic mock that returns synthetic data for tests."""

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    async def get_cpu_usage(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> list[DataPoint]:
        return self._generate_series(start, end, base=0.25, jitter=0.15)

    async def get_memory_usage(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> list[DataPoint]:
        return self._generate_series(start, end, base=512_000_000, jitter=100_000_000)

    async def get_storage_usage(self, tenant_id: str) -> int:
        return self._rng.randint(1_000_000_000, 50_000_000_000)

    async def get_api_call_count(self, tenant_id: str, start: datetime, end: datetime) -> int:
        hours = max(1, int((end - start).total_seconds() / 3600))
        return self._rng.randint(100, 500) * hours

    # -- helpers -------------------------------------------------------

    def _generate_series(
        self,
        start: datetime,
        end: datetime,
        base: float,
        jitter: float,
        step_seconds: int = 60,
    ) -> list[DataPoint]:
        points: list[DataPoint] = []
        current = start
        while current <= end:
            value = base + self._rng.uniform(-jitter, jitter)
            points.append(DataPoint(timestamp=current, value=max(0.0, value)))
            current = current.replace(second=current.second)  # avoid microsecond drift
            # Manually advance by step.
            from datetime import timedelta

            current += timedelta(seconds=step_seconds)
        return points


# ======================================================================
# Utilities
# ======================================================================


def _range_seconds(start: datetime, end: datetime) -> int:
    """Return the number of whole seconds between *start* and *end*."""
    return max(1, int((end - start).total_seconds()))
