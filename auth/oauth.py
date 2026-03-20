"""
PatrAI — OAuth2 PKCE auth manager.

Implements the full OAuth2 PKCE flow for Google authentication,
Fernet-based token encryption, and SQLite-backed token persistence.

Security rules:
- NEVER log token values, access_token, refresh_token, or ENCRYPTION_KEY.
- All secrets are read from config (which reads from environment variables).
"""
import base64
import hashlib
import json
import logging
import os
import secrets
import urllib.parse

import requests
from cryptography.fernet import Fernet

import config
from database import get_db

logger = logging.getLogger(__name__)

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPES = " ".join([
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
])


def _get_fernet() -> Fernet:
    """Return a Fernet instance using the configured ENCRYPTION_KEY."""
    return Fernet(config.ENCRYPTION_KEY.encode())


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def start_pkce_flow() -> tuple[str, str, str]:
    """
    Begin the OAuth2 PKCE authorization flow.

    Returns:
        (auth_url, code_verifier, state)
        - auth_url: Google authorization URL to redirect the user to
        - code_verifier: random secret to be used in exchange_code()
        - state: random nonce for CSRF protection
    """
    # Generate a cryptographically random code_verifier (43-128 URL-safe chars per RFC 7636)
    code_verifier = secrets.token_urlsafe(96)[:128]  # token_urlsafe gives URL-safe chars

    # code_challenge = BASE64URL(SHA256(code_verifier)), no padding
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    # Random state nonce for CSRF protection
    state = secrets.token_urlsafe(32)

    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "scope": _SCOPES,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "state": state,
    }
    auth_url = f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    logger.info("PKCE flow started; state=%s", state)
    return auth_url, code_verifier, state


# ---------------------------------------------------------------------------
# Token exchange / refresh
# ---------------------------------------------------------------------------

def exchange_code(code: str, verifier: str) -> dict:
    """
    Exchange an authorization code for tokens.

    Args:
        code: The authorization code received from Google.
        verifier: The code_verifier generated in start_pkce_flow().

    Returns:
        Token dict containing access_token, refresh_token, expires_in, etc.
    """
    payload = {
        "code": code,
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
    }
    response = requests.post(_GOOGLE_TOKEN_URL, data=payload, timeout=30)
    response.raise_for_status()
    token_dict = response.json()
    logger.info("Authorization code exchanged successfully")
    # NEVER log token values
    return token_dict


def refresh_token(token_dict: dict) -> dict:
    """
    Refresh an expired access token using the stored refresh token.

    Args:
        token_dict: Token dict containing at least a 'refresh_token' key.

    Returns:
        Updated token dict with a new access_token (and possibly new refresh_token).
    """
    payload = {
        "refresh_token": token_dict["refresh_token"],
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "grant_type": "refresh_token",
    }
    response = requests.post(_GOOGLE_TOKEN_URL, data=payload, timeout=30)
    response.raise_for_status()
    updated = response.json()
    # Preserve the original refresh_token if Google doesn't return a new one
    if "refresh_token" not in updated:
        updated["refresh_token"] = token_dict["refresh_token"]
    logger.info("Access token refreshed successfully")
    # NEVER log token values
    return updated


# ---------------------------------------------------------------------------
# Encryption / decryption
# ---------------------------------------------------------------------------

def encrypt_token(token_json: str) -> bytes:
    """
    Encrypt a token JSON string using Fernet symmetric encryption.

    Args:
        token_json: JSON string representation of the token dict.

    Returns:
        Fernet ciphertext bytes.
    """
    return _get_fernet().encrypt(token_json.encode())


def decrypt_token(ciphertext: bytes) -> str:
    """
    Decrypt Fernet ciphertext back to a token JSON string.

    Args:
        ciphertext: Fernet-encrypted bytes.

    Returns:
        Plaintext JSON string.
    """
    return _get_fernet().decrypt(ciphertext).decode()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_token(service: str, token_dict: dict) -> None:
    """
    Encrypt and upsert a token dict into the oauth_tokens table.

    Args:
        service: Service identifier (e.g. 'google').
        token_dict: Token dict to persist.
    """
    token_json = json.dumps(token_dict)
    ciphertext = encrypt_token(token_json)
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO oauth_tokens (service, ciphertext, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(service) DO UPDATE SET
                ciphertext = excluded.ciphertext,
                updated_at = excluded.updated_at
            """,
            (service, ciphertext),
        )
        conn.commit()
        logger.info("Token saved for service=%s", service)
    finally:
        conn.close()


def load_token(service: str) -> dict | None:
    """
    Load and decrypt a token dict from the oauth_tokens table.

    Args:
        service: Service identifier (e.g. 'google').

    Returns:
        Decrypted token dict, or None if no token is stored for the service.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT ciphertext FROM oauth_tokens WHERE service = ?",
            (service,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        logger.info("No token found for service=%s", service)
        return None

    token_json = decrypt_token(bytes(row["ciphertext"]))
    return json.loads(token_json)
