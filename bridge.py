"""The only module that imports Hermes internals (besides `store.namespace`).

- `now()`, `today()`, `zone_name()`: Hermes' own time zone (`timezone` setting, `HERMES_TIMEZONE`
  overrides, empty means server-local), through `hermes_time` (PLAN constraint 10). Tests replace
  the clock with `set_clock()`.
- `failed(tool, result, status)`: whether Hermes counts a tool call as failed, with Hermes' own
  `agent.display._detect_tool_failure` (constraint 2, U11). The hook's `status` is only the
  fallback when that import fails.
- `unattended_reason(ctx)`: why no person is at the keyboard (copied from Eselsbrücke's
  `hermes_bridge`, constraint 6), or None in an attended chat.
- `where(ctx)`: where the turn runs (Desktop chat, kanban task, cron job, CLI, ...) for the journal
  (0.2, AX-2); `route_unattended()`: the same markers for a page route (R10).
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any, Callable, Optional

# --- time -----------------------------------------------------------------------------------------

_clock: Optional[Callable[[], dt.datetime]] = None
_zone: Optional[str] = None


def set_clock(fn: Optional[Callable[[], dt.datetime]], zone: Optional[str] = None) -> None:
    """Tests: a fixed clock (aware datetimes) and the zone name it stands for; None restores Hermes'."""
    global _clock, _zone
    _clock, _zone = fn, zone


def now() -> dt.datetime:
    if _clock is not None:
        return _clock()
    try:
        import hermes_time

        return hermes_time.now()
    except Exception:
        return dt.datetime.now().astimezone()


def today() -> dt.date:
    return now().date()


def iso(at: Optional[dt.datetime] = None) -> str:
    return (at or now()).isoformat(timespec="seconds")


def zone_name() -> str:
    """The configured IANA zone, or "" when Hermes uses server-local time."""
    if _zone is not None:
        return _zone
    try:
        import hermes_time

        return hermes_time.get_timezone_name() or ""
    except Exception:
        return ""


# --- failure classification (constraint 2) ---------------------------------------------------------

_DETECT: Any = None
_DETECT_LOADED = False


def _detector():
    global _DETECT, _DETECT_LOADED
    if not _DETECT_LOADED:
        _DETECT_LOADED = True
        try:
            from agent.display import _detect_tool_failure

            _DETECT = _detect_tool_failure
        except Exception:
            _DETECT = None
    return _DETECT


def set_detector(fn: Any) -> None:
    """Tests: a stand-in for Hermes' `_detect_tool_failure` (None = use the hook's status)."""
    global _DETECT, _DETECT_LOADED
    _DETECT, _DETECT_LOADED = fn, True


def failed(tool: str, result: Any, status: str = "") -> bool:
    """Hermes' own verdict on this call: `_detect_tool_failure(tool, result)[0]`; the hook's
    `status == "error"` only when that function cannot be imported."""
    detect = _detector()
    if detect is not None:
        try:
            return bool(detect(tool, result)[0])
        except Exception:
            pass
    return str(status or "").lower() == "error"


def detector_source() -> str:
    return "hermes" if _detector() is not None else "hook status"


# --- unattended detection (constraint 6; copied from Eselsbrücke's hermes_bridge) ------------------
# Restated from Hermes' own rule (tools/approval_context.py is not a public import): a run is
# unattended when it is a cron job (or a session on the cron surface), a single-query `hermes chat -q`
# / `-z` run, or a session on the webhook, msgraph_webhook or api_server surface. Under
# `plugins.isolation: host` the gateway's markers are not visible in the host child, so a CLI or
# one-shot surface there fails closed (Q2), and so does a failed `current_cron_execution()` call.

UNATTENDED_PLATFORMS = frozenset({"webhook", "msgraph_webhook", "api_server", "cron"})
HOST_BLIND_SURFACES = frozenset({"", "cli", "oneshot"})


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _session_env(name: str) -> str:
    try:
        from gateway.session_context import get_session_env

        return get_session_env(name, "") or ""
    except Exception:
        return os.environ.get(name, "") or ""


def _finite_turn() -> Optional[bool]:
    """True on a gateway-admitted `chat -q`/`-z` turn; None when the private marker cannot be read."""
    try:
        from gateway.session_finite import finite_turn_required
    except ImportError:
        return None
    try:
        return finite_turn_required() is True
    except Exception:
        return None


def unattended_reason(ctx: Any = None, environ: Optional[dict] = None) -> Optional[str]:
    """Why no person is at the keyboard, or None in an attended chat."""
    env = os.environ if environ is None else environ
    host = env.get("HERMES_PLUGIN_HOST_PROCESS") == "1"
    surface = ""
    try:
        surface = (ctx.session_surface() if ctx is not None else "") or ""
    except Exception:
        surface = ""
    surface = str(surface).strip().lower()
    if host and surface in HOST_BLIND_SURFACES:
        return ("Unblockbrücke runs in a plugin host (plugins.isolation: host), where a one-shot or CLI turn "
                "cannot be told from an attended one; set plugins.isolation: in_process to allow it here")
    cron, unknown = False, False
    try:
        cron = ctx is not None and ctx.current_cron_execution() is not None
    except Exception:
        # A failed or missing call (an older Hermes) says nothing about cron. Over the host wire that
        # fails closed (Q2) with its own reason; in process the session markers below still decide.
        unknown = host
    if cron or _truthy(_session_env("HERMES_CRON_SESSION")):
        return "a scheduled job"
    if unknown:
        return ("Unblockbrücke could not ask Hermes whether this run is a scheduled job (plugin host); update "
                "Hermes, or set plugins.isolation: in_process")
    finite = _finite_turn()
    if finite is None and not host:
        return "this Hermes version moved its one-shot marker (gateway.session_finite); update Unblockbrücke"
    if finite or _truthy(_session_env("HERMES_SINGLE_QUERY_SESSION")):
        return "a single-query run (hermes chat -q or -z)"
    platform = surface or _session_env("HERMES_SESSION_PLATFORM").strip().lower()
    if platform in UNATTENDED_PLATFORMS:
        return f"the unattended {platform} surface"
    return None


# --- where the turn runs (0.2, AX-2) ---------------------------------------------------------------
# Read from Hermes' session markers, each in a try: a marker that moved answers "unknown", never an
# error. Under `plugins.isolation: host` most markers are not visible in the host child.

def _policy_source() -> str:
    try:
        from gateway.session_policy import active_policy

        policy = active_policy()
        return str(getattr(policy, "source", "") or "") if policy is not None else ""
    except Exception:
        return ""


def _delegated_child() -> bool:
    try:
        from agent.delegation_context import is_delegated_child_context

        return bool(is_delegated_child_context())
    except Exception:
        return False


LOCAL_CLI = frozenset({"cli", "tui", "oneshot", "tool", "local"})


def where(ctx: Any = None, environ: Optional[dict] = None) -> tuple[str, str]:
    """(code, platform): code is one of desktop, kanban, cron, cli, subagent, api, editor, webhook,
    messaging, unknown; platform names the messaging platform for `messaging`, else ""."""
    env = os.environ if environ is None else environ
    try:
        if ctx is not None and ctx.current_cron_execution() is not None:
            return "cron", ""
    except Exception:
        pass
    if _truthy(_session_env("HERMES_CRON_SESSION")):
        return "cron", ""
    source = (_policy_source() or _session_env("HERMES_SESSION_SOURCE")).strip().lower()
    if source == "kanban" or env.get("HERMES_KANBAN_TASK"):
        return "kanban", ""
    if source == "subagent" or _delegated_child():
        return "subagent", ""
    surface = ""
    try:
        surface = str((ctx.session_surface() if ctx is not None else "") or "")
    except Exception:
        surface = ""
    surface = (surface or _session_env("HERMES_SESSION_PLATFORM")).strip().lower()
    for name in (surface, source):  # the session's own surface first, then how the session was made
        if name in ("desktop", "gui"):
            return "desktop", ""
        if name in LOCAL_CLI:
            return "cli", ""
        if name == "api_server":
            return "api", ""
        if name == "acp":
            return "editor", ""
        if name in ("webhook", "msgraph_webhook"):
            return "webhook", ""
        if name == "cron":
            return "cron", ""
    if surface:
        return "messaging", surface[:40]
    return "unknown", ""


def route_unattended(environ: Optional[dict] = None) -> Optional[str]:
    """Why a page route runs without a person (R10), from the process's own markers only: a scheduled job
    or a single-query run. A route has no session, so the host-blind rule of `unattended_reason` does
    not apply (every route runs in the plugin host child under isolation)."""
    env = os.environ if environ is None else environ
    if _truthy(env.get("HERMES_CRON_SESSION")) or _truthy(_session_env("HERMES_CRON_SESSION")):
        return "a scheduled job"
    if _truthy(env.get("HERMES_SINGLE_QUERY_SESSION")) or _truthy(_session_env("HERMES_SINGLE_QUERY_SESSION")):
        return "a single-query run (hermes chat -q or -z)"
    return None


def as_json(text: Any) -> Any:
    try:
        return json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return None
