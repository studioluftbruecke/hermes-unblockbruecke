"""Backend routes for the UnblockBrücke Cards Desktop half, mounted at `/api/plugins/unblockbruecke/`.

Shapes: `experiments/unblockbruecke/v0.1-contract.md` §5 in the monorepo; the logic is `api.py`
(tested without FastAPI). Hermes loads this file as a standalone module, so the plugin folder is
loaded as a package by path. The data folder and the settings are read per call from the bound
Hermes home.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

PLUGIN = "unblockbruecke"
_PACKAGE = "hermes_unblockbruecke_dashboard"
log = logging.getLogger(__name__)


def _refusal(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "schema": 1, "error": code, "message": message}, status_code=status)


class ContractRoute(APIRoute):
    """Every answer keeps the contract's shape: a body FastAPI cannot parse (invalid JSON) is a 400
    `invalid`, and an unexpected error is a 500 `internal` without traceback text (the log keeps it).
    An APIRouter cannot carry exception handlers, so the route class wraps each handler."""

    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def guarded(request: Request):
            try:
                return await handler(request)
            except HTTPException:
                raise
            except RequestValidationError:
                return _refusal(400, "invalid", "the request is not valid JSON or has a field of the wrong type")
            except Exception:  # noqa: BLE001 - the public door answers JSON, whatever broke behind it
                log.exception("unblockbruecke route %s %s failed", request.method, request.url.path)
                return _refusal(500, "internal", "the plugin hit an unexpected error; the gateway log has the details")
        return guarded


router = APIRouter(route_class=ContractRoute)


def _plugin():
    module = sys.modules.get(_PACKAGE)
    if module is not None:
        return module
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(_PACKAGE, root / "__init__.py", submodule_search_locations=[str(root)])
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the {PLUGIN} package")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PACKAGE] = module
    spec.loader.exec_module(module)
    return module


def _api():
    _plugin()
    return importlib.import_module(f"{_PACKAGE}.api")


def _reply(result: "tuple[int, dict]") -> JSONResponse:
    status, body = result
    return JSONResponse(body, status_code=status)


# Sync handlers: FastAPI runs them on a worker thread.

@router.get("/health")
def health() -> JSONResponse:
    return _reply(_api().health())


@router.get("/decks")
def decks_get() -> JSONResponse:
    return _reply(_api().decks_get())


@router.post("/decks/import")
def decks_import(body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().import_deck(body))


@router.get("/decks/{slug}")
def deck_get(slug: str) -> JSONResponse:
    return _reply(_api().deck_get(slug))


@router.put("/decks/{slug}")
def deck_save(slug: str, body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().save(slug, body))


@router.post("/decks/{slug}/preview")
def deck_preview(slug: str, body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().preview(slug, body))


@router.get("/decks/{slug}/versions")
def deck_versions(slug: str) -> JSONResponse:
    return _reply(_api().versions(slug))


@router.post("/decks/{slug}/restore")
def deck_restore(slug: str, body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().restore(slug, body))


@router.post("/decks/{slug}/delete")
def deck_delete(slug: str, body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().delete(slug, body))


@router.get("/decks/{slug}/export")
def deck_export(slug: str) -> JSONResponse:
    return _reply(_api().export(slug))


@router.post("/draw")
def draw(body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().draw(body))


@router.get("/today")
def today() -> JSONResponse:
    return _reply(_api().today())


@router.get("/journal")
def journal_get(limit: Optional[str] = Query("50"), by: Optional[str] = Query(""),
                session: Optional[str] = Query("")) -> JSONResponse:
    return _reply(_api().journal_get(limit, by or "", session or ""))


@router.post("/journal/rate")
def journal_rate(body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().rate(body))


@router.post("/journal/reset")
def journal_reset(body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().reset(body))


@router.get("/settings")
def settings_get() -> JSONResponse:
    return _reply(_api().settings_get())


@router.put("/settings/decks")
def settings_decks(body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().switch(body))
