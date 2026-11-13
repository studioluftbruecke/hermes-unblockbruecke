"""What the plugin takes from Hermes: only public surfaces, plus the two guarded markers it documents."""
import datetime as dt
import pathlib

import pytest
from ub_fakes import ROOT, sub

try:
    from hermes_cli.plugin_validate_private_imports import private_import_findings
except Exception:  # the plain test venv has no Hermes
    private_import_findings = None

needs_hermes = pytest.mark.skipif(private_import_findings is None, reason="Hermes is not importable here")

# Each with its reason in bridge.py: Hermes has no public signal for either.
ACCEPTED = {"gateway.session_finite.finite_turn_required", "agent.delegation_context.is_delegated_child_context"}


@needs_hermes
def test_hermes_plugins_validate_names_only_the_two_documented_private_imports():
    found = {site.split(" ", 1)[1] for site in private_import_findings(ROOT)}
    assert found == ACCEPTED, found


def test_the_data_folder_name_follows_hermes_rule():
    import hashlib

    expected = "agent-plugin-unblockbruecke-" + hashlib.sha256(b"unblockbruecke").hexdigest()[:8]
    assert sub("store").namespace() == expected
    try:
        from hermes_cli.plugins_manifest import _portable_data_namespace
    except Exception:
        return
    assert _portable_data_namespace("unblockbruecke") == expected


@pytest.fixture
def real_clock():
    bridge = sub("bridge")
    bridge.set_clock(None)
    yield bridge


def write_config(home: pathlib.Path, text: str) -> None:
    (home / "config.yaml").write_text(text, encoding="utf-8")


@needs_hermes
def test_the_clock_follows_the_profile_timezone(real_clock, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_TIMEZONE", raising=False)
    write_config(tmp_path, "timezone: Pacific/Auckland\n")
    assert real_clock.zone_name() == "Pacific/Auckland"
    assert real_clock.now().utcoffset() == dt.datetime.now(__import__("zoneinfo").ZoneInfo("Pacific/Auckland")).utcoffset()


@needs_hermes
def test_hermes_timezone_env_wins_and_a_bad_zone_falls_back_to_local(real_clock, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    write_config(tmp_path, "timezone: Pacific/Auckland\n")
    monkeypatch.setenv("HERMES_TIMEZONE", "Asia/Tokyo")
    assert real_clock.zone_name() == "Asia/Tokyo"
    monkeypatch.setenv("HERMES_TIMEZONE", "Not/AZone")
    assert real_clock.zone_name() == ""
    assert real_clock.now().tzinfo is not None
