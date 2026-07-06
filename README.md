# stapel-vault

Production secret storage for the [Stapel framework](https://github.com/usestapel).
A facade over secret backends behind the `stapel_core.secrets` provider seam —
the first backend is **OpenBao / HashiCorp Vault** (KV v2; their HTTP APIs are
compatible, so one client speaks to both).

Local dev and the `minimal` preset keep reading secrets from the environment
(stapel-core's default provider). In production, where **env for secrets is
unacceptable**, point the seam at `stapel-vault` and the framework reads
`SECRET_KEY`, `JWT_SECRET_KEY`, database passwords and LLM pool keys from Vault
instead — with no change to the code that consumes them.

## Install

```bash
pip install stapel-vault      # requires stapel-core with the SecretProvider seam
```

## Wire it up

The provider is selected at settings-bootstrap time (production settings
resolve `SECRET_KEY` before `django.setup()`), via environment — which is also
where Vault's own connection/auth config belongs:

```bash
# control plane only — never a workload container (see MODULE.md, S1)
export STAPEL_SECRETS_PROVIDER=stapel_vault.VaultSecretProvider
export VAULT_ADDR=https://vault.internal:8200
export VAULT_K8S_ROLE=stapel-web       # Kubernetes auth (phase 2)
```

Then any `stapel_core.secrets.get_secret("DJANGO_SECRET_KEY")` — including the
`SECRET_KEY` / `JWT_SECRET_KEY` reads in `stapel_core.django.settings` — comes
from Vault. A missing secret is a hard, loud boot failure (`fail_closed`), not
a silent `None`.

## Secret layout (default convention)

A service's secrets are keys of one KV v2 secret (the "bundle") at
`secret/data/<prefix>/<app>` (defaults `secret/data/stapel/app`):

```bash
bao kv put secret/stapel/app \
    DJANGO_SECRET_KEY=... JWT_SECRET_KEY=... POSTGRES_PASSWORD=...
```

`DJANGO_SECRET_KEY` then resolves to `GET v1/secret/data/stapel/app` →
`.data.data["DJANGO_SECRET_KEY"]`. Override per name with `VAULT_SECRET_MAP`
(JSON). See [MODULE.md](MODULE.md) for the full config reference, auth methods,
rotation, and the deploy-mode map.

## Auth methods

| Method | When | Config |
|---|---|---|
| `token` | local/dev | `VAULT_TOKEN` |
| `kubernetes` | prod on k8s (phase 2) | `VAULT_K8S_ROLE` (+ projected SA JWT) |
| `approle` | prod, non-k8s | `VAULT_ROLE_ID` + `VAULT_SECRET_ID` |

Auto-detected from what is present, or forced with `VAULT_AUTH_METHOD`.

## License

MIT — see [LICENSE](LICENSE).
