"""Drift gate for docs/capabilities.json (stapel_tools.surface, as in stapel-core)."""
import json
from pathlib import Path

try:
    from stapel_tools.surface import _stable_json, build_static_capabilities, load_meta
except ImportError as exc:  # pragma: no cover - a skipped drift gate is no gate
    raise RuntimeError(
        "the capabilities drift gate needs stapel-tools (it carries the emitter)"
    ) from exc

REPO = Path(__file__).resolve().parent.parent
COMMITTED = REPO / "docs" / "capabilities.json"


def test_capabilities_committed_and_has_no_drift():
    assert COMMITTED.is_file(), "docs/capabilities.json is missing — run `make contract`"
    assert COMMITTED.read_text() == _stable_json(
        build_static_capabilities(REPO, load_meta(REPO))
    ), "docs/capabilities.json is stale — run `make contract` and commit it"


def test_version_matches_pyproject():
    import tomllib

    project = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
    doc = json.loads(COMMITTED.read_text())
    assert (doc["module"], doc["version"]) == (project["name"], project["version"])


def test_surface_names_the_entry_points():
    doc = json.loads(COMMITTED.read_text())
    assert {e["name"] for e in doc["surface"]} == {"load_config", "map_name"}
