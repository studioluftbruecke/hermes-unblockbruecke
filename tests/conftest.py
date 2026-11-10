"""Make ub_fakes.py importable by name (pytest runs with --import-mode=importlib), and make every
test an attended chat on a fixed clock unless it says otherwise: outside Hermes the one-shot marker
cannot be read, which the plugin treats as unattended (fail closed)."""
import datetime as dt
import pathlib
import sys
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def attended(monkeypatch):
    from ub_fakes import sub

    bridge = sub("bridge")
    monkeypatch.setattr(bridge, "_finite_turn", lambda: False)
    monkeypatch.delenv("HERMES_PLUGIN_HOST_PROCESS", raising=False)
    monkeypatch.delenv("HERMES_CRON_SESSION", raising=False)
    monkeypatch.delenv("HERMES_SINGLE_QUERY_SESSION", raising=False)
    bridge.set_clock(lambda: dt.datetime(2026, 11, 10, 14, 0, tzinfo=ZoneInfo("Europe/Berlin")), "Europe/Berlin")
    yield
    bridge.set_clock(None)
