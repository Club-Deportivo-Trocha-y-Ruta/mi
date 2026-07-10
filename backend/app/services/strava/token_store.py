"""Fernet encryption for Strava OAuth tokens at rest (specs/025-strava-activity-sync).

Inputs: ``encrypt_token`` takes a plaintext access/refresh token string;
``decrypt_token`` takes ciphertext bytes previously produced by
``encrypt_token``.
Outputs: ``encrypt_token`` returns ciphertext bytes (stored in the
``strava_connections.access_token_enc`` / ``refresh_token_enc`` VARBINARY
columns); ``decrypt_token`` returns the original plaintext string.
Side effects: none — both functions are pure over
``settings.strava_token_encryption_key``; no I/O, no logging.

Token values are third-party OAuth credentials for minors' accounts and MUST
NEVER be logged by this module or its callers (Ley 1581 minors-privacy gate,
see AGENTS constitution). Callers should log only numeric/opaque identifiers
(e.g. ``athlete_id``, ``strava_athlete_id``), never token contents.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import settings


class TokenEncryptionError(RuntimeError):
    """Raised when ``STRAVA_TOKEN_ENCRYPTION_KEY`` is missing or malformed.

    Never includes the offending key value in the message.
    """


@lru_cache(maxsize=1)
def _fernet_for_key(key: str) -> Fernet:
    """Build (and cache) the ``Fernet`` instance for ``key``.

    Caching is keyed by the key string itself (not a global singleton), so
    tests that monkeypatch ``settings.strava_token_encryption_key`` get a
    fresh, correctly-keyed instance instead of a stale cached one.
    """
    if not key:
        raise TokenEncryptionError(
            "STRAVA_TOKEN_ENCRYPTION_KEY no está configurada. Generar con: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise TokenEncryptionError(
            "STRAVA_TOKEN_ENCRYPTION_KEY inválida: debe ser una clave Fernet "
            "urlsafe-base64 de 32 bytes."
        ) from exc


def _fernet() -> Fernet:
    return _fernet_for_key(settings.strava_token_encryption_key)


def encrypt_token(plaintext: str) -> bytes:
    """Encrypt ``plaintext`` (an access or refresh token) with Fernet.

    Raises ``TokenEncryptionError`` if the encryption key is missing/invalid,
    or ``ValueError`` if ``plaintext`` is empty.
    """
    if not plaintext:
        raise ValueError("token vacío: nada que cifrar")
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_token(ciphertext: bytes) -> str:
    """Decrypt ``ciphertext`` previously produced by ``encrypt_token``.

    Raises ``TokenEncryptionError`` if the encryption key is missing/invalid.
    Raises ``cryptography.fernet.InvalidToken`` if ``ciphertext`` is corrupt,
    truncated, or was encrypted with a different key.
    """
    return _fernet().decrypt(bytes(ciphertext)).decode("utf-8")
