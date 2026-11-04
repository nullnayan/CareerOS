"""
Token encryption utility for storing sensitive credentials (GitHub tokens)
at rest in PostgreSQL.

Uses Fernet symmetric encryption from the `cryptography` library.
The encryption key lives in .env as TOKEN_ENCRYPTION_KEY — never committed.

Why encrypt at rest?
- Even in local dev, storing raw OAuth tokens in the DB is a bad habit.
- If the DB is ever leaked or accessed improperly, tokens are useless
  without the separate encryption key.
- In production, this key would live in a secrets manager (Vault, AWS SSM).
"""

import os
import base64
import hashlib
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()


def _get_fernet() -> Fernet:
    """
    Derive a valid Fernet key from TOKEN_ENCRYPTION_KEY.
    Fernet requires a 32-byte URL-safe base64-encoded key.
    We hash whatever string the user provides to get a consistent 32 bytes.
    """
    raw_key = os.getenv("TOKEN_ENCRYPTION_KEY", "")
    if not raw_key or raw_key == "generate_a_real_key_before_using":
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is not set or is still the placeholder. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\" "
            "and add it to your .env file."
        )
    # Hash the raw key to get exactly 32 bytes, then base64-encode for Fernet
    hashed = hashlib.sha256(raw_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(hashed)
    return Fernet(fernet_key)


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string. Returns a base64-encoded ciphertext string."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a previously encrypted token string."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
