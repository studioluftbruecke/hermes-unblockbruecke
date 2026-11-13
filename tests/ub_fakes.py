"""Test helpers (conftest.py puts this folder on sys.path): load the plugin without Hermes, a temp
store, deck builders, a fake ctx."""
from __future__ import annotations

import importlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = "unblockbruecke_under_test"


def load_plugin():
    if PKG in sys.modules:
        return sys.modules[PKG]
    spec = importlib.util.spec_from_file_location(PKG, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = module
    spec.loader.exec_module(module)
    return module


def sub(name: str):
    load_plugin()
    return importlib.import_module(f"{PKG}.{name}")


def hermes_source() -> "pathlib.Path | None":
    """Hermes' source tree: HERMES_SOURCE, a PYTHONPATH entry holding hermes_cli, the Docker image's
    /opt/hermes, then the installer's path. None when there is none."""
    import os

    candidates = [os.environ.get("HERMES_SOURCE", "")]
    candidates += os.environ.get("PYTHONPATH", "").split(os.pathsep)
    candidates += ["/opt/hermes", str(pathlib.Path.home() / ".hermes" / "hermes-agent")]
    for candidate in candidates:
        if candidate and (pathlib.Path(candidate) / "hermes_cli" / "__init__.py").is_file():
            return pathlib.Path(candidate)
    return None


def hermes_python(source: "pathlib.Path | None") -> "pathlib.Path | None":
    """The interpreter that runs Hermes: HERMES_PYTHON, else the source's venv."""
    import os

    candidates = [os.environ.get("HERMES_PYTHON", "")]
    if source is not None:
        candidates += [str(source / ".venv" / "bin" / "python"), str(source / "venv" / "bin" / "python")]
    for candidate in candidates:
        if candidate and pathlib.Path(candidate).exists():
            return pathlib.Path(candidate)
    return None


def make_store(tmp_path):
    return sub("store").Store(tmp_path / "data")


def card(n: int, prefix: str = "tt", tags=None, human=None, agent=None) -> dict:
    return {"id": f"{prefix}-{n:02d}", "human": human or f"Human line number {n}.",
            "agent": agent or f"Do concrete step number {n} and report what changed.", "tags": list(tags or ["test"])}


def deck_doc(slug: str = "test-deck", n: int = 5, prefix: str = "tt", cards=None, **extra) -> dict:
    doc = {"schema": 1, "deck": slug, "name": "Test deck", "by": "Tester", "license": "CC0-1.0", "version": 1,
           "faces": ["human", "agent"], "mark": "square", "description": "A deck for tests",
           "glossary": {"test": "A tag used in tests.", "lateral": "Comes at it sideways."},
           "cards": cards if cards is not None else [card(i, prefix) for i in range(1, n + 1)]}
    doc.update(extra)
    return doc


def yaml_text(doc: dict) -> str:
    from ruamel.yaml import YAML
    import io

    y = YAML()
    buf = io.StringIO()
    y.dump(doc, buf)
    return buf.getvalue()


def write_user_deck(store, doc: dict) -> pathlib.Path:
    path = store.path("decks", f"{doc['deck']}.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_text(doc), encoding="utf-8")
    return path


class SeqRng:
    """A random source whose choices() returns the item at fixed positions in turn."""

    def __init__(self, picks):
        self.picks = list(picks)

    def choices(self, pool, weights=None, k=1):
        return [pool[self.picks.pop(0) % len(pool)]]


class FakeState:
    def __init__(self, data_dir):
        self.data_dir = data_dir

    def get(self, key, default=None):
        return default

    def set(self, key, value):
        pass


class FakeCtx:
    """Records registrations; settings answer get_config."""

    def __init__(self, data_dir, settings=None, surface="desktop"):
        self.state = FakeState(data_dir)
        self.settings = dict(settings or {})
        self.surface = surface
        self.tools: dict = {}
        self.hooks: dict = {}
        self.commands: dict = {}
        self.skills: list = []

    def register_tool(self, **kw):
        self.tools[kw["name"]] = kw

    def register_hook(self, name, callback, **kw):
        self.hooks[name] = callback

    def register_command(self, name, handler, description="", args_hint="", **kw):
        self.commands[name] = handler

    def register_skill(self, name, path, description=""):
        self.skills.append(name)

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def session_surface(self):
        return self.surface

    def current_cron_execution(self):
        return None

    def call(self, tool, **args):
        return json.loads(self.tools[tool]["handler"](args))
