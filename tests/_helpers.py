"""Shared test helpers: a scripted fake Vault HTTP client (no network)."""
from __future__ import annotations

from stapel_vault.client import VaultResponse


class FakeClient:
    """Duck-typed VaultHTTPClient: routes each request through *handler*.

    ``handler(method, path, token, json_body) -> VaultResponse``. Every call is
    appended to ``self.calls`` as a dict for assertions.
    """

    def __init__(self, handler, addr="http://vault.test:8200", namespace=None, timeout=5.0):
        self.handler = handler
        self.addr = addr
        self.namespace = namespace
        self.timeout = timeout
        self.calls = []

    def request(self, method, path, *, token=None, json_body=None):
        self.calls.append(
            {"method": method, "path": path, "token": token, "json_body": json_body}
        )
        return self.handler(method, path, token, json_body)


def kv_response(data: dict, version: int = 1) -> VaultResponse:
    return VaultResponse(200, {"data": {"data": data, "metadata": {"version": version}}})


def login_response(token: str, lease: int = 3600) -> VaultResponse:
    return VaultResponse(200, {"auth": {"client_token": token, "lease_duration": lease}})
