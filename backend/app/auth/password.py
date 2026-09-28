"""
Password helpers for email/password authentication.

Passwords are never stored in plain text. We hash once on registration and
verify by re-hashing and comparing.

For a student project this is a reasonable default. If you later add real
production users, replace this with a deliberately slow KDF and a per-user
salt/pepper strategy that matches your deployment's secret management.
"""

from __future__ import annotations

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)
