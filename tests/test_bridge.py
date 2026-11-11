"""Unattended detection (constraint 6, Q2), copied from Eselsbrücke with its rules."""
import pytest

from ub_fakes import FakeCtx, sub


@pytest.mark.parametrize("surface,unattended", [("", True), ("cli", True), ("oneshot", True),
                                                ("desktop", False), ("tui", False), ("telegram", False)])
def test_host_isolation_fails_closed_for_blind_surfaces(tmp_path, monkeypatch, surface, unattended):
    """Q2: under plugins.isolation: host the one-shot marker is invisible, so cli/oneshot/unknown count as
    unattended (no human cards for auto-draw, no deck writes); attended clients keep working."""
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    bridge = sub("bridge")
    monkeypatch.setattr(bridge, "_finite_turn", lambda: None)
    reason = bridge.unattended_reason(FakeCtx(tmp_path, surface=surface))
    assert (reason is not None) is unattended
    if unattended:
        assert "plugins.isolation" in reason


def test_cron_single_query_and_webhook(tmp_path, monkeypatch):
    bridge = sub("bridge")
    ctx = FakeCtx(tmp_path)
    assert bridge.unattended_reason(ctx) is None
    monkeypatch.setenv("HERMES_CRON_SESSION", "1")
    assert bridge.unattended_reason(ctx) == "a scheduled job"
    monkeypatch.delenv("HERMES_CRON_SESSION")
    monkeypatch.setattr(bridge, "_finite_turn", lambda: True)
    assert "single-query" in bridge.unattended_reason(ctx)
    monkeypatch.setattr(bridge, "_finite_turn", lambda: False)
    assert "webhook" in bridge.unattended_reason(FakeCtx(tmp_path, surface="webhook"))


def test_unreadable_marker_fails_closed_in_process(tmp_path, monkeypatch):
    bridge = sub("bridge")
    monkeypatch.setattr(bridge, "_finite_turn", lambda: None)
    assert "update Unblockbrücke" in bridge.unattended_reason(FakeCtx(tmp_path))
