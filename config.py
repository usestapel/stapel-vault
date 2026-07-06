"""Bootstrap-tolerant configuration for the Vault facade.

Vault connection config (address, auth, mount) legitimately lives in the
**environment / Kubernetes**, not in Django settings — because a production
settings module resolves ``SECRET_KEY`` through Vault *before* ``django.setup()``
runs. So every key is resolved env-first, with an optional ``STAPEL_VAULT``
Django-settings override that only applies once Django is configured.

Resolution order per key: ``STAPEL_VAULT[<key>]`` (when Django is configured)
→ environment variable (the ``VAULT_*`` name) → default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .exceptions import VaultConfigError

# Django-settings namespace for optional overrides (post-setup only).
SETTINGS_NAMESPACE = "STAPEL_VAULT"

# Default location of the Kubernetes service-account JWT (projected token).
DEFAULT_K8S_JWT_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"  # noqa: S105


def _setting(key: str) -> str | None:
    """Value from ``STAPEL_VAULT[key]`` if Django is configured, else None."""
    try:
        from django.conf import settings

        ns = getattr(settings, SETTINGS_NAMESPACE, None) or {}
        val = ns.get(key)
        return None if val is None else str(val)
    except Exception:
        # Django not configured (bootstrap) — env is the source of truth.
        return None


def _resolve(key: str, env: str, default: str | None = None) -> str | None:
    val = _setting(key)
    if val is not None:
        return val
    val = os.environ.get(env)
    if val is not None and val != "":
        return val
    return default


@dataclass(frozen=True)
class VaultConfig:
    """Resolved connection + mapping configuration for :class:`VaultSecretProvider`."""

    addr: str
    namespace: str | None
    kv_mount: str
    path_prefix: str
    app: str
    kv_version: int | None
    timeout: float
    bundle_cache_ttl: float
    # auth
    auth_method: str  # "token" | "kubernetes" | "approle"
    token: str | None
    auth_mount: str
    k8s_role: str | None
    k8s_jwt_path: str
    role_id: str | None
    secret_id: str | None
    # optional explicit per-name mapping: {"NAME": "path#key", ...}
    secret_map: dict[str, str]


def _auto_auth_method() -> str:
    """Pick an auth method from what is present in the environment/settings."""
    if _resolve("TOKEN", "VAULT_TOKEN"):
        return "token"
    if _resolve("ROLE_ID", "VAULT_ROLE_ID"):
        return "approle"
    if _resolve("K8S_ROLE", "VAULT_K8S_ROLE") or os.path.exists(
        _resolve("K8S_JWT_PATH", "VAULT_K8S_JWT_PATH", DEFAULT_K8S_JWT_PATH) or ""
    ):
        return "kubernetes"
    return "token"


def _default_auth_mount(method: str) -> str:
    return {"kubernetes": "kubernetes", "approle": "approle", "token": "token"}[method]


def load_config(**overrides) -> VaultConfig:
    """Resolve a :class:`VaultConfig`. Explicit *overrides* win over everything.

    Raises :class:`VaultConfigError` for an unknown auth method (missing
    required credentials are surfaced lazily at auth time so a misconfigured
    non-token method still constructs — the boot error then names Vault).
    """
    import json

    def ov(name, resolver):
        return overrides[name] if name in overrides else resolver()

    auth_method = ov("auth_method", lambda: _resolve("AUTH_METHOD", "VAULT_AUTH_METHOD") or _auto_auth_method())
    if auth_method not in ("token", "kubernetes", "approle"):
        raise VaultConfigError(
            f"unknown VAULT auth method {auth_method!r} (expected token, "
            "kubernetes or approle)"
        )

    raw_map = ov("secret_map", lambda: _resolve("SECRET_MAP", "VAULT_SECRET_MAP"))
    if isinstance(raw_map, str):
        try:
            secret_map = dict(json.loads(raw_map))
        except (ValueError, TypeError) as exc:
            raise VaultConfigError(f"VAULT_SECRET_MAP is not valid JSON: {exc}") from exc
    else:
        secret_map = dict(raw_map or {})

    def _int(name, env):
        v = _resolve(name, env)
        return int(v) if v not in (None, "") else None

    def _float(name, env, default):
        v = _resolve(name, env)
        return float(v) if v not in (None, "") else default

    return VaultConfig(
        addr=ov("addr", lambda: _resolve("ADDR", "VAULT_ADDR", "http://127.0.0.1:8200")).rstrip("/"),
        namespace=ov("namespace", lambda: _resolve("NAMESPACE", "VAULT_NAMESPACE")),
        kv_mount=ov("kv_mount", lambda: _resolve("KV_MOUNT", "VAULT_KV_MOUNT", "secret")),
        path_prefix=ov("path_prefix", lambda: _resolve("SECRET_PATH_PREFIX", "VAULT_SECRET_PATH_PREFIX", "stapel")),
        app=ov("app", lambda: _resolve("SECRET_APP", "VAULT_SECRET_APP", "app")),
        kv_version=ov("kv_version", lambda: _int("KV_VERSION", "VAULT_KV_VERSION")),
        timeout=ov("timeout", lambda: _float("HTTP_TIMEOUT", "VAULT_HTTP_TIMEOUT", 5.0)),
        bundle_cache_ttl=ov("bundle_cache_ttl", lambda: _float("BUNDLE_CACHE_TTL", "VAULT_BUNDLE_CACHE_TTL", 0.0)),
        auth_method=auth_method,
        token=ov("token", lambda: _resolve("TOKEN", "VAULT_TOKEN")),
        auth_mount=ov("auth_mount", lambda: _resolve("AUTH_MOUNT", "VAULT_AUTH_MOUNT") or _default_auth_mount(auth_method)),
        k8s_role=ov("k8s_role", lambda: _resolve("K8S_ROLE", "VAULT_K8S_ROLE")),
        k8s_jwt_path=ov("k8s_jwt_path", lambda: _resolve("K8S_JWT_PATH", "VAULT_K8S_JWT_PATH", DEFAULT_K8S_JWT_PATH)),
        role_id=ov("role_id", lambda: _resolve("ROLE_ID", "VAULT_ROLE_ID")),
        secret_id=ov("secret_id", lambda: _resolve("SECRET_ID", "VAULT_SECRET_ID")),
        secret_map=secret_map,
    )


__all__ = ["DEFAULT_K8S_JWT_PATH", "SETTINGS_NAMESPACE", "VaultConfig", "load_config"]
