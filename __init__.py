"""stapel-vault — production secret storage for the Stapel framework.

A facade over secret backends behind the ``stapel_core.secrets`` provider seam.
The first backend is **OpenBao / HashiCorp Vault** (KV v2 — their HTTP APIs are
compatible, so one client speaks to both). Point the core seam at it and the
framework reads ``SECRET_KEY`` / ``JWT_SECRET_KEY`` / DB passwords / LLM pool
keys from Vault instead of the environment — the decision that "env for prod
secrets is unacceptable" (arch-stapel-vault).

    # deployment environment (control plane only — S1: never a workload container)
    export STAPEL_SECRETS_PROVIDER=stapel_vault.VaultSecretProvider
    export VAULT_ADDR=https://vault.internal:8200
    export VAULT_K8S_ROLE=stapel-web

See MODULE.md for the deploy-mode map (local=env / prod=vault+k8s auth) and
the S1 constraint that workload containers never see Vault.

Public API is lazily exported (PEP 562) so importing this package never runs
the provider's relative imports until an attribute is actually used.
"""

try:  # single source of truth: pyproject version via package metadata
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("stapel-vault")
except Exception:  # editable/vendored checkout without dist-info
    __version__ = "0.1.0"

__all__ = [
    "SecretProvider",
    "VaultAuthError",
    "VaultConfigError",
    "VaultError",
    "VaultSecretProvider",
    "VaultTransportError",
    "__version__",
]

# name -> submodule that defines it. Deferred until first attribute access.
_LAZY_EXPORTS = {
    "SecretProvider": ".provider",
    "VaultSecretProvider": ".provider",
    "VaultAuthError": ".exceptions",
    "VaultConfigError": ".exceptions",
    "VaultError": ".exceptions",
    "VaultTransportError": ".exceptions",
}


def __getattr__(name):
    if name in _LAZY_EXPORTS:
        from importlib import import_module

        value = getattr(import_module(_LAZY_EXPORTS[name], __name__), name)
        globals()[name] = value  # cache for subsequent lookups
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
