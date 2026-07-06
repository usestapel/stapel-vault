"""Minimal Vault / OpenBao HTTP client (stdlib ``urllib`` — no heavy deps).

Design decision (arch-stapel-vault Part 2): we do **not** depend on ``hvac``.
It is a large dependency for what we need (a couple of JSON endpoints), it
pulls its own ``requests`` stack, and this facade must be importable at
settings-bootstrap time in a control-plane process where a slim dependency
footprint matters. The OpenBao and HashiCorp Vault HTTP APIs are compatible,
so one small ``urllib`` client speaks to both. ``requests`` is avoided too —
``urllib`` is stdlib and always present, so the provider adds *zero* runtime
dependencies of its own.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .exceptions import VaultTransportError


@dataclass
class VaultResponse:
    status: int
    data: dict


class VaultHTTPClient:
    """Tiny JSON-over-HTTP client for the Vault/OpenBao API.

    Only :meth:`request` touches the network — tests mock this one method.
    """

    def __init__(self, addr: str, namespace: str | None = None, timeout: float = 5.0) -> None:
        self.addr = addr.rstrip("/")
        self.namespace = namespace
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: dict | None = None,
    ) -> VaultResponse:
        """Perform one request. Returns status + parsed JSON.

        Raises :class:`VaultTransportError` for unreachable host, timeout, a
        5xx, or an unparseable body. Application-level statuses (200, 403,
        404, …) are returned for the caller to interpret.
        """
        url = f"{self.addr}/{path.lstrip('/')}"
        body = json.dumps(json_body).encode() if json_body is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["X-Vault-Token"] = token
        if self.namespace:
            headers["X-Vault-Namespace"] = self.namespace

        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                return VaultResponse(resp.status, _parse(resp.read()))
        except urllib.error.HTTPError as exc:
            payload = _parse(exc.read() or b"")
            if exc.code >= 500:
                raise VaultTransportError(
                    f"Vault returned {exc.code} for {method} {path}: "
                    f"{payload.get('errors') or exc.reason}",
                    status=exc.code,
                ) from exc
            return VaultResponse(exc.code, payload)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise VaultTransportError(
                f"cannot reach Vault at {self.addr} ({type(exc).__name__}: {exc})"
            ) from exc


def _parse(raw: bytes) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise VaultTransportError(f"Vault response was not JSON: {exc}") from exc
    return value if isinstance(value, dict) else {"data": value}


__all__ = ["VaultHTTPClient", "VaultResponse"]
