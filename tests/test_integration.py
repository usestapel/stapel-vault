"""Opt-in smoke test against a real OpenBao / HashiCorp Vault.

Skipped unless ``VAULT_ADDR`` and ``VAULT_TOKEN`` are set. Run explicitly::

    # start a dev OpenBao (in-memory, root token "root"):
    docker run --rm -p 8200:8200 -e BAO_DEV_ROOT_TOKEN_ID=root \
        openbao/openbao server -dev
    # (HashiCorp Vault works identically: hashicorp/vault, VAULT_DEV_ROOT_TOKEN_ID)

    export VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root
    pytest -m vault_integration

The test writes a KV v2 secret at the default bundle path and reads it back
through the provider, exercising the real urllib transport end-to-end.
"""
import os

import pytest

from stapel_vault.client import VaultHTTPClient
from stapel_vault.provider import VaultSecretProvider

pytestmark = pytest.mark.vault_integration

_HAVE_VAULT = bool(os.environ.get("VAULT_ADDR") and os.environ.get("VAULT_TOKEN"))


@pytest.mark.skipif(not _HAVE_VAULT, reason="set VAULT_ADDR + VAULT_TOKEN to run")
def test_write_then_read_roundtrip():
    addr = os.environ["VAULT_ADDR"]
    token = os.environ["VAULT_TOKEN"]
    client = VaultHTTPClient(addr, timeout=5.0)

    # Ensure the KV v2 mount exists at "secret" (dev servers mount it already).
    client.request(
        "POST", "v1/secret/data/stapel/app", token=token,
        json_body={"data": {"DJANGO_SECRET_KEY": "integration-value", "OTHER": "x"}},
    )

    provider = VaultSecretProvider(auth_method="token", token=token, addr=addr)
    assert provider.get("DJANGO_SECRET_KEY") == "integration-value"
    assert provider.get("OTHER") == "x"
    assert provider.get("ABSENT_KEY") is None
