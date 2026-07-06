"""VaultHTTPClient urllib layer — mocked urlopen, error mapping."""
import io
import json
import urllib.error
from unittest import mock

import pytest

import stapel_vault.client as client_mod
from stapel_vault.client import VaultHTTPClient
from stapel_vault.exceptions import VaultTransportError


class _Resp:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _client():
    return VaultHTTPClient("http://vault.test:8200", namespace="ns", timeout=1.0)


def test_get_200_parses_json():
    payload = {"data": {"data": {"K": "v"}}}
    with mock.patch.object(client_mod.urllib.request, "urlopen",
                           return_value=_Resp(200, json.dumps(payload).encode())):
        resp = _client().request("GET", "v1/secret/data/x", token="t")
    assert resp.status == 200
    assert resp.data == payload


def test_sets_token_and_namespace_headers():
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = req.headers
        captured["url"] = req.full_url
        return _Resp(200, b"{}")

    with mock.patch.object(client_mod.urllib.request, "urlopen", side_effect=fake_urlopen):
        _client().request("GET", "/v1/x", token="tok")
    # urllib capitalizes header keys
    assert captured["headers"]["X-vault-token"] == "tok"
    assert captured["headers"]["X-vault-namespace"] == "ns"
    assert captured["url"] == "http://vault.test:8200/v1/x"


def test_404_returned_not_raised():
    err = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b'{"errors":[]}'))
    with mock.patch.object(client_mod.urllib.request, "urlopen", side_effect=err):
        resp = _client().request("GET", "v1/x", token="t")
    assert resp.status == 404


def test_5xx_raises_transport_error():
    err = urllib.error.HTTPError("u", 503, "unavail", {}, io.BytesIO(b'{"errors":["down"]}'))
    with mock.patch.object(client_mod.urllib.request, "urlopen", side_effect=err):
        with pytest.raises(VaultTransportError) as exc:
            _client().request("GET", "v1/x", token="t")
    assert exc.value.status == 503


def test_urlerror_raises_transport_error():
    with mock.patch.object(client_mod.urllib.request, "urlopen",
                           side_effect=urllib.error.URLError("refused")):
        with pytest.raises(VaultTransportError):
            _client().request("GET", "v1/x", token="t")


def test_non_json_body_raises_transport_error():
    with mock.patch.object(client_mod.urllib.request, "urlopen",
                           return_value=_Resp(200, b"<html>not json</html>")):
        with pytest.raises(VaultTransportError):
            _client().request("GET", "v1/x", token="t")


def test_post_sends_json_body():
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = req.data
        captured["method"] = req.get_method()
        return _Resp(200, b'{"auth":{"client_token":"x"}}')

    with mock.patch.object(client_mod.urllib.request, "urlopen", side_effect=fake_urlopen):
        _client().request("POST", "v1/auth/approle/login", json_body={"role_id": "r"})
    assert captured["method"] == "POST"
    assert json.loads(captured["data"]) == {"role_id": "r"}
