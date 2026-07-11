# CONFIG.MD — stapel-vault

Config registry for **stapel-vault** (`static-scaffold-and-config.md` §2). One
row per configuration key the module reads, its **source** (`env` = the process
environment — Vault connection config legitimately lives in the environment /
Kubernetes, not Django settings, because a prod settings module resolves
`SECRET_KEY` through Vault *before* `django.setup()` runs), what it is for,
whether it is required, and its default.

stapel-vault is a **secrets-provider facade** activated by pointing
`STAPEL_SECRETS_PROVIDER` (a stapel-core key) at
`stapel_vault.VaultSecretProvider`. It is **headless**: no models, urls or
Django app of its own — the scaffolder installs it as a pip dependency but
mounts it in neither `INSTALLED_APPS` nor the URL conf.

Every key is resolved by `stapel_vault.config.load_config`. Resolution order
per key: `STAPEL_VAULT[<key>]` (once Django is configured) → the `VAULT_*`
environment variable → the default below.

## stapel-vault

| Key | Source | Purpose | Required | Default |
|-----|--------|---------|----------|---------|
| VAULT_ADDR | env | Vault/OpenBao server address. | no | http://127.0.0.1:8200 |
| VAULT_NAMESPACE | env | Vault Enterprise namespace (optional). | no | (none) |
| VAULT_KV_MOUNT | env | KV v2 secrets-engine mount point. | no | secret |
| VAULT_SECRET_PATH_PREFIX | env | path prefix under the KV mount where secrets live. | no | stapel |
| VAULT_SECRET_APP | env | application segment appended to the path prefix. | no | app |
| VAULT_KV_VERSION | env | KV engine version override (auto-detected when unset). | no | (auto) |
| VAULT_HTTP_TIMEOUT | env | HTTP timeout (seconds) for Vault requests. | no | 5.0 |
| VAULT_BUNDLE_CACHE_TTL | env | seconds a fetched secret bundle is cached (0 disables). | no | 0.0 |
| VAULT_AUTH_METHOD | env | auth method: token \| kubernetes \| approle (auto-detected from what is present when unset). | no | (auto) |
| VAULT_TOKEN | vault | Vault token (token auth). | no | (none) |
| VAULT_AUTH_MOUNT | env | auth-method mount point. | no | (per method) |
| VAULT_K8S_ROLE | env | Kubernetes auth role. | no | (none) |
| VAULT_K8S_JWT_PATH | env | path to the projected Kubernetes service-account JWT. | no | /var/run/secrets/kubernetes.io/serviceaccount/token |
| VAULT_ROLE_ID | vault | AppRole role id (approle auth). | no | (none) |
| VAULT_SECRET_ID | vault | AppRole secret id (approle auth). | no | (none) |
| VAULT_SECRET_MAP | env | explicit per-name mapping JSON {"NAME": "path#key", …}. | no | {} |
