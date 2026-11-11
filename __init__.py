"""UnblockBrücke: cards to unblock yourself or your agent.

`register(ctx)` adds the agent tools in `REGISTERED`, the `/card` command, the
`transform_tool_result` hook for auto-draw (off by default) and the bundled skill. State lives in
`ctx.state.data_dir`; the dashboard routes (`dashboard/plugin_api.py`) compute the same folder per
call. Sibling modules load lazily: pytest imports this file on its own, and the package name differs
between Hermes, the dashboard and the tests.
"""
from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any

PLUGIN = "unblockbruecke"
TOOLSET = "unblockbruecke"
SKILL_NAME = "unblockbruecke"

# Agent tools registered by this version, each with a module under tools/. Each milestone adds its
# tools here and to plugin.yaml provides_tools together.
REGISTERED = {"unblockbruecke_card": "card", "unblockbruecke_decks": "decks"}

MODULES = ("store", "bridge", "settings", "decks", "draw", "journal", "service", "command", "autodraw", "editor",
           "tools.card", "tools.decks")

logger = logging.getLogger(__name__)


def _mod(name: str):
    return importlib.import_module(f".{name}", __package__ or __name__)


def _state_or_none(ctx) -> Any:
    try:
        state = ctx.state
    except Exception:
        return None
    return state if hasattr(state, "get") and hasattr(state, "set") and hasattr(state, "data_dir") else None


def make_store(ctx):
    """The data folder: `ctx.state.data_dir`, read per call so it follows the turn's profile."""
    store_mod = _mod("store")
    state = _state_or_none(ctx)
    if state is not None:
        return store_mod.Store(lambda: Path(state.data_dir))
    return store_mod.Store(lambda: store_mod.default_root())


def settings_reader(ctx):
    settings = _mod("settings")

    def read() -> dict:
        return settings.read(lambda key, default=None: ctx.get_config(key, default))

    return read


def autodraw_reader(ctx):
    """Only the `autodraw` setting, read the way `settings.read` reads it (one config read)."""
    settings = _mod("settings")
    default = settings.DEFAULTS["autodraw"]

    def on() -> bool:
        try:
            value = ctx.get_config("autodraw", default)
        except Exception:
            return default
        return settings.as_bool(default if value is None else value, default)

    return on


def make_handler(tool: str, ctx, store, read_settings):
    module = _mod(f"tools.{REGISTERED[tool]}")
    runtime = _mod("tools").Runtime
    bridge = _mod("bridge")

    def handler(args: dict, session_id: str = "", **_kwargs: Any) -> str:
        try:
            rt = runtime(store=store, settings=read_settings(), unattended=lambda: bridge.unattended_reason(ctx),
                         session_id=session_id or "", author="agent")
            result = module.handle(dict(args) if isinstance(args, dict) else {}, rt)
        except Exception as exc:  # never a traceback into the chat
            logger.warning("unblockbruecke: %s failed", tool, exc_info=True)
            result = {"ok": False, "error": "internal", "message": f"{type(exc).__name__}: {exc}"}
        return json.dumps(result, ensure_ascii=False)

    handler.__name__ = tool
    return handler


def register(ctx) -> None:
    for name in MODULES:
        _mod(name)  # a broken install fails at load, not mid-turn
    store = make_store(ctx)
    read_settings = settings_reader(ctx)
    for tool, module in REGISTERED.items():
        schema = _mod(f"tools.{module}").SCHEMA
        ctx.register_tool(name=tool, toolset=TOOLSET, schema=schema, handler=make_handler(tool, ctx, store, read_settings),
                          description=schema["description"], emoji="🃏")
    if callable(getattr(ctx, "register_command", None)):
        ctx.register_command("card", _mod("command").make_handler(lambda: store, read_settings),
                             description="Draw an UnblockBrücke card: /card, /card <deck>, /card agent, /card decks",
                             args_hint="[deck|agent|decks]")
    if callable(getattr(ctx, "register_hook", None)):
        bridge = _mod("bridge")
        hook = _mod("autodraw").AutoDraw(lambda: store, read_settings, lambda: bridge.unattended_reason(ctx),
                                         autodraw_on=autodraw_reader(ctx))
        ctx.register_hook("transform_tool_result", hook)
    _register_skill(ctx)


def _register_skill(ctx) -> None:
    skill = Path(__file__).resolve().parent / "skills" / SKILL_NAME / "SKILL.md"
    if callable(getattr(ctx, "register_skill", None)) and skill.exists():
        try:
            ctx.register_skill(SKILL_NAME, skill, "Use UnblockBrücke: when to offer a card, how to coach with a "
                                                  "card's agent face, auto-draw, the deck file format.")
        except ValueError:
            pass  # already registered by an earlier load in this process
