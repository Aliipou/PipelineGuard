"""Schema validation contract tests — verify request validation and RFC 9457 errors."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

# A valid tenant ID header to pass the tenant context middleware
TENANT_HEADERS = {"X-Tenant-ID": str(uuid.uuid4())}


@pytest.fixture
def client():
    from starlette.testclient import TestClient

    from presentation.main import create_app

    return TestClient(create_app())


@pytest.mark.contract
class TestTenantValidation:
    def test_create_tenant_missing_name(self, client):
        resp = client.post(
            "/api/v1/tenants",
            json={"slug": "valid-slug", "admin_email": "a@b.com"},
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["title"] == "Validation Error"
        assert any("name" in e.get("field", "") for e in data.get("errors", []))

    def test_create_tenant_invalid_slug(self, client):
        resp = client.post(
            "/api/v1/tenants",
            json={
                "name": "Test",
                "slug": "INVALID SLUG!",
                "admin_email": "a@b.com",
            },
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 422

    def test_create_tenant_invalid_email(self, client):
        resp = client.post(
            "/api/v1/tenants",
            json={
                "name": "Test",
                "slug": "valid-slug",
                "admin_email": "not-an-email",
            },
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 422

    def test_create_tenant_slug_too_short(self, client):
        resp = client.post(
            "/api/v1/tenants",
            json={
                "name": "Test",
                "slug": "x",
                "admin_email": "a@b.com",
            },
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 422


@pytest.mark.contract
class TestAuthValidation:
    def test_register_weak_password(self, client):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@test.com",
                "password": "weak",
                "full_name": "Test User",
            },
        )
        assert resp.status_code == 422

    def test_register_missing_email(self, client):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "password": "Str0ng!Pass#99",
                "full_name": "Test User",
            },
        )
        assert resp.status_code == 422

    def test_login_missing_password(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": "user@test.com",
            },
        )
        assert resp.status_code == 422


@pytest.mark.contract
class TestRFC9457Format:
    def test_validation_error_has_all_fields(self, client):
        resp = client.post("/api/v1/tenants", json={}, headers=TENANT_HEADERS)
        assert resp.status_code == 422
        data = resp.json()
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data
        assert data["status"] == 422
        assert resp.headers.get("content-type") == "application/problem+json"

    def test_missing_tenant_context_returns_problem_json(self, client):
        """Requests without tenant context get a 403 RFC 9457 response."""
        resp = client.get(f"/api/v1/tenants/{uuid.uuid4()}")
        assert resp.status_code == 403
        data = resp.json()
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert data["status"] == 403

    def test_not_found_returns_problem_json(self, client):
        """A GET to a nonexistent tenant with valid context should return domain error."""
        resp = client.get(f"/api/v1/tenants/{uuid.uuid4()}", headers=TENANT_HEADERS)
        assert resp.status_code in (404, 500)
        data = resp.json()
        assert "type" in data
        assert "title" in data
        assert "status" in data
