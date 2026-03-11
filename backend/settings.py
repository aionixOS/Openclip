"""
settings.py — User settings management for OpenClip.

Stores key-value configuration in the SQLite ``settings`` table.
API keys are encrypted at rest using Fernet symmetric encryption
with a key derived deterministically from the machine's UUID.

How it works:
    The machine's MAC-based node id (``uuid.getnode()``) is hashed with
    SHA-256 and base64-encoded to produce a stable Fernet key.  This
    means the encrypted data is tied to the physical machine — if the
    database is moved to another device the API key will need to be
    re-entered.
"""

import uuid
import base64
import hashlib
import logging
from typing import Optional, Any, Dict

from cryptography.fernet import Fernet, InvalidToken # type: ignore

import database # type: ignore


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    """
    Derive a deterministic Fernet key from the machine's UUID.

    Returns:
        A ``Fernet`` instance ready to encrypt / decrypt.
    """
    machine_id = str(uuid.getnode()).encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(machine_id).digest())
    return Fernet(key)


def _encrypt(value: str) -> str:
    """Encrypt a plaintext string and return the token as a string."""
    return _get_fernet().encrypt(value.encode()).decode()


def _decrypt(token: str) -> str:
    """
    Decrypt a Fernet token back to plaintext.

    Returns the original string, or ``"<decryption failed>"`` if the
    token is invalid (e.g. database was moved to another machine).
    """
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except Exception: # Fallback to catch all InvalidToken subclasses since importing might fail
        logger.warning("Failed to decrypt setting — wrong machine key?")
        return "<decryption failed>"


# Keys whose values should be encrypted at rest
_ENCRYPTED_KEYS = {"llm_api_key"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_setting(key: str) -> Optional[str]:
    """
    Read a single setting by key.

    Encrypted keys (e.g. ``llm_api_key``) are decrypted automatically.

    Args:
        key: The setting key to look up.

    Returns:
        The setting value as a string, or *None* if not set.
    """
    conn = await database._get_connection()
    try:
        cursor = await conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if not row:
            if key == "caption_style":
                return "none"
            return None
        value = row[0] # type: ignore
        if key in _ENCRYPTED_KEYS and value:
            value = _decrypt(str(value)) # type: ignore
        return str(value) if value is not None else value
    except Exception as exc:
        raise RuntimeError(f"Failed to read setting '{key}': {exc}") from exc
    finally:
        await conn.close()


async def set_setting(key: str, value: str) -> None:
    """
    Create or update a setting.

    Encrypted keys (e.g. ``llm_api_key``) are stored encrypted.

    Args:
        key:   The setting key.
        value: The plaintext value to store.
    """
    store_value = _encrypt(value) if key in _ENCRYPTED_KEYS else value
    conn = await database._get_connection()
    try:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, store_value),
        )
        await conn.commit()
    except Exception as exc:
        raise RuntimeError(f"Failed to save setting '{key}': {exc}") from exc
    finally:
        await conn.close()


async def get_all_settings() -> Dict[str, Any]:
    """
    Return every setting as a flat dict.

    Encrypted values are **not** decrypted here — instead, encrypted
    keys are replaced with a ``has_<key>`` boolean so that the API
    never leaks raw secrets.

    Returns:
        Dict like ``{"llm_provider": "openai", "has_api_key": True, ...}``
    """
    result: Dict[str, Any] = {}
    conn = await database._get_connection()
    try:
        cursor = await conn.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        for row in rows:
            k, v = row["key"], row["value"]
            if k in _ENCRYPTED_KEYS:
                result[f"has_{k.replace('llm_', '')}"] = bool(v)
            else:
                result[k] = v

        if "caption_style" not in result:
            result["caption_style"] = "none"

    except Exception as exc:
        raise RuntimeError(f"Failed to read settings: {exc}") from exc
    finally:
        await conn.close()

    return result
