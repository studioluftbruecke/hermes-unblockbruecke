"""Where the plugin reads Hermes' state: public surfaces, plus two guarded private markers that
Hermes has no public signal for (the one-shot marker and the delegated-child marker).

- `now()`, `today()`, `zone_name()`: Hermes' own time zone (`timezone` setting, `HERMES_TIMEZONE`
  overrides, empty means server-local), read through `hermes_cli.config`. Tests replace the clock
  with `set_clock()`.
- `failed(tool, result, status)`: whether Hermes counts a tool call as failed: the `status` Hermes
  passes to the `transform_tool_result` hook, less the guardrail's refusals of repeated calls.
- `unattended_reason(ctx)`: why no person is there to approve, or None in an attended chat.
- `where(ctx)`: where the turn runs (Desktop chat, kanban task, cron job, CLI, ...) for the journal;
  `route_unattended()`: the same markers for a page route.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

# --- time -----------------------------------------------------------------------------------------

_clock: Optional[Callable[[], dt.datetime]] = None
_zone: Optional[str] = None


def set_clock(fn: Optional[Callable[[], dt.datetime]], zone: Optional[str] = None) -> None:
    """Tests: a fixed clock (aware datetimes) and the zone name it stands for; None restores Hermes'."""
    global _clock, _zone
    _clock, _zone = fn, zone


def _configured_zone() -> tuple[str, Optional[ZoneInfo]]:
    """Hermes' time zone rule, read through its public config: `HERMES_TIMEZONE` (except in a
    multiplexed gateway, where that variable holds the default profile's value), else the profile's
    `timezone` setting; ("", None) means server-local time, also for a name that is no IANA zone."""
    name = ""
    try:
        from agent.secret_scope import is_multiplex_active

        multiplexed = is_multiplex_active()
    except Exception:
        multiplexed = False
    if not multiplexed:
        name = os.environ.get("HERMES_TIMEZONE", "").strip()
    if not name:
        try:
            from hermes_cli.config import load_config_readonly

            value = load_config_readonly().get("timezone", "")
            name = value.strip() if isinstance(value, str) else ""
        except Exception:
            name = ""
    if not name:
        return "", None
    try:
        return name, ZoneInfo(name)
    except Exception:
        return "", None


def now() -> dt.datetime:
    if _clock is not None:
        return _clock()
    zone = _configured_zone()[1]
    return dt.datetime.now(zone) if zone is not None else dt.datetime.now().astimezone()


def today() -> dt.date:
    return now().date()


def iso(at: Optional[dt.datetime] = None) -> str:
    return (at or now()).isoformat(timespec="seconds")


def zone_name() -> str:
    """The configured IANA zone, or "" when Hermes uses server-local time."""
    if _zone is not None:
        return _zone
    return _configured_zone()[0]


# --- failure classification ---------------------------------------------------------------------

GUARDRAIL_REFUSAL_KEY = "guardrail_refusal"


def failed(tool: str, result: Any, status: str = "") -> bool:
    """Hermes' own verdict on this call, as the `transform_tool_result` hook receives it: `status` is
    "error" for a failed call. Two exceptions, Hermes' own: a call its guardrail refused as a repeat
    (`{"guardrail_refusal": true, ...}`), and a `terminal` call whose exit code is 0 or missing (its
    `error` text is then a warning). The hook's status says "error" for both, but Hermes' loop does not
    count them as failed calls, so neither does auto-draw."""
    if str(status or "").strip().lower() != "error":
        return False
    data = as_json(result.strip()) if isinstance(result, str) and result.lstrip().startswith("{") else result
    if not isinstance(data, dict):
        return True
    if tool == "terminal" and data.get("exit_code") in (None, 0):
        return False
    return data.get(GUARDRAIL_REFUSAL_KEY) is not True


# --- is a person there to approve? -----------------------------------------------------------------
# Hermes' own rule restated (its module is not a public import): a run is unattended when it is a cron
# job, a session on the webhook, msgraph_webhook or api_server surface, a single-query `hermes chat -q`
# / `-z` run (HERMES_SINGLE_QUERY_SESSION, or the gateway's one-shot marker), and, inside the plugin
# host (plugins.isolation: host), any CLI or one-shot surface, where the turn's own markers are not
# visible. A marker that cannot be read counts as unattended.

UNATTENDED_PLATFORMS = frozenset({"webhook", "msgraph_webhook", "api_server", "cron"})
HOST_BLIND_SURFACES = frozenset({"", "cli", "oneshot"})
NO_SIGNAL = "this Hermes version does not say whether a person is present, so writes are refused; update the plugin"


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _session_env(name: str) -> str:
    try:
        from gateway.session_context import get_session_env

        return get_session_env(name, "") or ""
    except Exception:
        return os.environ.get(name, "") or ""


def _finite_turn() -> Optional[bool]:
    """True on a gateway-admitted `chat -q`/`-z` turn; None when the marker cannot be read."""
    try:
        # Private on purpose: Hermes 0.23.1 has no public signal for a gateway-admitted chat -q/-z turn.
        from gateway.session_finite import finite_turn_required
    except ImportError:
        return None
    try:
        return finite_turn_required() is True
    except Exception:
        return None


def unattended_reason(ctx: Any = None, environ: Optional[dict] = None) -> Optional[str]:
    """Why no person is there to approve, or None in an attended chat."""
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
        # fails closed with its own reason; in process the session markers below still decide.
        unknown = host
    if cron or _truthy(_session_env("HERMES_CRON_SESSION")):
        return "a scheduled job"
    if unknown:
        return ("Unblockbrücke could not ask Hermes whether this run is a scheduled job (plugin host); update "
                "Hermes, or set plugins.isolation: in_process")
    if _truthy(_session_env("HERMES_SINGLE_QUERY_SESSION")):
        return "a single-query run (hermes chat -q or -z)"
    platform = surface or _session_env("HERMES_SESSION_PLATFORM").strip().lower()
    if platform in UNATTENDED_PLATFORMS:
        return f"the unattended {platform} surface"
    finite = _finite_turn()
    if finite is None:
        return NO_SIGNAL
    if finite:
        return "a single-query run (hermes chat -q or -z)"
    return None


# --- where the turn runs ---------------------------------------------------------------------------
# Read from Hermes' session markers, each in a try: a marker that moved answers "unknown", never an
# error. Under `plugins.isolation: host` most markers are not visible in the host child.

def _delegated_child() -> bool:
    try:
        # Private on purpose, for a journal label only: Hermes 0.23.1 has no public signal for a
        # delegate_task child. When it moves, a child's draw shows the parent's surface instead.
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
    source = _session_env("HERMES_SESSION_SOURCE").strip().lower()
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
    """Why a page route runs without a person, from the process's own markers only: a scheduled job
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
