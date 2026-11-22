"""
settings.py — User settings management for OpenClip.

Stores key-value configuration in the SQLite ``settings`` table.
API keys are encrypted at rest using Fernet symmetric encryption.

How it works:
    A random Fernet key is generated on first use and stored next to the
    database as ``.secret_key`` (file mode 0600). Values written by older
    versions, which derived the key from ``uuid.getnode()``, can still be
    decrypted on machines where that value is stable. If the database is
    moved without its ``.secret_key`` the API key must be re-entered.
"""

import os
import uuid
import base64
import hashlib
import logging
from typing import Optional, Any, Dict

from cryptography.fernet import Fernet, MultiFernet, InvalidToken # type: ignore

import database # type: ignore


logger = logging.getLogger(__name__)

_DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-5-5",
    "gemini": "gemini-3.5-flash",
    "ollama": "llama3",
}

# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _key_file_path() -> str:
    """Secret key lives next to the SQLite database (e.g. data/.secret_key)."""
    return os.path.join(os.path.dirname(os.path.abspath(database.DB_PATH)), ".secret_key")


def _load_or_create_file_key() -> bytes:
    """
    Load the persistent Fernet key, creating it (mode 0600) on first use.

    ``uuid.getnode()`` is not reliable: when Python cannot read a hardware
    address (common on macOS) it returns a *random* value per process, so a
    key derived from it changes on every restart and saved API keys become
    undecryptable. A random key stored on disk is stable.
    """
    path = _key_file_path()
    try:
        with open(path, "rb") as f:
            return f.read().strip()
    except FileNotFoundError:
        key = Fernet.generate_key()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        return key


def _legacy_machine_key() -> bytes:
    """Old key derivation, kept only so previously saved values still decrypt."""
    machine_id = str(uuid.getnode()).encode()
    return base64.urlsafe_b64encode(hashlib.sha256(machine_id).digest())


def _get_fernet() -> MultiFernet:
    """
    Return a Fernet that encrypts with the persistent file key and can
    still decrypt values written with the legacy machine-derived key.
    """
    return MultiFernet([Fernet(_load_or_create_file_key()), Fernet(_legacy_machine_key())])


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
                return "viral_word"
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

        # Fill in defaults for anything never saved, so the UI always gets
        # every field (a missing llm_model made the Settings input flip from
        # uncontrolled to controlled).
        result.setdefault("llm_provider", "openai")
        result.setdefault("llm_model", _DEFAULT_MODELS.get(result["llm_provider"], ""))
        result.setdefault("whisper_model", "base")
        result.setdefault("caption_style", "viral_word")
        result.setdefault("has_api_key", False)

    except Exception as exc:
        raise RuntimeError(f"Failed to read settings: {exc}") from exc
    finally:
        await conn.close()

    return result
