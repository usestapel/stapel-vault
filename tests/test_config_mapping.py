"""Config resolution (env-first + settings override) and name->KV mapping."""
import pytest
from django.test import override_settings

from stapel_vault.config import load_config
from stapel_vault.exceptions import VaultConfigError
from stapel_vault.mapping import KVLocation, map_name


# --- mapping ----------------------------------------------------------------

def test_default_mapping_bundle():
    cfg = load_config(auth_method="token", token="t")
    loc = map_name("DJANGO_SECRET_KEY", cfg)
    assert loc == KVLocation(mount="secret", path="stapel/app", key="DJANGO_SECRET_KEY")
    assert loc.read_url_path(None) == "v1/secret/data/stapel/app"


def test_mapping_honors_prefix_app_mount():
    cfg = load_config(
        auth_method="token", token="t",
        kv_mount="kv", path_prefix="acme", app="web",
    )
    loc = map_name("POSTGRES_PASSWORD", cfg)
    assert loc.read_url_path(None) == "v1/kv/data/acme/web"
    assert loc.key == "POSTGRES_PASSWORD"


def test_versioned_read_url():
    cfg = load_config(auth_method="token", token="t", kv_version=7)
    loc = map_name("X", cfg)
    assert loc.read_url_path(cfg.kv_version) == "v1/secret/data/stapel/app?version=7"


def test_secret_map_override_relative_path():
    cfg = load_config(auth_method="token", token="t", secret_map={"DBPW": "db/creds#password"})
    loc = map_name("DBPW", cfg)
    assert loc == KVLocation(mount="secret", path="db/creds", key="password")


def test_secret_map_override_explicit_mount():
    cfg = load_config(
        auth_method="token", token="t",
        secret_map={"K": "other/data/team/app#K"},
    )
    loc = map_name("K", cfg)
    assert loc == KVLocation(mount="other", path="team/app", key="K")
    assert loc.read_url_path(None) == "v1/other/data/team/app"


def test_secret_map_bad_json_raises(monkeypatch):
    monkeypatch.setenv("VAULT_SECRET_MAP", "{not json")
    monkeypatch.setenv("VAULT_TOKEN", "t")
    with pytest.raises(VaultConfigError):
        load_config()


# --- config resolution ------------------------------------------------------

def test_env_resolution(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "https://v.example:8200/")
    monkeypatch.setenv("VAULT_TOKEN", "root-token")
    monkeypatch.setenv("VAULT_KV_MOUNT", "kv2")
    cfg = load_config()
    assert cfg.addr == "https://v.example:8200"  # trailing slash stripped
    assert cfg.auth_method == "token"  # auto-detected from VAULT_TOKEN
    assert cfg.token == "root-token"
    assert cfg.kv_mount == "kv2"


def test_auto_method_approle(monkeypatch):
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.setenv("VAULT_ROLE_ID", "rid")
    monkeypatch.setenv("VAULT_SECRET_ID", "sid")
    cfg = load_config()
    assert cfg.auth_method == "approle"
    assert cfg.auth_mount == "approle"


def test_settings_override_beats_env(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "http://env:8200")
    monkeypatch.setenv("VAULT_TOKEN", "t")
    with override_settings(STAPEL_VAULT={"ADDR": "http://settings:8200"}):
        cfg = load_config()
    assert cfg.addr == "http://settings:8200"


def test_unknown_auth_method_raises():
    with pytest.raises(VaultConfigError):
        load_config(auth_method="ldap", token="t")
