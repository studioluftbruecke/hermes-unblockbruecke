"""The agent tools. Each module has `SCHEMA` and `handle(args, rt) -> dict`; `__init__.register` wraps
them (JSON answer, no traceback into the chat)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Runtime:
    store: Any
    settings: dict
    unattended: Callable[[], Optional[str]] = field(default=lambda: None)
    session_id: str = ""
    author: str = "agent"
