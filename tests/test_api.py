"""M5 routes (contract §5) through api.py, without FastAPI: shapes, statuses, op_id, the seam the
Desktop half reads."""
import pytest

from ub_fakes import deck_doc, make_store, sub, yaml_text


@pytest.fixture
def api(tmp_path):
    mod = sub("api")
    store = make_store(tmp_path)
    settings = sub("settings").read(lambda k, d=None: {"show_in_sidebar": False}.get(k, d))
    mod.configure(lambda: store, lambda: settings)
    yield mod
    mod.configure(None, None)


def test_health_and_settings(api):
    status, body = api.health()
    assert status == 200 and body["schema"] == 1 and body["version"] == "0.1.3"
    status, body = api.settings_get()
    assert body["settings"]["show_in_sidebar"] is False and body["settings"]["autodraw"] is False


def test_decks_list_and_one_deck_with_stats(api):
    status, body = api.decks_get()
    assert status == 200 and [d["deck"] for d in body["decks"]][:2] == ["agent-unblock", "coding"]
    assert body["autodraw"] == {"on": False, "decks": ["agent-unblock"], "threshold": 3}
    api.draw({"deck": "design"})
    status, deck = api.deck_get("design")
    assert status == 200 and deck["deck"]["editable"] is False and deck["deck"]["edits_save_as"] == "design-own"
    assert sum(c["stats"]["drawn"] for c in deck["deck"]["cards"]) == 1
    assert api.deck_get("nope")[0] == 404


def test_draw_today_journal_rate_reset(api):
    status, out = api.draw({"context": "human", "op_id": "op-1"})
    assert status == 200 and out["card"]["deck"] == "human-unblock" and out["card"]["face"] == "human"
    dup = api.draw({"context": "human", "op_id": "op-1"})
    assert dup == (200, {"ok": True, "schema": 1, "duplicate": True, "op_id": "op-1"})
    status, day = api.today()
    assert day["enabled"] is True and day["date"] == "2026-11-10" and day["card"]["deck"] == "human-unblock"
    status, rated = api.rate({"draw_id": out["draw_id"], "rating": "helped"})
    assert rated["rated"]["rating"] == "helped"
    assert api.rate({"draw_id": "nope", "rating": "helped"})[0] == 404
    status, j = api.journal_get(10)
    assert j["draws"][0]["rating"] == "helped" and j["draws"][0]["view"]["human"] == out["card"]["human"]
    assert j["totals"] == {"draws": 1, "helped": 1, "not_now": 0, "by_auto": 0} and j["learning"] is True
    assert api.reset({})[1]["reset_at"]
    assert api.draw({"context": "sideways"})[0] == 400
    assert api.draw({"op_id": "bad id with spaces"})[0] == 400


def test_edit_cycle_through_routes(api):
    change = {"changes": {"add": [{"human": "Hum it first.", "agent": "Ask for a hummed idea, then build from it.",
                                   "tags": ["start"]}], "meta": {"glossary": {"start": "Gets something going."}}}}
    status, pv = api.preview("my-music", change)
    assert status == 200 and pv["target"] == "my-music" and pv["yaml"].startswith("schema: 1") and pv["confirm"]
    bad = api.save("my-music", {**change, "confirm": "wrong"})
    assert bad[0] == 409 and bad[1]["error"] == "stale_preview" and bad[1]["preview"]["confirm"] == pv["confirm"]
    status, saved = api.save("my-music", {**change, "confirm": pv["confirm"], "op_id": "save-1"})
    assert status == 200 and saved["version"] == 1 and saved["undo"] == {"delete": "my-music"}
    assert api.save("my-music", {**change, "confirm": pv["confirm"], "op_id": "save-1"})[1]["duplicate"] is True
    assert api.versions("my-music")[1]["versions"][0]["author"] == "user"
    status, exp = api.export("my-music")
    assert exp["file_name"] == "my-music.yaml" and "Hum it first." in exp["yaml"]
    status, gone = api.delete("my-music", {})
    assert status == 200 and gone["undo"]["restore"] == 2
    assert api.restore("my-music", {"version": 2})[0] == 200
    invalid = api.preview("my-music", {"changes": {"add": [{"human": "x" * 95, "agent": "ok"}]}})
    assert invalid[0] == 422 and invalid[1]["problems"][0]["rule"] == "length_human"
    assert api.delete("coding", {})[0] == 400


def test_import_and_switch(api):
    text = yaml_text(deck_doc("bought", prefix="bo"))
    status, out = api.import_deck({"yaml": text, "file_name": "bought.yaml"})
    assert status == 200 and out["source"] == "imported"
    again = api.import_deck({"yaml": text})
    assert again[0] == 409 and again[1]["error"] == "exists"
    assert api.import_deck({"yaml": "deck: ["})[0] == 422
    assert api.import_deck({})[0] == 400
    status, sw = api.switch({"deck": "bought", "auto": True})
    assert sw["switch"] == {"draw": True, "auto": True}
    assert api.switch({"deck": "nope", "draw": False})[0] == 404
    assert api.switch({"deck": "coding", "draw": "no"})[0] == 400
    assert api.switch({"deck": "coding"})[0] == 400


def test_session_filter_for_the_chip(api, tmp_path):
    journal = sub("journal")
    store = api.store()
    journal.record_draw(store, by="auto", deck="agent-unblock", card="ag-03", face="agent", context="auto",
                        session_id="sess-1", turn_id="sess-1:x", tool="terminal", streak=3, attached=True)
    journal.record_draw(store, by="auto", deck="agent-unblock", card="ag-08", face="agent", context="auto",
                        session_id="sess-2")
    status, body = api.journal_get(1, "auto", "sess-1")
    assert [d["card"] for d in body["draws"]] == ["ag-03"] and body["draws"][0]["view"]["face"] == "agent"


HOSTILE = [
    ("switch", ({"deck": ["coding"], "draw": True},)),
    ("switch", ({"deck": {"a": 1}, "auto": False},)),
    ("draw", ({"decks": 5},)),
    ("draw", ({"decks": True},)),
    ("preview", ("my-deck", {"changes": {"remove": 5}})),
    ("preview", ("my-deck", {"changes": {"meta": ["name"]}})),
    ("preview", ("my-deck", {"changes": {"meta": "name"}})),
    ("preview", ("agent-unblock", {"changes": {"edit": 5}})),
    ("preview", ("agent-unblock", {"changes": {"edit": [{"id": "ag-01", "tags": 5}]}})),
    ("preview", ("my-deck", {"changes": {"add": [{"human": "Say it.", "agent": "Write the goal.", "tags": True}]}})),
    ("preview", ("my-deck", {"changes": {"add": 7}})),
    ("save", ("my-deck", {"changes": {"remove": 5}, "confirm": "x"})),
]


@pytest.mark.parametrize("name,args", HOSTILE, ids=[f"{n}-{i}" for i, (n, _) in enumerate(HOSTILE)])
def test_wrong_types_answer_400_invalid_in_the_contract_shape(api, name, args):
    """UI-01: a body of the wrong type is a 4xx refusal in the contract shape, never an exception."""
    status, body = getattr(api, name)(*args)
    assert 400 <= status < 500, (status, body)
    assert body["ok"] is False and body["schema"] == 1 and isinstance(body["error"], str) and isinstance(body["message"], str)


def test_guard_maps_type_and_overflow_errors_to_invalid(api):
    """UI-01: _guard is the last line of defence for TypeError, AttributeError, ValueError, OverflowError."""
    for exc in (TypeError("x"), AttributeError("x"), ValueError("x"), OverflowError("x")):
        def boom(exc=exc):
            raise exc
        status, body = api._guard(boom)()
        assert status == 400 and body["error"] == "invalid" and body["ok"] is False and body["schema"] == 1, exc
        assert "Traceback" not in body["message"]


def _router_client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    import importlib.util
    import pathlib

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    path = pathlib.Path(sub("api").__file__).resolve().parent / "dashboard" / "plugin_api.py"
    spec = importlib.util.spec_from_file_location("ub_plugin_api_client", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    app = FastAPI()
    app.include_router(mod.router, prefix="/p")
    return mod, TestClient(app, raise_server_exceptions=False)


def _contract(resp) -> dict:
    body = resp.json()
    assert body["ok"] is False and body["schema"] == 1 and isinstance(body["error"], str) and isinstance(body["message"], str), body
    return body


def test_router_answers_bad_json_and_bad_query_in_the_contract_shape(tmp_path):
    """UI-02: invalid JSON and a bad query param answer in the contract shape, not FastAPI's detail list."""
    mod, client = _router_client()
    api = mod._api()
    store = make_store(tmp_path)
    settings = sub("settings").read(lambda k, d=None: d)
    api.configure(lambda: store, lambda: settings)
    try:
        r = client.post("/p/draw", content=b"{not json", headers={"content-type": "application/json"})
        assert r.status_code == 400 and _contract(r)["error"] == "invalid"
        r = client.get("/p/journal?limit=abc")
        assert r.status_code == 200 and r.json()["ok"] is True, r.text
        r = client.get("/p/journal?limit=99999999999999999999999")
        assert r.status_code == 200 and r.json()["ok"] is True, r.text
        r = client.put("/p/settings/decks", json={"deck": ["coding"], "draw": True})
        assert r.status_code == 400 and _contract(r)["error"] == "invalid"
    finally:
        api.configure(None, None)


def test_router_never_answers_a_plain_text_500(tmp_path, monkeypatch):
    """UI-01/UI-12: an unexpected error still answers JSON in the contract shape, without traceback text."""
    mod, client = _router_client()
    api = mod._api()

    def broken():
        raise KeyError("boom")
    monkeypatch.setattr(api, "health", broken)
    r = client.get("/p/health")
    assert r.status_code == 500
    body = _contract(r)
    assert body["error"] == "internal" and "Traceback" not in r.text


def test_router_mounts_every_contract_route():
    """The FastAPI adapter declares exactly the contract's routes (skipped where FastAPI is missing)."""
    pytest.importorskip("fastapi")
    import importlib.util
    import pathlib

    path = pathlib.Path(sub("api").__file__).resolve().parent / "dashboard" / "plugin_api.py"
    spec = importlib.util.spec_from_file_location("ub_plugin_api_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    routes = {(next(iter(r.methods)), r.path) for r in mod.router.routes}
    assert routes == {("GET", "/health"), ("GET", "/decks"), ("GET", "/decks/{slug}"), ("POST", "/draw"),
                      ("GET", "/today"), ("GET", "/journal"), ("POST", "/journal/rate"), ("POST", "/journal/reset"),
                      ("POST", "/decks/{slug}/preview"), ("PUT", "/decks/{slug}"), ("GET", "/decks/{slug}/versions"),
                      ("POST", "/decks/{slug}/restore"), ("POST", "/decks/{slug}/delete"), ("POST", "/decks/import"),
                      ("GET", "/decks/{slug}/export"), ("GET", "/settings"), ("PUT", "/settings/decks")}
