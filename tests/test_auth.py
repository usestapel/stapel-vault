"""Auth methods: token, kubernetes, approle — login, token caching, renewal."""
from unittest import mock

import pytest

import stapel_vault.auth as auth_mod
from stapel_vault.auth import Authenticator
from stapel_vault.config import load_config
from stapel_vault.exceptions import VaultAuthError, VaultConfigError
from tests._helpers import FakeClient, login_response
from stapel_vault.client import VaultResponse


def test_token_auth_uses_configured_token():
    cfg = load_config(auth_method="token", token="root")
    a = Authenticator(cfg, FakeClient(lambda *a: None))
    assert a.token() == "root"


def test_token_auth_missing_token_raises():
    cfg = load_config(auth_method="token", token=None)
    a = Authenticator(cfg, FakeClient(lambda *a: None))
    with pytest.raises(VaultConfigError):
        a.token()


def test_kubernetes_login(tmp_path):
    jwt = tmp_path / "token"
    jwt.write_text("k8s-jwt-abc")
    cfg = load_config(
        auth_method="kubernetes", k8s_role="stapel-web", k8s_jwt_path=str(jwt),
    )
    client = FakeClient(lambda m, p, t, b: login_response("s.k8s-client-token"))
    a = Authenticator(cfg, client)
    assert a.token() == "s.k8s-client-token"
    call = client.calls[0]
    assert call["path"] == "v1/auth/kubernetes/login"
    assert call["json_body"] == {"role": "stapel-web", "jwt": "k8s-jwt-abc"}


def test_kubernetes_missing_jwt_file_raises(tmp_path):
    cfg = load_config(
        auth_method="kubernetes", k8s_role="r",
        k8s_jwt_path=str(tmp_path / "nope"),
    )
    a = Authenticator(cfg, FakeClient(lambda *a: None))
    with pytest.raises(VaultConfigError):
        a.token()


def test_approle_login():
    cfg = load_config(auth_method="approle", role_id="rid", secret_id="sid")
    client = FakeClient(lambda m, p, t, b: login_response("s.approle-token"))
    a = Authenticator(cfg, client)
    assert a.token() == "s.approle-token"
    assert client.calls[0]["json_body"] == {"role_id": "rid", "secret_id": "sid"}


def test_approle_missing_creds_raises():
    cfg = load_config(auth_method="approle", role_id="rid", secret_id=None)
    a = Authenticator(cfg, FakeClient(lambda *a: None))
    with pytest.raises(VaultConfigError):
        a.token()


def test_login_failure_raises_auth_error():
    cfg = load_config(auth_method="approle", role_id="rid", secret_id="bad")
    client = FakeClient(lambda m, p, t, b: VaultResponse(400, {"errors": ["invalid secret id"]}))
    a = Authenticator(cfg, client)
    with pytest.raises(VaultAuthError):
        a.token()


def test_token_cached_until_lease_then_renews():
    cfg = load_config(auth_method="approle", role_id="rid", secret_id="sid")
    tokens = iter(["s.first", "s.second"])
    client = FakeClient(lambda m, p, t, b: login_response(next(tokens), lease=100))
    a = Authenticator(cfg, client)

    with mock.patch.object(auth_mod.time, "monotonic", return_value=1000.0):
        assert a.token() == "s.first"
        assert a.token() == "s.first"  # cached — one login
    assert len([c for c in client.calls]) == 1

    # Past 90% of the 100s lease -> re-login.
    with mock.patch.object(auth_mod.time, "monotonic", return_value=1000.0 + 95):
        assert a.token() == "s.second"
    assert len(client.calls) == 2


def test_invalidate_forces_reauth():
    cfg = load_config(auth_method="approle", role_id="rid", secret_id="sid")
    tokens = iter(["s.a", "s.b"])
    client = FakeClient(lambda m, p, t, b: login_response(next(tokens)))
    a = Authenticator(cfg, client)
    assert a.token() == "s.a"
    a.invalidate()
    assert a.token() == "s.b"
