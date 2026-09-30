"""
Session token security utilities.

Raw session tokens are issued to the client; only a secure SHA-256 hash
is stored in the database.
"""

from __future__ import annotations

import hashlib
import secrets


def issue_raw_token() -> str:
    """Generate a high-entropy URL-safe random token for the client."""
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    """Compute the SHA-256 digest of a raw token for database storage/lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
