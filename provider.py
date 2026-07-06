"""``VaultSecretProvider`` — the stapel-core secret-provider seam, backed by
OpenBao / HashiCorp Vault (KV v2).

Wiring is one setting in the host project — **no import of stapel-core here**
(invariant I2; the provider is duck-typed against the core seam, mirrored by
:class:`SecretProvider` below). In production the *provider* is selected at
settings-bootstrap time via the ``STAPEL_SECRETS_PROVIDER`` env var, because
``SECRET_KEY`` is resolved before ``django.setup()``::

    # deployment environment (control plane only — never a workload container)
    export STAPEL_SECRETS_PROVIDER=stapel_vault.VaultSecretProvider
    export VAULT_ADDR=https://vault.internal:8200
    export VAULT_K8S_ROLE=stapel-web            # kubernetes auth (phase 2)

Once Django is up, ``STAPEL_SECRETS['PROVIDER']`` may point here too. Either
way ``stapel_core.secrets.get_secret("DJANGO_SECRET_KEY")`` reaches Vault.

``fail_closed = True``: a missing secret makes the core seam raise
``SecretUnavailable`` (a production secret that isn't there is a hard boot
failure, never a silent ``None``). A transport/auth failure raises a
``VaultError`` that likewise propagates fail-closed.
"""
from __future__ import annotations

import threading
import time
from typing import Protocol, runtime_checkable

from .auth import Authenticator
from .client import VaultHTTPClient
from .config import VaultConfig, load_config
from .mapping import map_name


@runtime_checkable
class SecretProvider(Protocol):
    """Mirror of the ``stapel_core.secrets`` seam (documented, not imported).

    Kept in lockstep with ``stapel_core.secrets.SecretProvider``. If the
    upstream contract changes, this Protocol and :class:`VaultSecretProvider`
    move together — stapel-core is the contract owner.
    """

    fail_closed: bool

    def get(self, name: str) -> str | None: ...


class VaultSecretProvider:
    """Resolve secrets from a Vault/OpenBao KV v2 store."""

    fail_closed = True

    def __init__(self, *, config: VaultConfig | None = None, client: VaultHTTPClient | None = None, **overrides) -> None:
        self.config = config or load_config(**overrides)
        self.client = client or VaultHTTPClient(
            self.config.addr, self.config.namespace, self.config.timeout
        )
        self.auth = Authenticator(self.config, self.client)
        # Optional per-(mount,path) bundle cache so resolving a whole app's
        # secrets at boot is one KV read. Off by default (bundle_cache_ttl=0):
        # correctness-first, since stapel-core already caches resolved values.
        self._bundle_lock = threading.Lock()
        self._bundle: dict[tuple[str, str], tuple[dict, int | None, float]] = {}

    # -- core seam ----------------------------------------------------------

    def get(self, name: str) -> str | None:
        """Return the secret value for *name*, or ``None`` if absent in Vault."""
        location = map_name(name, self.config)
        data, _version = self._read_bundle(location.mount, location.path)
        if data is None:
            return None
        value = data.get(location.key)
        return None if value is None else str(value)

    def invalidate(self) -> None:
        """Drop the provider's bundle cache (rotation hook counterpart).

        Pair with ``stapel_core.secrets.invalidate_secret()`` for eager
        rotation: that clears the core value cache, this forces the next read
        to re-fetch the latest KV version from Vault instead of a warm bundle.
        """
        with self._bundle_lock:
            self._bundle.clear()

    # -- KV v2 read ---------------------------------------------------------

    def _read_bundle(self, mount: str, path: str) -> tuple[dict | None, int | None]:
        key = (mount, path)
        ttl = self.config.bundle_cache_ttl
        if ttl > 0:
            with self._bundle_lock:
                entry = self._bundle.get(key)
                if entry is not None and entry[2] > time.monotonic():
                    return entry[0], entry[1]

        data, version = self._kv_read(mount, path)
        if data is not None and ttl > 0:
            with self._bundle_lock:
                self._bundle[key] = (data, version, time.monotonic() + ttl)
        return data, version

    def _kv_read(self, mount: str, path: str) -> tuple[dict | None, int | None]:
        from .mapping import KVLocation

        api_path = KVLocation(mount, path, "").read_url_path(self.config.kv_version)
        token = self.auth.token()
        resp = self.client.request("GET", api_path, token=token)
        if resp.status in (401, 403):
            # Token likely expired/revoked mid-flight — re-auth once and retry.
            self.auth.invalidate()
            token = self.auth.token()
            resp = self.client.request("GET", api_path, token=token)
        if resp.status == 404:
            return None, None  # no such secret/path -> core decides default vs raise
        if resp.status != 200:
            from .exceptions import VaultTransportError

            errors = resp.data.get("errors") or [f"HTTP {resp.status}"]
            raise VaultTransportError(
                f"KV read {api_path} failed: {errors}", status=resp.status
            )
        kv = resp.data.get("data") or {}
        inner = kv.get("data")
        version = (kv.get("metadata") or {}).get("version")
        return (inner if isinstance(inner, dict) else None), version


__all__ = ["SecretProvider", "VaultSecretProvider"]
