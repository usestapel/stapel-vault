# Changelog

## [Unreleased]

### Added — initial release (0.1.0): OpenBao/HashiCorp Vault secret provider

- **`VaultSecretProvider`** — implements the `stapel_core.secrets` provider
  seam (`get(name) -> str | None`, `fail_closed = True`) against a Vault /
  OpenBao **KV v2** store. Wiring is one setting in the host project
  (`STAPEL_SECRETS_PROVIDER=stapel_vault.VaultSecretProvider` at bootstrap, or
  `STAPEL_SECRETS["PROVIDER"]` once Django is up) — no import of stapel-core
  (invariant I2; the seam contract is mirrored, not imported).

- **Name → KV mapping** — a logical secret name is a key inside one KV v2
  "bundle" secret at `<kv_mount>/data/<path_prefix>/<app>` (defaults
  `secret/data/stapel/app`), so `DJANGO_SECRET_KEY` reads
  `.data.data["DJANGO_SECRET_KEY"]`. Per-name overrides via `VAULT_SECRET_MAP`
  (`{"NAME": "<path>#<key>"}`).

- **Auth methods** — token (dev), Kubernetes (service-account JWT exchange,
  deploy-topology phase 2), AppRole. Client tokens are cached until ~90% of
  their lease and re-authenticated on demand; a mid-flight 403 triggers one
  re-auth + retry.

- **Rotation / versioned reads (SEC gap)** — `invalidate()` clears the
  provider's optional bundle cache (pair with
  `stapel_core.secrets.invalidate_secret()`); reads honor a pinned
  `VAULT_KV_VERSION` and otherwise fetch the latest version.

- **No heavy deps** — the Vault client is stdlib `urllib` (no `hvac`, no
  `requests`), so the provider imports at settings-bootstrap time with a slim
  footprint. Config resolves env-first (`VAULT_*`) with an optional
  `STAPEL_VAULT` settings override.

- Depends on `stapel-core>=0.9,<0.10` (the release carrying the SecretProvider
  seam). Until core 0.9 is on PyPI the CI release-track job is advisory.

- 40 unit tests (mock HTTP; 94% coverage) + an opt-in `vault_integration`
  smoke test against a real OpenBao/Vault.
