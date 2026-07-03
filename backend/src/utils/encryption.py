"""
Fernet encryption helpers for sensitive data at rest (e.g., OAuth tokens).

Requires ENCRYPTION_KEY environment variable set to a Fernet key.
Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet | None:
    """Get cached Fernet instance. Returns None if key not configured."""
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        logger.warning("ENCRYPTION_KEY not set — token encryption disabled")
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.error(f"Invalid ENCRYPTION_KEY: {e}")
        return None


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value. Returns plaintext unchanged if encryption not configured."""
    f = _get_fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a string value. Returns ciphertext unchanged if decryption fails
    (graceful fallback for pre-encryption data)."""
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # Value was likely stored before encryption was enabled
        return ciphertext
