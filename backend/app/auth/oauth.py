"""
OAuth 2.0 / OpenID Connect client utilities for Google and DigiLocker.

Implements:
- Cryptographic state generation and validation (HMAC-SHA256 signed, time-limited)
- PKCE (Proof Key for Code Exchange) code_verifier and code_challenge (S256)
- Google OAuth 2.0 authorization URL, token exchange, and userinfo verification
- DigiLocker / MeriPehchaan official OAuth 2.0 authorization URL, token exchange, and user verification
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_settings

STATE_TTL_SECONDS = 900  # 15 minutes


class OAuthConfigurationError(Exception):
    """Raised when an OAuth provider is not configured with client credentials."""
    status_code: int = 503
    detail: str = "OAuth provider is not configured"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.detail)
        if detail:
            self.detail = detail


class OAuthVerificationError(Exception):
    """Raised when OAuth state, token exchange, or identity verification fails."""
    status_code: int = 400
    detail: str = "OAuth verification failed"

    def __init__(self, detail: str | None = None, status_code: int = 400) -> None:
        super().__init__(detail or self.detail)
        if detail:
            self.detail = detail
        self.status_code = status_code


# ---------------------------------------------------------------------------
# PKCE Helpers (RFC 7636)
# ---------------------------------------------------------------------------

def generate_code_verifier() -> str:
    """Generate a high-entropy cryptographic code verifier."""
    token = secrets.token_urlsafe(64)
    # RFC 7636 limits code_verifier to 43-128 unreserved characters
    return token[:128]


def generate_code_challenge(verifier: str) -> str:
    """Compute S256 code challenge from a code verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii")
    return challenge.rstrip("=")


# ---------------------------------------------------------------------------
# State Protection (HMAC-SHA256 signed)
# ---------------------------------------------------------------------------

def _get_signing_key() -> bytes:
    settings = get_settings()
    # Derive HMAC signing key from available configuration
    seed = settings.GOOGLE_CLIENT_SECRET or settings.DIGILOCKER_CLIENT_SECRET or settings.DATABASE_URL
    return hashlib.sha256(seed.encode("utf-8")).digest()


def generate_oauth_state(provider: str, redirect_path: str = "/") -> str:
    """
    Generate an HMAC-SHA256 signed state string with timestamp, provider, and nonce.
    Prevents CSRF and replay attacks.
    """
    payload = {
        "provider": provider.upper(),
        "nonce": secrets.token_hex(16),
        "ts": int(time.time()),
        "path": redirect_path or "/",
    }
    raw_json = json.dumps(payload, separators=(",", ":"))
    b64_payload = base64.urlsafe_b64encode(raw_json.encode("utf-8")).decode("ascii").rstrip("=")
    signature = hmac.new(_get_signing_key(), b64_payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{signature}"


def verify_oauth_state(state: str, expected_provider: str) -> dict[str, Any]:
    """
    Validate HMAC signature, expiration timestamp, and matching provider.
    Returns the parsed payload dict on success; raises OAuthVerificationError on failure.
    """
    if not state or "." not in state:
        raise OAuthVerificationError("Invalid OAuth state parameter")

    b64_payload, signature = state.rsplit(".", 1)
    expected_sig = hmac.new(_get_signing_key(), b64_payload.encode("ascii"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        raise OAuthVerificationError("Invalid or tampered OAuth state signature")

    # Decode payload
    padded = b64_payload + "=" * ((4 - len(b64_payload) % 4) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception:
        raise OAuthVerificationError("Corrupted OAuth state payload")

    # Validate provider
    if data.get("provider") != expected_provider.upper():
        raise OAuthVerificationError("OAuth state provider mismatch")

    # Validate expiration
    ts = data.get("ts", 0)
    if time.time() - ts > STATE_TTL_SECONDS:
        raise OAuthVerificationError("OAuth state has expired. Please try signing in again.")

    return data


# ---------------------------------------------------------------------------
# Google OAuth 2.0 / OpenID Connect
# ---------------------------------------------------------------------------

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"


def is_google_configured() -> bool:
    settings = get_settings()
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def get_google_auth_url(state: str, code_challenge: str | None = None) -> str:
    """Build the official Google OAuth 2.0 authorization URL."""
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID:
        raise OAuthConfigurationError("GOOGLE_CLIENT_ID is not configured")

    params: dict[str, str] = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"


async def exchange_google_code(code: str, code_verifier: str | None = None) -> dict[str, Any]:
    """Exchange authorization code with Google token endpoint."""
    settings = get_settings()
    if not is_google_configured():
        raise OAuthConfigurationError("Google OAuth credentials are not configured")

    data: dict[str, str] = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(GOOGLE_TOKEN_ENDPOINT, data=data)
        if response.status_code != 200:
            raise OAuthVerificationError("Failed to exchange authorization code with Google")
        return response.json()


async def get_google_user_info(access_token: str) -> dict[str, Any]:
    """Retrieve and verify user identity from Google UserInfo endpoint."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(GOOGLE_USERINFO_ENDPOINT, headers=headers)
        if response.status_code != 200:
            raise OAuthVerificationError("Failed to fetch verified user profile from Google")
        return response.json()


# ---------------------------------------------------------------------------
# DigiLocker / MeriPehchaan Official OAuth 2.0 Integration
# ---------------------------------------------------------------------------

def is_digilocker_configured() -> bool:
    settings = get_settings()
    return bool(settings.DIGILOCKER_CLIENT_ID and settings.DIGILOCKER_CLIENT_SECRET)


def get_digilocker_auth_url(state: str, code_challenge: str) -> str:
    """
    Build the official DigiLocker / MeriPehchaan OAuth 2.0 authorization URL.
    Uses official endpoint: /public/oauth2/1/authorize
    Requires PKCE code_challenge with method S256.
    """
    settings = get_settings()
    if not settings.DIGILOCKER_CLIENT_ID:
        raise OAuthConfigurationError("DIGILOCKER_CLIENT_ID is not configured")

    base = settings.DIGILOCKER_BASE_URL.rstrip("/")
    auth_endpoint = f"{base}/public/oauth2/1/authorize"

    params = {
        "response_type": "code",
        "client_id": settings.DIGILOCKER_CLIENT_ID,
        "redirect_uri": settings.DIGILOCKER_REDIRECT_URI,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{auth_endpoint}?{urlencode(params)}"


async def exchange_digilocker_code(code: str, code_verifier: str) -> dict[str, Any]:
    """
    Exchange authorization code with DigiLocker token endpoint.
    Uses official endpoint: /public/oauth2/1/token
    """
    settings = get_settings()
    if not is_digilocker_configured():
        raise OAuthConfigurationError("DigiLocker OAuth credentials are not configured")

    base = settings.DIGILOCKER_BASE_URL.rstrip("/")
    token_endpoint = f"{base}/public/oauth2/1/token"

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.DIGILOCKER_CLIENT_ID,
        "client_secret": settings.DIGILOCKER_CLIENT_SECRET,
        "redirect_uri": settings.DIGILOCKER_REDIRECT_URI,
        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(token_endpoint, data=data)
        if response.status_code != 200:
            raise OAuthVerificationError("Failed to exchange authorization code with DigiLocker")
        return response.json()


async def get_digilocker_user_info(access_token: str) -> dict[str, Any]:
    """
    Retrieve user identity from DigiLocker user endpoint.
    Uses official endpoint: /public/oauth2/1/user
    """
    settings = get_settings()
    base = settings.DIGILOCKER_BASE_URL.rstrip("/")
    user_endpoint = f"{base}/public/oauth2/1/user"

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(user_endpoint, headers=headers)
        if response.status_code != 200:
            raise OAuthVerificationError("Failed to fetch verified user profile from DigiLocker")
        return response.json()
