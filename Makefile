# stapel-vault — contract emission + drift gate.
#
# docs/capabilities.json is built the way stapel-core's is
# (stapel_tools.surface): provides / extension_points / requires from the
# curated docs/capabilities.meta.json, `surface` derived by AST from its
# surface_roots, module/version from pyproject.toml. Re-run after a version
# bump. tests/test_capabilities.py is the same gate under pytest.
PYTHON ?= python3

.PHONY: contract contract-check

contract:
	$(PYTHON) -m stapel_tools.surface .

contract-check:
	$(PYTHON) -m stapel_tools.surface . --check
