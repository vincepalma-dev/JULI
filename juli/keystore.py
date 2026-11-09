"""
API keys in the OS keychain (service "juli"), with an environment fallback.

Lookup order: keychain, then the process environment, then ./.env.
Nothing here writes os.environ or logs a key.
"""

import os
from functools import lru_cache
from pathlib import Path

import keyring
from dotenv import dotenv_values
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE = "juli"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class KeystoreUnavailable(RuntimeError):
    """The OS keychain can't be used on this machine."""


def env_var(provider: str) -> str:
    """The environment variable that can hold a provider's key."""
    return f"{provider.upper()}_API_KEY"


@lru_cache(maxsize=1)
def _dotenv() -> dict:
    return dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}


def get_key(provider: str) -> str | None:
    try:
        key = keyring.get_password(SERVICE, provider)
    except KeyringError:
        key = None
    if key:
        return key
    var = env_var(provider)
    return os.environ.get(var) or _dotenv().get(var) or None


def set_key(provider: str, key: str) -> None:
    try:
        keyring.set_password(SERVICE, provider, key)
    except KeyringError as e:
        raise KeystoreUnavailable(str(e)) from None


def delete_key(provider: str) -> None:
    try:
        keyring.delete_password(SERVICE, provider)
    except PasswordDeleteError:
        pass  # nothing stored
    except KeyringError as e:
        raise KeystoreUnavailable(str(e)) from None


def key_hint(key: str | None) -> str:
    """A safe display form of a key: "••••abcd", or "" when there is none."""
    if not key:
        return ""
    return "••••" + key[-4:] if len(key) >= 8 else "••••"
