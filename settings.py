"""Plugin settings with their defaults.

`ctx.get_config` applies no `config_schema` defaults, so every read goes through `read()` with the
`DEFAULTS` below, and numbers are clamped here. `tests/test_autodraw.py` checks `DEFAULTS` against
`plugin.yaml`. Settings are read on every call (a `config set` applies on the next tool call).

`RETIRED` keys left `config_schema` (Hermes' settings form) but are still read:
- `show_in_sidebar` (left in 0.1.4): the sidebar switch moved to the Desktop (per computer,
  ctx.storage), and a Desktop with no stored choice seeds it once from `GET /settings`, so the old
  value stays readable there.
- `autodraw_decks` (left in 0.2.0): each deck's Hermes switch decides. A stored list seeds those switches
  once (`decks.seed_hermes_switches`); no answer shows it.
`autodraw_per_turn` (left in 0.2.0) is gone: one card per turn, always.

`SETTABLE`: the keys the page may write through `POST /setting` (five keys, no secret).
"""
from __future__ import annotations

from typing import Any, Callable

DEFAULTS: dict[str, Any] = {
    "autodraw": False,
    "autodraw_threshold": 3,
    "card_of_day": True,
    "learning": True,
    "show_in_statusbar": True,
    "show_in_sidebar": True,
    "autodraw_decks": ["agent-unblock"],
}

RETIRED = frozenset({"show_in_sidebar", "autodraw_decks"})
HIDDEN = frozenset({"autodraw_decks"})  # read for the one-time seed, never answered
SETTABLE = ("autodraw", "autodraw_threshold", "card_of_day", "learning", "show_in_statusbar")

RANGES = {"autodraw_threshold": (2, 6)}


def as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str) and value.strip():
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def as_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        number = int(value) if not isinstance(value, bool) else default
    except (TypeError, ValueError, OverflowError):  # OverflowError: `.inf` is a valid YAML float
        number = default
    return max(lo, min(hi, number))


def as_slugs(value: Any, default: list) -> list:
    if isinstance(value, str):
        value = [v.strip() for v in value.split(",")]
    if not isinstance(value, (list, tuple)):
        return list(default)
    return [str(v).strip() for v in value if str(v).strip()]


def read(get: Callable[[str, Any], Any]) -> dict:
    """All settings, defaulted and clamped. `get(key, default)` is `ctx.get_config` or a stand-in."""
    def raw(key: str) -> Any:
        try:
            value = get(key, DEFAULTS[key])
        except Exception:
            return DEFAULTS[key]
        return DEFAULTS[key] if value is None else value

    out: dict[str, Any] = {}
    for key, default in DEFAULTS.items():
        value = raw(key)
        if isinstance(default, bool):
            out[key] = as_bool(value, default)
        elif key in RANGES:
            out[key] = as_int(value, default, *RANGES[key])
        elif isinstance(default, list):
            out[key] = as_slugs(value, default)
        else:
            out[key] = value
    return out


def public(settings: dict) -> dict:
    """The settings an answer shows: every key but the hidden legacy ones."""
    return {k: v for k, v in settings.items() if k not in HIDDEN}


def check_value(key: str, value: Any) -> Any:
    """The value `POST /setting` may save for `key`, or ValueError. No clamping: a value out of range is
    refused, so the page never shows one number while another is saved."""
    if key not in SETTABLE:
        raise KeyError(key)
    if key in RANGES:
        lo, hi = RANGES[key]
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            raise ValueError(f"{key} must be a whole number from {lo} to {hi}")
        return value
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false")
    return value


def read_from_config_file(home_config: Any) -> dict:
    """Settings from a loaded `config.yaml` dict (routes have no ctx)."""
    entry = {}
    try:
        entry = ((home_config or {}).get("plugins") or {}).get("entries", {}).get("unblockbruecke") or {}
    except AttributeError:
        entry = {}
    settings = entry.get("settings") or {}
    legacy = entry.get("config") or {}

    def get(key: str, default: Any = None) -> Any:
        if isinstance(settings, dict) and key in settings:
            return settings[key]
        if isinstance(legacy, dict) and key in legacy:
            return legacy[key]
        return default

    return read(get)


def saved_value(key: str) -> Any:
    """The value the bound profile's config now holds for one setting (None when unset), read through
    Hermes' loader, so an administrator's pinned value counts as what is in force."""
    from hermes_cli.config import load_config_readonly

    entry = (((load_config_readonly() or {}).get("plugins") or {}).get("entries") or {}).get("unblockbruecke") or {}
    values = entry.get("settings") if isinstance(entry, dict) else None
    return values.get(key) if isinstance(values, dict) else None


def load_route_settings() -> dict:
    """The bound profile's settings, read from its config file (dashboard routes)."""
    try:
        from hermes_cli.config import load_config_readonly

        return read_from_config_file(load_config_readonly() or {})
    except Exception:
        return dict(DEFAULTS)
