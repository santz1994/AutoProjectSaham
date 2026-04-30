"""Credential vault utilities: asymmetric/symmetric encryption helpers.

This module provides a simple runtime-only decryption helper using Fernet
from the `cryptography` package. The master key must be injected via env
variable (not stored on disk) for security.
"""
from __future__ import annotations

import os

try:
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover - optional dependency
    Fernet = None  # type: ignore


class CredentialVault:
    def __init__(self, master_key_env_var: str = "VAULT_MASTER_KEY"):
        master_key = os.environ.get(master_key_env_var)
        if not master_key:
            raise RuntimeError(
                "CRITICAL: Master Key for vault decryption not found in environment"
            )
        if Fernet is None:
            raise RuntimeError("cryptography package required for CredentialVault")
        self.cipher = Fernet(master_key.encode())

    def decrypt_broker_pin(self, encrypted_pin_b64: str) -> str:
        """Decrypt a base64-encoded Fernet token.

        The decrypted PIN is returned as a string and should not be stored
        in persistent variables.
        """
        decrypted = self.cipher.decrypt(encrypted_pin_b64.encode())
        return decrypted.decode("utf-8")
