"""The page's settings writes go through Hermes' public CLI, `hermes config set`, into the profile's own
config.yaml: a real child process against a temp profile, read back from the file. Hermes' own refusals
(a managed install, an administrator's pinned key) hold in the child and answer 403, also when the CLI
refuses with exit code 0, and the ordinary saves keep working."""
import os
import pathlib

import pytest
from ub_fakes import hermes_source, make_store, sub

api = sub("api")
settings = sub("settings")
SOURCE = hermes_source()
needs_hermes = pytest.mark.skipif(SOURCE is None, reason="Hermes' source tree is needed for its CLI")


@pytest.fixture
def profile(tmp_path, monkeypatch):
    home = tmp_path / "home"
    for sub_dir in ("cron", "sessions", "logs", "memories"):  # a real profile's skeleton (a managed install needs it)
        (home / sub_dir).mkdir(parents=True)
    (home / "config.yaml").write_text("model:\n  default: kept-as-is\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    for name in ("HERMES_MANAGED", "HERMES_MANAGED_DIR", "HERMES_CONFIG_BACKEND"):
        monkeypatch.delenv(name, raising=False)
    if SOURCE is not None and str(SOURCE) not in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        monkeypatch.setenv("PYTHONPATH", os.pathsep.join(p for p in (str(SOURCE), os.environ.get("PYTHONPATH", "")) if p))
    api.configure(store_factory=lambda: make_store(tmp_path), settings_factory=lambda: settings.read(lambda k, d=None: d))
    yield home
    api.configure()


def saved(home: pathlib.Path) -> dict:
    from ruamel.yaml import YAML

    doc = YAML(typ="safe", pure=True).load((home / "config.yaml").read_text(encoding="utf-8")) or {}
    return doc


def plugin_settings(home: pathlib.Path) -> dict:
    return ((saved(home).get("plugins") or {}).get("entries") or {}).get("unblockbruecke", {}).get("settings", {})


@needs_hermes
@pytest.mark.parametrize("key,value", [("autodraw", True), ("learning", False), ("autodraw_threshold", 4),
                                       ("card_of_day", False), ("show_in_statusbar", True)])
def test_a_setting_lands_in_the_profile_config_through_the_cli(profile, key, value):
    status, body = api.setting_set({"key": key, "value": value})
    assert status == 200 and body["saved"] == {"key": key, "value": value}, body
    assert plugin_settings(profile)[key] == value
    assert saved(profile)["model"] == {"default": "kept-as-is"}


@needs_hermes
def test_saving_the_same_value_twice_and_then_another_one_answers_saved_each_time(profile):
    for value in (True, True, False):
        status, body = api.setting_set({"key": "autodraw", "value": value})
        assert status == 200 and plugin_settings(profile)["autodraw"] is value, body


@needs_hermes
def test_an_explicit_not_managed_marker_still_saves(profile, monkeypatch):
    monkeypatch.setenv("HERMES_MANAGED", "false")
    status, body = api.setting_set({"key": "autodraw_threshold", "value": 5})
    assert status == 200 and plugin_settings(profile)["autodraw_threshold"] == 5, body


@needs_hermes
def test_a_managed_install_by_marker_file_is_refused_and_nothing_is_written(profile):
    (profile / ".managed").write_text("nix\n", encoding="utf-8")
    before = (profile / "config.yaml").read_text(encoding="utf-8")
    status, body = api.setting_set({"key": "autodraw", "value": True})
    assert status == 403 and body["error"] == "not_allowed" and "managed" in body["message"], body
    assert (profile / "config.yaml").read_text(encoding="utf-8") == before


@needs_hermes
def test_a_managed_install_by_service_environment_is_refused_and_nothing_is_written(profile, monkeypatch):
    monkeypatch.setenv("HERMES_MANAGED", "nix")
    before = (profile / "config.yaml").read_text(encoding="utf-8")
    status, body = api.setting_set({"key": "autodraw", "value": True})
    assert status == 403 and body["error"] == "not_allowed" and "managed" in body["message"], body
    assert (profile / "config.yaml").read_text(encoding="utf-8") == before


@needs_hermes
def test_a_key_the_administrator_pinned_is_refused_and_nothing_is_written(profile, monkeypatch, tmp_path):
    admin = tmp_path / "etc-hermes"
    admin.mkdir()
    (admin / "config.yaml").write_text("plugins:\n  entries:\n    unblockbruecke:\n      settings:\n        autodraw: false\n",
                                       encoding="utf-8")
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(admin))
    status, body = api.setting_set({"key": "autodraw", "value": True})
    assert status == 403 and body["error"] == "not_allowed" and "administrator" in body["message"], body
    assert "plugins" not in saved(profile)
    other = api.setting_set({"key": "learning", "value": False})  # a key the administrator left alone
    assert other[0] == 200 and plugin_settings(profile)["learning"] is False, other


def _recording_cli(tmp_path, then_run_hermes: bool) -> tuple[pathlib.Path, pathlib.Path]:
    seen = tmp_path / "env.txt"
    script = tmp_path / "fake_hermes.py"
    run = "os.execv(sys.executable, [sys.executable, '-m', 'hermes_cli.main', *sys.argv[1:]])\n" if then_run_hermes else ""
    script.write_text("import os, sys\nopen(%r, 'w').write('\\n'.join(sorted(os.environ)))\n%s" % (str(seen), run),
                      encoding="utf-8")
    return script, seen


@needs_hermes
def test_the_child_gets_no_secret_from_the_process_environment(profile, monkeypatch, tmp_path):
    script, seen = _recording_cli(tmp_path, then_run_hermes=True)
    monkeypatch.setenv("UNBLOCK_TEST_SECRET_TOKEN", "sentinel")
    monkeypatch.setenv("HERMES_TEST_API_KEY", "sentinel")
    monkeypatch.setattr(api, "HERMES_CLI", [api.sys.executable, str(script)])
    status, _body = api.setting_set({"key": "autodraw", "value": True})
    names = seen.read_text().split("\n")
    assert status == 200 and plugin_settings(profile)["autodraw"] is True
    assert "UNBLOCK_TEST_SECRET_TOKEN" not in names and "HERMES_TEST_API_KEY" not in names and "HERMES_HOME" in names


def test_the_child_sees_what_hermes_reads_to_decide_whether_it_may_write(profile, monkeypatch, tmp_path):
    script, seen = _recording_cli(tmp_path, then_run_hermes=False)
    for name in ("HERMES_MANAGED", "HERMES_MANAGED_DIR", "HERMES_CONFIG_BACKEND"):
        monkeypatch.setenv(name, "x")
    monkeypatch.setattr(api, "HERMES_CLI", [api.sys.executable, str(script)])
    monkeypatch.setattr(settings, "saved_value", lambda key: None)
    api.setting_set({"key": "autodraw", "value": True})
    names = seen.read_text().split("\n")
    assert {"HERMES_MANAGED", "HERMES_MANAGED_DIR", "HERMES_CONFIG_BACKEND"} <= set(names)


def test_a_cli_that_exits_0_without_saving_answers_403_with_its_reason(profile, monkeypatch, tmp_path):
    script = tmp_path / "quiet_refusal.py"
    script.write_text("import sys\nprint('Cannot set configuration values: this install is managed.', file=sys.stderr)\n",
                      encoding="utf-8")
    monkeypatch.setattr(api, "HERMES_CLI", [api.sys.executable, str(script)])
    monkeypatch.setattr(settings, "saved_value", lambda key: None)
    status, body = api.setting_set({"key": "autodraw", "value": True})
    assert status == 403 and body["error"] == "not_allowed" and "managed" in body["message"], body


def test_a_quiet_refusal_names_hermes_reason_not_a_warning_printed_before_it(profile, monkeypatch, tmp_path):
    script = tmp_path / "warned_refusal.py"
    script.write_text("import sys\nprint('\u26a0 install out of sync: rebuild the artifact', file=sys.stderr)\n"
                      "print('\u2717 Cannot set configuration values: this install is managed by nix.', file=sys.stderr)\n",
                      encoding="utf-8")
    monkeypatch.setattr(api, "HERMES_CLI", [api.sys.executable, str(script)])
    monkeypatch.setattr(settings, "saved_value", lambda key: None)
    status, body = api.setting_set({"key": "autodraw", "value": True})
    assert status == 403 and "managed by nix" in body["message"] and "out of sync" not in body["message"], body


def test_a_refusal_by_hermes_answers_403_with_its_reason(profile, monkeypatch, tmp_path):
    script = tmp_path / "refuse.py"
    script.write_text("import sys\nprint('✗ plugins.entries.unblockbruecke is administrator-managed')\nsys.exit(1)\n", encoding="utf-8")
    monkeypatch.setattr(api, "HERMES_CLI", [api.sys.executable, str(script)])
    status, body = api.setting_set({"key": "autodraw", "value": True})
    assert status == 403 and body["error"] == "not_allowed" and "administrator-managed" in body["message"]
