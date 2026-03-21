"""PipelineGuard Python SDK.

Drop-in decorator and context manager for reporting pipeline executions.
Zero dependencies beyond the standard library.

Quick start::

    from pipelineguard import guard

    @guard(
        pipeline_id="550e8400-e29b-41d4-a716-446655440000",
        tenant_id="your-tenant-id",
        api_url="https://pipelineguard.example.com",
        api_key="pg_live_...",
    )
    def nightly_etl():
        df = extract()
        df = transform(df)
        records = load(df)
        return records  # return count -> reported as records_processed
"""
from __future__ import annotations

import functools
import json
import logging
import time
import urllib.request
from datetime import UTC, datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)


class PipelineGuardClient:
    """HTTP client for the PipelineGuard API."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        tenant_id: str,
        timeout: int = 10,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.timeout = timeout

    def report_execution(
        self,
        pipeline_id: str,
        status: str,
        started_at: datetime,
        finished_at: datetime,
        duration_seconds: float,
        records_processed: int = 0,
        error_message: str = "",
    ) -> dict[str, Any]:
        """POST an execution record to PipelineGuard."""
        url = (
            f"{self.api_url}/api/v1/tenants/{self.tenant_id}"
            f"/pipelines/{pipeline_id}/executions"
        )
        payload = {
            "status": status,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": duration_seconds,
            "records_processed": records_processed,
            "error_message": error_message,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            logger.warning(
                "PipelineGuard report failed: %s", exc,
                extra={"pipeline_id": pipeline_id},
            )
            return {"error": str(exc)}


def guard(
    pipeline_id: str,
    tenant_id: str,
    api_url: str,
    api_key: str,
    count_result: bool = True,
    timeout: int = 10,
) -> Callable:
    """Decorator that wraps a function and reports its execution to PipelineGuard.

    Args:
        pipeline_id: The UUID of the pipeline registered in PipelineGuard.
        tenant_id: Your PipelineGuard tenant UUID.
        api_url: Base URL of the PipelineGuard API.
        api_key: API key for authentication.
        count_result: If True, the function's integer return value is used
            as ``records_processed``. Useful for ETL functions that return
            a record count.
        timeout: HTTP timeout in seconds for the report call.

    Example::

        @guard(
            pipeline_id="550e8400-e29b-41d4-a716-446655440000",
            tenant_id="acme-tenant-uuid",
            api_url="https://pipelineguard.example.com",
            api_key="pg_live_abc123",
        )
        def daily_user_sync() -> int:
            users = fetch_users_from_crm()
            upsert_to_warehouse(users)
            return len(users)  # reported as records_processed
    """
    client = PipelineGuardClient(
        api_url=api_url,
        api_key=api_key,
        tenant_id=tenant_id,
        timeout=timeout,
    )

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started_at = datetime.now(UTC)
            start_time = time.perf_counter()
            status = "SUCCEEDED"
            error_message = ""
            result = None

            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                status = "FAILED"
                error_message = str(exc)
                raise
            finally:
                finished_at = datetime.now(UTC)
                duration = round(time.perf_counter() - start_time, 3)
                records = int(result) if count_result and isinstance(result, int) else 0

                client.report_execution(
                    pipeline_id=pipeline_id,
                    status=status,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_seconds=duration,
                    records_processed=records,
                    error_message=error_message,
                )

            return result

        return wrapper

    return decorator
