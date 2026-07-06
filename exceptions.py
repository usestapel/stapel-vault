"""Exceptions raised inside the Vault facade.

These are *internal* failures (misconfiguration, auth failure, transport
error). They are deliberately distinct from ``stapel_core.secrets``'s
``SecretUnavailable`` — that one means "the secret simply isn't there and no
default was given", which the core seam raises after a provider returns
``None``. A ``VaultError`` here means "I could not even ask Vault properly",
which propagates fail-closed through ``get_secret`` (a boot-stopping error, as
intended for a production secret store).
"""
from __future__ import annotations


class VaultError(Exception):
    """Base class for all stapel-vault failures."""


class VaultConfigError(VaultError):
    """The provider is misconfigured (missing address, unknown auth method…)."""


class VaultAuthError(VaultError):
    """Authentication to Vault/OpenBao failed (bad token, role, secret-id…)."""


class VaultTransportError(VaultError):
    """A network/HTTP-level failure talking to Vault (timeout, 5xx, unreachable)."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        self.status = status
        super().__init__(message)


__all__ = [
    "VaultAuthError",
    "VaultConfigError",
    "VaultError",
    "VaultTransportError",
]
