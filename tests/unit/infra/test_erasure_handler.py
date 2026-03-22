"""Tests for infrastructure.gdpr.erasure_handler."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from infrastructure.gdpr.erasure_handler import (
    ErasureHandler,
    ErasureStep,
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_backend(**overrides: AsyncMock) -> AsyncMock:
    """Return an AsyncMock backend with all expected methods."""
    backend = AsyncMock()
    backend.freeze_tenant = overrides.get("freeze_tenant", AsyncMock())
    backend.export_final_archive = overrides.get(
        "export_final_archive",
        AsyncMock(return_value="/tmp/archive.tar.gz"),
    )
    backend.cascade_delete_data = overrides.get("cascade_delete_data", AsyncMock())
    backend.drop_schema = overrides.get("drop_schema", AsyncMock())
    backend.rotate_encryption_key = overrides.get("rotate_encryption_key", AsyncMock())
    backend.purge_caches = overrides.get("purge_caches", AsyncMock())
    backend.write_audit_record = overrides.get("write_audit_record", AsyncMock())
    return backend


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestErasureHandlerExecute:
    async def test_runs_all_7_steps(self) -> None:
        backend = _make_backend()
        handler = ErasureHandler(backend=backend)
        result = await handler.execute("t-1")

        assert len(result.steps) == 7
        step_names = [s.step for s in result.steps]
        assert step_names == [
            ErasureStep.FREEZE_TENANT,
            ErasureStep.EXPORT_FINAL_ARCHIVE,
            ErasureStep.CASCADE_DELETE_DATA,
            ErasureStep.DROP_SCHEMA,
            ErasureStep.ROTATE_ENCRYPTION_KEY,
            ErasureStep.PURGE_CACHES,
            ErasureStep.WRITE_AUDIT_RECORD,
        ]

    async def test_all_steps_succeed(self) -> None:
        backend = _make_backend()
        handler = ErasureHandler(backend=backend)
        result = await handler.execute("t-1")

        assert result.success is True
        assert all(s.success for s in result.steps)

    async def test_one_step_fails_but_all_attempted(self) -> None:
        failing_drop = AsyncMock(side_effect=RuntimeError("boom"))
        backend = _make_backend(drop_schema=failing_drop)
        handler = ErasureHandler(backend=backend)
        result = await handler.execute("t-1")

        assert result.success is False
        # All 7 steps should still be recorded
        assert len(result.steps) == 7
        # The drop_schema step (index 3) failed
        assert result.steps[3].success is False
        assert "boom" in result.steps[3].detail
        # Subsequent steps still ran
        assert result.steps[4].success is True  # rotate_encryption_key
        assert result.steps[5].success is True  # purge_caches


@pytest.mark.asyncio
class TestConvenienceMethods:
    async def test_freeze_tenant(self) -> None:
        backend = _make_backend()
        handler = ErasureHandler(backend=backend)
        step_result = await handler.freeze_tenant("t-1")
        assert step_result.success is True
        assert step_result.step == ErasureStep.FREEZE_TENANT

    async def test_purge_caches(self) -> None:
        backend = _make_backend()
        handler = ErasureHandler(backend=backend)
        step_result = await handler.purge_caches("t-1")
        assert step_result.success is True
        assert step_result.step == ErasureStep.PURGE_CACHES

    async def test_convenience_method_records_failure(self) -> None:
        failing = AsyncMock(side_effect=ValueError("oops"))
        backend = _make_backend(cascade_delete_data=failing)
        handler = ErasureHandler(backend=backend)
        step_result = await handler.cascade_delete_data("t-1")
        assert step_result.success is False
        assert "oops" in step_result.detail
