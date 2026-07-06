"""Vault auth methods: token (dev), kubernetes (service-account JWT), approle.

Every method produces a short-lived *client token*; :class:`Authenticator`
caches it until shortly before its lease expires and re-authenticates on
demand (the token/lease TTL is honored — the same re-read-by-TTL idea the
core seam applies to secret values). ``invalidate()`` drops the cached token
so a 403 (token expired/revoked mid-flight) triggers exactly one re-auth.

Kubernetes auth (deploy-topology phase 2): the pod's projected service-account
JWT at ``VAULT_K8S_JWT_PATH`` is exchanged at
``auth/<mount>/login`` for a Vault token bound to a Vault role. approle
(``role_id`` + ``secret_id``) is the non-k8s server option; token auth is for
local/dev.
"""
from __future__ import annotations

import threading
import time

from .client import VaultHTTPClient
from .config import VaultConfig
from .exceptions import VaultAuthError, VaultConfigError

# Re-authenticate once the token has less than this fraction of its lease left.
_RENEW_AT = 0.9
# Floor lease used when Vault reports a non-renewable/zero lease (token auth).
_MIN_LEASE = 60.0


class Authenticator:
    """Produces (and refreshes) a valid Vault client token for the configured method."""

    def __init__(self, config: VaultConfig, client: VaultHTTPClient) -> None:
        self.config = config
        self.client = client
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at: float = 0.0

    def token(self) -> str:
        """A currently-valid client token (login/renew as needed)."""
        now = time.monotonic()
        tok = self._token
        if tok is not None and self._expires_at > now:
            return tok
        with self._lock:
            if self._token is not None and self._expires_at > time.monotonic():
                return self._token
            tok, lease = self._authenticate()
            self._token = tok
            self._expires_at = time.monotonic() + max(_MIN_LEASE, lease) * _RENEW_AT
            return tok

    def invalidate(self) -> None:
        """Forget the cached token so the next :meth:`token` re-authenticates."""
        with self._lock:
            self._token = None
            self._expires_at = 0.0

    # -- per-method login ---------------------------------------------------

    def _authenticate(self) -> tuple[str, float]:
        method = self.config.auth_method
        if method == "token":
            if not self.config.token:
                raise VaultConfigError(
                    "auth method 'token' requires VAULT_TOKEN (or STAPEL_VAULT['TOKEN'])"
                )
            # A directly-supplied token has no lease we manage; treat as static.
            return self.config.token, float("inf")
        if method == "kubernetes":
            return self._login_kubernetes()
        if method == "approle":
            return self._login_approle()
        raise VaultConfigError(f"unknown auth method {method!r}")  # pragma: no cover

    def _login_kubernetes(self) -> tuple[str, float]:
        if not self.config.k8s_role:
            raise VaultConfigError(
                "auth method 'kubernetes' requires VAULT_K8S_ROLE"
            )
        try:
            with open(self.config.k8s_jwt_path, encoding="utf-8") as fh:
                jwt = fh.read().strip()
        except OSError as exc:
            raise VaultConfigError(
                f"cannot read Kubernetes service-account JWT at "
                f"{self.config.k8s_jwt_path}: {exc}"
            ) from exc
        return self._login({"role": self.config.k8s_role, "jwt": jwt})

    def _login_approle(self) -> tuple[str, float]:
        if not (self.config.role_id and self.config.secret_id):
            raise VaultConfigError(
                "auth method 'approle' requires VAULT_ROLE_ID and VAULT_SECRET_ID"
            )
        return self._login(
            {"role_id": self.config.role_id, "secret_id": self.config.secret_id}
        )

    def _login(self, payload: dict) -> tuple[str, float]:
        path = f"v1/auth/{self.config.auth_mount}/login"
        resp = self.client.request("POST", path, json_body=payload)
        if resp.status != 200:
            errors = resp.data.get("errors") or [f"HTTP {resp.status}"]
            raise VaultAuthError(
                f"{self.config.auth_method} login to {path} failed: {errors}"
            )
        auth = resp.data.get("auth") or {}
        client_token = auth.get("client_token")
        if not client_token:
            raise VaultAuthError(f"{path} returned no client_token")
        lease = float(auth.get("lease_duration") or 0) or _MIN_LEASE
        return client_token, lease


__all__ = ["Authenticator"]
