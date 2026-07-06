"""Logical secret name → Vault KV v2 location.

The convention (documented in MODULE.md): every logical secret name is a
**key inside one KV v2 secret** — the service's "bundle" — living at

    <kv_mount>/data/<path_prefix>/<app>

So with the defaults (``kv_mount=secret``, ``path_prefix=stapel``,
``app=app``), the logical name ``DJANGO_SECRET_KEY`` is read from

    GET  <addr>/v1/secret/data/stapel/app
    ->   .data.data["DJANGO_SECRET_KEY"]

Grouping a service's secrets as keys of one KV secret is the common
operational pattern (one ``vault kv put secret/stapel/app SECRET_KEY=… …``)
and lets a single read populate the whole bundle. A deployment that prefers a
secret-per-path layout, or needs a specific name to come from elsewhere, sets
an explicit override in ``VAULT_SECRET_MAP`` (JSON), e.g.::

    {"POSTGRES_PASSWORD": "db/creds#password",
     "DJANGO_SECRET_KEY": "secret2/data/other/app#DJANGO_SECRET_KEY"}

An override value is ``"<path>#<key>"``; ``<path>`` may include its own
mount as a leading ``"<mount>/data/…"`` segment (used verbatim), otherwise it
is taken relative to the default mount.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import VaultConfig


@dataclass(frozen=True)
class KVLocation:
    """Where a logical name lives: the KV v2 read path and the data key."""

    mount: str
    path: str  # the logical path *without* the /data/ infix
    key: str

    def read_url_path(self, version: int | None) -> str:
        """The API path ``v1/<mount>/data/<path>`` (+ optional ?version=)."""
        url = f"v1/{self.mount}/data/{self.path}"
        if version is not None:
            url += f"?version={version}"
        return url


def _split_override(mount_default: str, spec: str) -> KVLocation:
    if "#" not in spec:
        raise ValueError(
            f"VAULT_SECRET_MAP entry {spec!r} must be '<path>#<key>'"
        )
    path, key = spec.rsplit("#", 1)
    mount = mount_default
    # Allow an explicit "<mount>/data/<rest>" — strip the /data/ infix so the
    # location composes it back uniformly.
    if "/data/" in path:
        head, rest = path.split("/data/", 1)
        mount, path = head, rest
    return KVLocation(mount=mount, path=path.strip("/"), key=key)


def map_name(name: str, config: VaultConfig) -> KVLocation:
    """Resolve *name* to its :class:`KVLocation` under *config*."""
    override = config.secret_map.get(name)
    if override:
        return _split_override(config.kv_mount, override)
    bundle_path = "/".join(p for p in (config.path_prefix, config.app) if p)
    return KVLocation(mount=config.kv_mount, path=bundle_path, key=name)


__all__ = ["KVLocation", "map_name"]
