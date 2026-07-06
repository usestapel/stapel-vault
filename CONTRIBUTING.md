# Contributing to stapel-vault

Part of the [Stapel framework](https://github.com/usestapel) — composable
Django apps for monolith-or-microservices deployments. The normative
package standard lives in the stapel workspace
(`docs/library-standard.md`); the short version is below.

## Dev setup

```bash
git clone https://github.com/usestapel/stapel-vault.git && cd stapel-vault
python -m venv .venv && source .venv/bin/activate
# stapel-core provides the secret-provider seam this plugs into:
pip install git+https://github.com/usestapel/stapel-core.git
pip install -e ".[dev]" --no-deps
./setup-hooks.sh   # enables the ruff pre-commit hook
```

## Running tests

```bash
pytest tests/                 # unit tests (mock HTTP, no live Vault)
```

The opt-in smoke test against a real OpenBao/Vault is gated behind a marker
and skipped unless `VAULT_ADDR` + `VAULT_TOKEN` are set:

```bash
docker run --rm -p 8200:8200 -e BAO_DEV_ROOT_TOKEN_ID=root \
    openbao/openbao server -dev
export VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root
pytest -m vault_integration
```

## Lint

```bash
ruff check . --select E,F,W --ignore E501
```

The pre-commit hook runs the same command; CI rejects anything it flags.

## Design rules (the short version)

- **No new hardcoded behavior.** Connection config resolves env-first
  (`VAULT_*`) with an optional `STAPEL_VAULT` Django-settings override —
  because production settings modules resolve secrets *before*
  `django.setup()`. See `config.py`.
- **No module imports another.** The provider is duck-typed against the
  `stapel_core.secrets` seam (invariant I2); the contract is mirrored, not
  imported, in `provider.py` (`SecretProvider` Protocol).
- **No heavy dependencies.** The Vault client is stdlib `urllib` — no `hvac`,
  no `requests`. Keep it that way (this must import at settings-bootstrap
  time with a slim footprint).
- **Every seam/behavior is documented in MODULE.md** — in the same PR that
  adds or changes it.

## Commit style

Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`); one logical
change per commit; add a CHANGELOG entry under **Unreleased**.

## Coverage policy (CI)

Two Codecov statuses (see `codecov.yml`): `codecov/project` is a ratchet
(total must not drop >0.5%); `codecov/patch` is an 80% floor for new code.
