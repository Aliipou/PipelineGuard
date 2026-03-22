"""Contract tests for OpenAPI schema validation.

These tests verify that the API conforms to its OpenAPI specification
and that endpoints return expected response structures.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

TENANT_HEADERS = {"X-Tenant-ID": str(uuid.uuid4())}


@pytest.fixture
def app():
    from presentation.main import app

    return app


@pytest.fixture
def client(app):
    from starlette.testclient import TestClient

    return TestClient(app)


@pytest.mark.contract
class TestOpenAPIContract:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_openapi_schema_available(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "EU Multi-Tenant Cloud Platform"
        assert "paths" in schema

    def test_tenant_endpoints_documented(self, client):
        schema = client.get("/openapi.json").json()
        paths = schema["paths"]
        tenant_paths = [p for p in paths if "tenant" in p.lower()]
        assert len(tenant_paths) >= 1

    def test_error_responses_follow_rfc9457(self, client):
        resp = client.post("/api/v1/tenants", json={}, headers=TENANT_HEADERS)
        assert resp.status_code == 422
        data = resp.json()
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert data["status"] == 422
        assert "detail" in data
