"""Is a person there to approve? The one rule every Studio Luftbrücke plugin follows."""
import sys
import types

import pytest
from ub_fakes import FakeCtx, sub

bridge = sub("bridge")
READ_MARKER = bridge._finite_turn  # the real reader; conftest replaces it with an attended stand-in per test
NO_SIGNAL = "this Hermes version does not say whether a person is present, so writes are refused; update the plugin"


def finite_module(monkeypatch, answer):
    """Stand in for gateway.session_finite: `answer` is what finite_turn_required returns, an exception
    it raises, or None for a Hermes without the module."""
    monkeypatch.setattr(bridge, "_finite_turn", READ_MARKER)
    if answer is None:
        monkeypatch.setitem(sys.modules, "gateway.session_finite", None)
        return
    mod = types.ModuleType("gateway.session_finite")

    def finite_turn_required():
        if isinstance(answer, BaseException):
            raise answer
        return answer

    mod.finite_turn_required = finite_turn_required
    monkeypatch.setitem(sys.modules, "gateway.session_finite", mod)


@pytest.mark.parametrize("host", [False, True])
def test_an_attended_desktop_chat_may_write(tmp_path, monkeypatch, host):
    finite_module(monkeypatch, False)
    if host:
        monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    assert bridge.unattended_reason(FakeCtx(tmp_path, surface="desktop")) is None


def test_a_gateway_admitted_single_query_turn_is_unattended(tmp_path, monkeypatch):
    finite_module(monkeypatch, True)
    assert "single-query" in bridge.unattended_reason(FakeCtx(tmp_path, surface="desktop"))


@pytest.mark.parametrize("answer", [None, RuntimeError("moved")], ids=["module missing", "call raises"])
@pytest.mark.parametrize("host", [False, True])
def test_no_readable_marker_fails_closed_with_one_sentence(tmp_path, monkeypatch, answer, host):
    finite_module(monkeypatch, answer)
    if host:
        monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    assert bridge.unattended_reason(FakeCtx(tmp_path, surface="desktop")) == NO_SIGNAL


@pytest.mark.parametrize("platform", ["webhook", "msgraph_webhook", "api_server"])
def test_unattended_platforms(tmp_path, monkeypatch, platform):
    finite_module(monkeypatch, False)
    assert bridge.unattended_reason(FakeCtx(tmp_path, surface=platform)) is not None


def test_cron_and_single_query_env(tmp_path, monkeypatch):
    finite_module(monkeypatch, False)
    monkeypatch.setenv("HERMES_CRON_SESSION", "1")
    assert bridge.unattended_reason(FakeCtx(tmp_path)) == "a scheduled job"
    monkeypatch.delenv("HERMES_CRON_SESSION")
    monkeypatch.setenv("HERMES_SINGLE_QUERY_SESSION", "1")
    assert "single-query" in bridge.unattended_reason(FakeCtx(tmp_path))


def test_a_cron_execution_seen_through_ctx_is_unattended(tmp_path, monkeypatch):
    finite_module(monkeypatch, False)
    ctx = FakeCtx(tmp_path)
    ctx.current_cron_execution = lambda: {"job_id": "j1"}
    assert bridge.unattended_reason(ctx) == "a scheduled job"


def test_the_agent_tool_refusal_names_the_missing_signal(tmp_path, monkeypatch):
    finite_module(monkeypatch, None)
    from ub_fakes import load_plugin

    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    out = ctx.call("unblockbruecke_decks", action="switch", deck="coding", auto=True)
    assert out["ok"] is False and out["error"] == "unattended" and NO_SIGNAL in out["message"]


@pytest.mark.parametrize("surface,unattended", [("", True), ("cli", True), ("oneshot", True),
                                                ("desktop", False), ("tui", False), ("telegram", False)])
def test_inside_the_plugin_host_a_cli_or_one_shot_surface_is_unattended(tmp_path, monkeypatch, surface, unattended):
    """Inside the plugin host the turn's own one-shot markers are not visible, so a CLI, one-shot or unknown
    surface counts as unattended; Desktop, the TUI and messaging chats keep the approval card."""
    finite_module(monkeypatch, False)
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    reason = bridge.unattended_reason(FakeCtx(tmp_path, surface=surface))
    assert (reason is not None) is unattended
    if unattended:
        assert "plugins.isolation" in reason
