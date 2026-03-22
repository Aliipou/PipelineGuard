"""
Password hashing using Argon2id.

Argon2id is the recommended password hashing algorithm for new applications
(OWASP 2023+). It combines the side-channel resistance of Argon2i with the
GPU-cracking resistance of Argon2d.
"""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class PasswordHandler:
    """
    Thin wrapper around argon2-cffi configured with secure defaults.

    Parameters mirror OWASP recommendations for interactive logins:
    - time_cost=3        (iterations)
    - memory_cost=65536  (64 MiB)
    - parallelism=4      (threads)
    """

    def __init__(
        self,
        time_cost: int = 3,
        memory_cost: int = 65536,
        parallelism: int = 4,
    ) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            type=Type.ID,  # Argon2id
        )

    def hash_password(self, plain_password: str) -> str:
        """
        Hash *plain_password* and return the encoded Argon2id string.

        The returned string includes algorithm parameters and a random salt,
        making it safe to store directly.
        """
        return str(self._hasher.hash(plain_password))

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify *plain_password* against *hashed_password*.

        Returns ``True`` on match, ``False`` on mismatch or when the hash is
        malformed.
        """
        try:
            return bool(self._hasher.verify(hashed_password, plain_password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
