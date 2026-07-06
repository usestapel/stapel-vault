"""VaultSecretProvider — KV reads, mapping, 403 re-auth, bundle cache, rotation."""
from unittest import mock

import pytest

import stapel_vault.provider as provider_mod
from stapel_vault.config import load_config
from stapel_vault.exceptions import VaultTransportError
from stapel_vault.provider import SecretProvider, VaultSecretProvider
from stapel_vault.client import VaultResponse
from tests._helpers import FakeClient, kv_response


def _provider(handler, **cfg_over):
    cfg = load_config(auth_method="token", token="root", **cfg_over)
    return VaultSecretProvider(config=cfg, client=FakeClient(handler))


def test_is_fail_closed_and_duck_types_seam():
    p = _provider(lambda *a: kv_response({}))
    assert p.fail_closed is True
    assert isinstance(p, SecretProvider)


def test_get_returns_value_from_bundle():
    p = _provider(lambda m, path, t, b: kv_response({"DJANGO_SECRET_KEY": "s3cr3t"}))
    assert p.get("DJANGO_SECRET_KEY") == "s3cr3t"


def test_get_reads_expected_kv_path():
    p = _provider(lambda m, path, t, b: kv_response({"K": "v"}))
    p.get("K")
    assert p.client.calls[-1]["path"] == "v1/secret/data/stapel/app"
    assert p.client.calls[-1]["token"] == "root"


def test_get_missing_key_returns_none():
    p = _provider(lambda m, path, t, b: kv_response({"OTHER": "v"}))
    assert p.get("DJANGO_SECRET_KEY") is None


def test_get_404_returns_none():
    p = _provider(lambda m, path, t, b: VaultResponse(404, {"errors": []}))
    assert p.get("ANY") is None


def test_non_dict_inner_data_is_none():
    p = _provider(lambda m, path, t, b: VaultResponse(200, {"data": {"data": None}}))
    assert p.get("ANY") is None


def test_403_triggers_reauth_and_retry():
    # First KV read 403 (expired token), second succeeds after re-auth.
    seq = iter([VaultResponse(403, {"errors": ["permission denied"]}),
                kv_response({"K": "after-reauth"})])

    def handler(m, path, t, b):
        return next(seq)

    cfg = load_config(auth_method="token", token="root")
    p = VaultSecretProvider(config=cfg, client=FakeClient(handler))
    assert p.get("K") == "after-reauth"
    # two GETs to the KV path (retry after invalidate)
    kv_calls = [c for c in p.client.calls if c["method"] == "GET"]
    assert len(kv_calls) == 2


def test_5xx_raises_transport_error():
    # FakeClient bypasses the HTTP layer, so simulate the client raising.
    def handler(m, path, t, b):
        raise VaultTransportError("boom", status=502)

    p = _provider(handler)
    with pytest.raises(VaultTransportError):
        p.get("K")


def test_other_status_raises_transport_error():
    p = _provider(lambda m, path, t, b: VaultResponse(418, {"errors": ["teapot"]}))
    with pytest.raises(VaultTransportError):
        p.get("K")


def test_versioned_read_appends_version():
    p = _provider(lambda m, path, t, b: kv_response({"K": "v"}, version=3), kv_version=3)
    p.get("K")
    assert p.client.calls[-1]["path"] == "v1/secret/data/stapel/app?version=3"


# --- bundle cache + rotation ------------------------------------------------

def test_no_bundle_cache_by_default():
    calls = {"n": 0}

    def handler(m, path, t, b):
        calls["n"] += 1
        return kv_response({"A": "1", "B": "2"})

    p = _provider(handler)
    assert p.get("A") == "1"
    assert p.get("B") == "2"
    assert calls["n"] == 2  # correctness-first: every get reads Vault


def test_bundle_cache_serves_second_read():
    calls = {"n": 0}

    def handler(m, path, t, b):
        calls["n"] += 1
        return kv_response({"A": "1", "B": "2"})

    p = _provider(handler, bundle_cache_ttl=300)
    with mock.patch.object(provider_mod.time, "monotonic", return_value=1000.0):
        assert p.get("A") == "1"
        assert p.get("B") == "2"
    assert calls["n"] == 1  # one KV read populated the whole bundle


def test_bundle_cache_expires():
    calls = {"n": 0}

    def handler(m, path, t, b):
        calls["n"] += 1
        return kv_response({"A": "1"})

    p = _provider(handler, bundle_cache_ttl=10)
    with mock.patch.object(provider_mod.time, "monotonic", return_value=1000.0):
        p.get("A")
    with mock.patch.object(provider_mod.time, "monotonic", return_value=1011.0):
        p.get("A")
    assert calls["n"] == 2


def test_invalidate_clears_bundle_cache():
    calls = {"n": 0}

    def handler(m, path, t, b):
        calls["n"] += 1
        return kv_response({"A": "old" if calls["n"] == 1 else "rotated"})

    p = _provider(handler, bundle_cache_ttl=300)
    assert p.get("A") == "old"
    p.invalidate()  # rotation hook: force re-read of the latest KV version
    assert p.get("A") == "rotated"
    assert calls["n"] == 2
