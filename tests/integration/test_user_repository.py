"""Integration tests for UserRepository — tenant schema isolation."""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.models.user import User
from infrastructure.adapters import InMemoryUserRepository


@pytest.mark.integration
class TestUserRepository:
    def test_save_and_get_by_id(self):
        repo = InMemoryUserRepository()
        user = User(id=uuid4(), email="a@b.com", full_name="A B")
        repo.save(user)
        assert repo.get_by_id(user.id).email == "a@b.com"

    def test_get_by_email(self):
        repo = InMemoryUserRepository()
        user = User(id=uuid4(), email="test@x.com", full_name="Test")
        repo.save(user)
        assert repo.get_by_email("test@x.com").full_name == "Test"

    def test_get_by_email_not_found(self):
        repo = InMemoryUserRepository()
        assert repo.get_by_email("nope@x.com") is None

    def test_count_by_tenant(self):
        repo = InMemoryUserRepository()
        tid = uuid4()
        repo.save(User(id=uuid4(), tenant_id=tid, email="u1@x.com"))
        repo.save(User(id=uuid4(), tenant_id=tid, email="u2@x.com"))
        repo.save(User(id=uuid4(), tenant_id=uuid4(), email="u3@x.com"))
        assert repo.count_by_tenant(tid) == 2

    def test_update_user(self):
        repo = InMemoryUserRepository()
        user = User(id=uuid4(), email="up@x.com", full_name="Before")
        repo.save(user)
        user.full_name = "After"
        repo.update(user)
        assert repo.get_by_id(user.id).full_name == "After"

    def test_tenant_isolation(self):
        """Users from different tenants don't mix."""
        repo = InMemoryUserRepository()
        t1, t2 = uuid4(), uuid4()
        repo.save(User(id=uuid4(), tenant_id=t1, email="a@t1.com"))
        repo.save(User(id=uuid4(), tenant_id=t2, email="a@t2.com"))
        assert repo.count_by_tenant(t1) == 1
        assert repo.count_by_tenant(t2) == 1
