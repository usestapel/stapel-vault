# stapel-vault — MODULE

Production secret storage behind the `stapel_core.secrets` provider seam.
Backend #1: **OpenBao / HashiCorp Vault** (KV v2). Cloud secret managers
(AWS/GCP/Azure) are future backends, reached on Kubernetes via External Secrets
(see "What's not here").

## What this module provides

- `VaultSecretProvider` — the seam implementation: `get(name) -> str | None`,
  `fail_closed = True`. Reads a secret from Vault/OpenBao KV v2.
- `SecretProvider` — a Protocol **mirror** of the core seam (documented, not
  imported; invariant I2).
- Exceptions: `VaultError` / `VaultConfigError` / `VaultAuthError` /
  `VaultTransportError` (all distinct from core's `SecretUnavailable`).

## Deploy-mode map

| Mode | Provider | Secret source | Auth |
|---|---|---|---|
| **local / minimal** | `EnvSecretProvider` (core default) | `os.environ` | — |
| **prod (single host, phase 1)** | `VaultSecretProvider` | OpenBao/Vault KV v2 | `token` or `approle` |
| **prod (k8s, phase 2)** | `VaultSecretProvider` | Vault KV v2 | `kubernetes` (SA JWT) |

**What you must never do (S1 — studio-design §5):** a **workload container**
never sees Vault. Containers get only short-lived **scope tokens** from the
privilege gateway (`stapel_core.gateway`); their "secrets" (e.g. an LLM key)
are injected by the gateway/LLM-proxy at call time. `VaultSecretProvider` lives
only in the **control plane** (the app/settings process), never on the
dev/execution plane. This is a documentation + deployment constraint, not a
code check — do not set `STAPEL_SECRETS_PROVIDER=stapel_vault…` inside a
provisioned workload container's environment.

## Configuration

Resolved **env-first** (`VAULT_*`) with an optional `STAPEL_VAULT` Django
settings override — because a production settings module resolves `SECRET_KEY`
*before* `django.setup()`, so Vault's connection config must come from the
environment/Kubernetes, not from Django settings.

| Setting (`STAPEL_VAULT[key]`) | Env var | Default | Meaning |
|---|---|---|---|
| `ADDR` | `VAULT_ADDR` | `http://127.0.0.1:8200` | Vault/OpenBao base URL |
| `NAMESPACE` | `VAULT_NAMESPACE` | — | `X-Vault-Namespace` (Enterprise/OpenBao) |
| `KV_MOUNT` | `VAULT_KV_MOUNT` | `secret` | KV v2 mount |
| `SECRET_PATH_PREFIX` | `VAULT_SECRET_PATH_PREFIX` | `stapel` | bundle path prefix |
| `SECRET_APP` | `VAULT_SECRET_APP` | `app` | bundle path app segment |
| `KV_VERSION` | `VAULT_KV_VERSION` | — | pin a specific KV version (else latest) |
| `SECRET_MAP` | `VAULT_SECRET_MAP` | `{}` | per-name override JSON `{"NAME":"<path>#<key>"}` |
| `HTTP_TIMEOUT` | `VAULT_HTTP_TIMEOUT` | `5.0` | request timeout (s) |
| `BUNDLE_CACHE_TTL` | `VAULT_BUNDLE_CACHE_TTL` | `0` | provider-side bundle cache (s); 0 = off |
| `AUTH_METHOD` | `VAULT_AUTH_METHOD` | auto | `token` / `kubernetes` / `approle` |
| `TOKEN` | `VAULT_TOKEN` | — | token auth |
| `AUTH_MOUNT` | `VAULT_AUTH_MOUNT` | per method | auth mount path |
| `K8S_ROLE` | `VAULT_K8S_ROLE` | — | Vault role for kubernetes auth |
| `K8S_JWT_PATH` | `VAULT_K8S_JWT_PATH` | `/var/run/secrets/kubernetes.io/serviceaccount/token` | projected SA JWT |
| `ROLE_ID` / `SECRET_ID` | `VAULT_ROLE_ID` / `VAULT_SECRET_ID` | — | approle auth |

## Name → KV mapping

A logical name is a **key inside one KV v2 secret** (the service bundle) at
`<KV_MOUNT>/data/<SECRET_PATH_PREFIX>/<SECRET_APP>`. With defaults,
`DJANGO_SECRET_KEY` →

```
GET  <ADDR>/v1/secret/data/stapel/app   ->   .data.data["DJANGO_SECRET_KEY"]
```

Grouping secrets as keys of one bundle is the common ops pattern and lets one
read populate the whole app (see `BUNDLE_CACHE_TTL`). Override a specific name
with `VAULT_SECRET_MAP`: value `"<path>#<key>"`, where `<path>` may carry an
explicit `"<mount>/data/<rest>"` (used verbatim) or is relative to `KV_MOUNT`.

## Auth methods

- **token** — `VAULT_TOKEN` used directly (local/dev). Treated as static.
- **kubernetes** — the pod's projected service-account JWT at `K8S_JWT_PATH`
  is exchanged at `auth/<mount>/login` for a role-bound Vault token
  (deploy-topology phase 2). Token cached until ~90% of its lease.
- **approle** — `ROLE_ID` + `SECRET_ID` at `auth/<mount>/login` (prod, non-k8s).

A mid-flight `403` (token expired/revoked) triggers exactly one re-auth + retry.

## Rotation & versioned reads (SEC gap)

The facade does not rotate Vault's secrets; it behaves correctly *when* they
rotate. Core caches resolved values for `STAPEL_SECRETS["CACHE_TTL"]` (the
re-read window); calling `stapel_core.secrets.invalidate_secret()` forces an
eager re-read, and `VaultSecretProvider.invalidate()` drops the provider's
bundle cache so the next read fetches the latest KV version. Reads can be
pinned to a version with `VAULT_KV_VERSION`.

## Failure semantics

- Secret absent in Vault (missing key / 404) → `get` returns `None`; the core
  seam then applies the caller's default or raises `SecretUnavailable`
  (fail-closed).
- Transport/auth failure (unreachable, 5xx, bad credentials) → `VaultError`
  propagates fail-closed (a production secret store that cannot answer is a
  boot-stopping error, as intended). The client is stdlib `urllib` — no `hvac`,
  no `requests`.

## Testing

`pytest tests/` runs unit tests with a mock HTTP client (no live Vault). The
opt-in smoke test against a real OpenBao/Vault is gated behind the
`vault_integration` marker and skipped unless `VAULT_ADDR` + `VAULT_TOKEN` are
set:

```bash
docker run --rm -p 8200:8200 -e BAO_DEV_ROOT_TOKEN_ID=root \
    openbao/openbao server -dev
export VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root
pytest -m vault_integration
```

## What's not here (roadmap)

- Cloud secret-manager backends (AWS Secrets Manager, GCP Secret Manager,
  Azure Key Vault) — on Kubernetes these are typically reached via **External
  Secrets Operator** syncing into Vault or into projected secrets; a native
  provider per manager is a future addition behind the same core seam.
- Per-service integration (which services read which names from Vault) —
  wiring, tracked in the deploy-topology rollout, not in this module.
