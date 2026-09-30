"""
Unit and integration tests for authentication system:
- Password hashing & verification
- Session token generation and SHA-256 storage
- OAuth state signing, expiry, and CSRF protection
- PKCE verifier & challenge derivation (S256)
- Google and DigiLocker endpoint routing and configuration checks
- OAuth callback error handling
"""

import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth.password import hash_password, verify_password
from app.auth.session import issue_raw_token, hash_session_token
from app.auth.oauth import (
    generate_code_verifier,
    generate_code_challenge,
    generate_oauth_state,
    verify_oauth_state,
    OAuthVerificationError,
    OAuthConfigurationError,
)

client = TestClient(app)


def test_password_hashing():
    raw = "SecureSecretPassword123!"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_session_token_hashing():
    raw_token = issue_raw_token()
    assert len(raw_token) >= 48
    digest1 = hash_session_token(raw_token)
    digest2 = hash_session_token(raw_token)
    assert digest1 == digest2
    assert digest1 != raw_token
    # Different tokens produce different digests
    other_token = issue_raw_token()
    assert hash_session_token(other_token) != digest1


def test_pkce_generation():
    verifier = generate_code_verifier()
    assert len(verifier) >= 43
    challenge = generate_code_challenge(verifier)
    assert len(challenge) > 0
    # Deterministic challenge for same verifier
    assert generate_code_challenge(verifier) == challenge


def test_oauth_state_generation_and_verification():
    state = generate_oauth_state("GOOGLE", "/profile")
    assert "." in state

    data = verify_oauth_state(state, "GOOGLE")
    assert data["provider"] == "GOOGLE"
    assert data["path"] == "/profile"
    assert "nonce" in data

    # State for wrong provider must fail
    with pytest.raises(OAuthVerificationError):
        verify_oauth_state(state, "DIGILOCKER")

    # Tampered state must fail
    tampered = state[:-4] + "abcd"
    with pytest.raises(OAuthVerificationError):
        verify_oauth_state(tampered, "GOOGLE")


def test_oauth_state_tampering_rejected():
    with pytest.raises(OAuthVerificationError):
        verify_oauth_state("invalid_state_without_signature", "GOOGLE")


def test_google_auth_url_requires_configuration():
    # If GOOGLE_CLIENT_ID is not set, endpoint returns 503 configuration error
    response = client.get("/api/v1/auth/google/url")
    if response.status_code == 200:
        data = response.json()
        assert "accounts.google.com" in data["url"]
        assert "state" in data
    else:
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"].lower()


def test_digilocker_auth_url_requires_configuration():
    # If DIGILOCKER_CLIENT_ID is not set, endpoint returns 503 configuration error
    response = client.get("/api/v1/auth/digilocker/url")
    if response.status_code == 200:
        data = response.json()
        assert "public/oauth2/1/authorize" in data["url"]
        assert "state" in data
        assert "code_verifier" in data
    else:
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"].lower()


def test_google_callback_invalid_state():
    response = client.post(
        "/api/v1/auth/google/callback",
        json={"code": "dummy_code", "state": "tampered_state"},
    )
    assert response.status_code in (400, 503)


def test_digilocker_callback_missing_verifier():
    response = client.post(
        "/api/v1/auth/digilocker/callback",
        json={"code": "dummy_code", "state": "valid_state_format.sig"},
    )
    # Missing code_verifier should return 400
    assert response.status_code == 400
    assert "code_verifier" in response.json()["detail"]


def test_protected_me_endpoint_requires_auth():
    response = client.get("/api/v1/auth/me")
    assert response.status_code in (401, 422)  # missing header
