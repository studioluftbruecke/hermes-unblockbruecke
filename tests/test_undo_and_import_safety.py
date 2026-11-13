"""Undo never throws away text the user wrote by hand,
an import says whether it replaced a deck, export stays out of the plugin's own files, the host-mode
unattended reason, and short rule messages."""
import pathlib

import pytest

from ub_fakes import FakeCtx, card, deck_doc, load_plugin, make_store, sub, write_user_deck, yaml_text

SLUG = "mine"


def save_doc(store, doc, replace=False):
    editor = sub("editor")
    pv = editor.preview(store, doc["deck"], deck=doc)
    assert pv["ok"], pv
    extra = {"replace": True} if replace else {}
    return editor.save(store, doc["deck"], pv["confirm"], "user", deck=doc, **extra)


def import_doc(store, doc, replace=False):
    return sub("editor").import_text(store, yaml_text(doc), "user", replace=replace)


def apply_undo(store, slug, undo):
    editor = sub("editor")
    if "restore" in undo:
        return editor.restore(store, slug, undo["restore"], "user")
    return editor.delete(store, undo["delete"], "user")


def deck_name(store, slug):
    deck = sub("decks").catalog(store)["decks"].get(slug)
    return deck and deck["name"]


def broken_hand_file(store):
    doc = deck_doc(SLUG, prefix="mi", license="own", name="Hand made")
    doc["cards"][0]["human"] = "x" * 200  # one rule broken: too long, so the deck does not load
    path = write_user_deck(store, doc)
    return path, path.read_text(encoding="utf-8")


# --- hand-written text is kept -------

def test_first_save_over_a_hand_written_deck_undoes_to_the_hand_text(tmp_path):
    """Fixed: the first editor save answered undo {delete}, which threw the hand text away."""
    store = make_store(tmp_path)
    write_user_deck(store, deck_doc(SLUG, prefix="mi", license="own", name="Hand made"))
    out = save_doc(store, deck_doc(SLUG, prefix="mi", license="own", name="Edited"))
    assert "restore" in out["undo"], out["undo"]
    apply_undo(store, SLUG, out["undo"])
    assert deck_name(store, SLUG) == "Hand made"


def test_a_hand_edit_after_a_save_is_kept_before_the_next_save(tmp_path):
    """The same rule when the file was changed by hand after an editor save."""
    store = make_store(tmp_path)
    save_doc(store, deck_doc(SLUG, prefix="mi", license="own", name="First"))
    write_user_deck(store, deck_doc(SLUG, prefix="mi", license="own", name="Hand edit"))
    out = save_doc(store, deck_doc(SLUG, prefix="mi", license="own", name="Second"))
    apply_undo(store, SLUG, out["undo"])
    assert deck_name(store, SLUG) == "Hand edit"


def test_save_over_a_broken_hand_file_needs_replace_and_keeps_it(tmp_path):
    """A hand file that breaks a rule is not in the catalog, and a save of
    a new deck of that name overwrote it without a version."""
    store = make_store(tmp_path)
    editor = sub("editor")
    path, hand = broken_hand_file(store)
    with pytest.raises(editor.EditError) as err:
        save_doc(store, deck_doc(SLUG, prefix="mi", license="own", name="New"))
    assert err.value.code == "exists"
    assert path.read_text(encoding="utf-8") == hand
    out = save_doc(store, deck_doc(SLUG, prefix="mi", license="own", name="New"), replace=True)
    assert deck_name(store, SLUG) == "New" and "restore" in out["undo"], out["undo"]
    apply_undo(store, SLUG, out["undo"])
    assert path.read_text(encoding="utf-8") == hand


def test_agent_save_over_a_broken_hand_file_needs_replace(tmp_path):
    """The agent's tool takes the same `replace` flag for save."""
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    store = make_store(tmp_path)
    path, hand = broken_hand_file(store)
    doc = deck_doc(SLUG, prefix="mi", license="own", name="New")
    pv = ctx.call("unblockbruecke_decks", action="preview", deck=SLUG, content=doc)
    assert pv["ok"], pv
    refused = ctx.call("unblockbruecke_decks", action="save", deck=SLUG, content=doc, confirm=pv["confirm"])
    assert refused["ok"] is False and refused["error"] == "exists"
    assert path.read_text(encoding="utf-8") == hand
    saved = ctx.call("unblockbruecke_decks", action="save", deck=SLUG, content=doc, confirm=pv["confirm"], replace=True)
    assert saved["ok"] is True and "restore" in saved["undo"], saved


def test_import_over_a_broken_hand_file_needs_replace_and_keeps_it(tmp_path):
    """Fixed: import without replace was ok and answered undo {delete}."""
    store = make_store(tmp_path)
    editor = sub("editor")
    path, hand = broken_hand_file(store)
    with pytest.raises(editor.EditError) as err:
        import_doc(store, deck_doc(SLUG, prefix="mi", name="Imported"))
    assert err.value.code == "exists"
    assert path.read_text(encoding="utf-8") == hand
    out = import_doc(store, deck_doc(SLUG, prefix="mi", name="Imported"), replace=True)
    assert "restore" in out["undo"], out
    apply_undo(store, SLUG, out["undo"])
    assert path.read_text(encoding="utf-8") == hand


def test_import_replace_over_a_hand_file_written_after_a_delete_keeps_it(tmp_path):
    """Fixed: the index ended with a deletion row, so the hand file was not kept."""
    store = make_store(tmp_path)
    editor = sub("editor")
    save_doc(store, deck_doc(SLUG, prefix="mi", license="own"))
    editor.delete(store, SLUG, "user")
    write_user_deck(store, deck_doc(SLUG, prefix="mi", license="own", name="Hand again"))
    out = import_doc(store, deck_doc(SLUG, prefix="mi", name="Imported"), replace=True)
    assert "restore" in out["undo"], out["undo"]
    apply_undo(store, SLUG, out["undo"])
    assert deck_name(store, SLUG) == "Hand again"


def test_restore_over_a_hand_edit_keeps_it_and_undo_brings_it_back(tmp_path):
    store = make_store(tmp_path)
    editor = sub("editor")
    save_doc(store, deck_doc(SLUG, prefix="mi", license="own", name="One"))
    save_doc(store, deck_doc(SLUG, prefix="mi", license="own", name="Two"))
    write_user_deck(store, deck_doc(SLUG, prefix="mi", license="own", name="Hand edit"))
    out = editor.restore(store, SLUG, 1, "user")
    assert deck_name(store, SLUG) == "One"
    apply_undo(store, SLUG, out["undo"])
    assert deck_name(store, SLUG) == "Hand edit"


def test_undo_of_a_restore_that_brought_a_deleted_deck_back_removes_it(tmp_path):
    """Fixed: that undo restored the deletion row's text, so the deck stayed."""
    store = make_store(tmp_path)
    editor = sub("editor")
    save_doc(store, deck_doc(SLUG, prefix="mi", license="own"))
    gone = editor.delete(store, SLUG, "user")
    back = editor.restore(store, SLUG, gone["undo"]["restore"], "user")
    assert back["undo"] == {"delete": SLUG}
    apply_undo(store, SLUG, back["undo"])
    assert SLUG not in sub("decks").catalog(store)["decks"]


# --- the import answer and its undo -----------------------------------------------------------------

def test_a_fresh_import_says_it_replaced_nothing_and_undo_deletes(tmp_path):
    """Fixed: the Desktop read every import with an undo as a replace. `replaced` says which it was."""
    store = make_store(tmp_path)
    out = import_doc(store, deck_doc("fresh-one", prefix="fr"))
    assert out["replaced"] is False and out["undo"] == {"delete": "fresh-one"}


def test_an_import_with_replace_says_so_and_undo_restores(tmp_path):
    store = make_store(tmp_path)
    save_doc(store, deck_doc(SLUG, prefix="mi", license="own", name="Mine by hand"))
    out = import_doc(store, deck_doc(SLUG, prefix="mi", name="Imported"), replace=True)
    assert out["replaced"] is True and out["undo"] == {"restore": out["version"] - 1}


def test_an_import_over_a_broken_hand_file_counts_as_a_replace(tmp_path):
    store = make_store(tmp_path)
    broken_hand_file(store)
    out = import_doc(store, deck_doc(SLUG, prefix="mi", name="Imported"), replace=True)
    assert out["replaced"] is True and "restore" in out["undo"]


def test_undo_of_a_re_import_brings_back_the_auto_switch(tmp_path):
    """An imported deck switched auto on, re-imported, undone: auto stayed off."""
    store = make_store(tmp_path)
    decks = sub("decks")
    import_doc(store, deck_doc(SLUG, prefix="mi", name="First import"))
    decks.set_switch(store, SLUG, auto=True)
    out = import_doc(store, deck_doc(SLUG, prefix="mi", name="Second import"), replace=True)
    assert decks.catalog(store)["decks"][SLUG]["switch"]["auto"] is False
    apply_undo(store, SLUG, out["undo"])
    deck = decks.catalog(store)["decks"][SLUG]
    assert deck["name"] == "First import" and deck["switch"]["auto"] is True and deck["source"] == "imported"


def test_a_plain_restore_keeps_todays_switch(tmp_path):
    """The re-import rule does not reach plain edits: restoring an older save keeps the switch as set now."""
    store = make_store(tmp_path)
    decks, editor = sub("decks"), sub("editor")
    save_doc(store, deck_doc(SLUG, prefix="mi", license="own", name="One"))
    save_doc(store, deck_doc(SLUG, prefix="mi", license="own", name="Two"))
    decks.set_switch(store, SLUG, auto=False)
    editor.restore(store, SLUG, 1, "user")
    assert decks.catalog(store)["decks"][SLUG]["switch"]["auto"] is False


# --- export never writes into the plugin's data or its own folder ------------

def test_export_refuses_the_plugin_data_dir(tmp_path):
    """Export with overwrite replaced another deck's file and a kept version, with no version written."""
    store = make_store(tmp_path)
    editor = sub("editor")
    other = write_user_deck(store, deck_doc("other", prefix="ot", license="own", name="Other"))
    save_doc(store, deck_doc(SLUG, prefix="mi", license="own", name="Kept"))
    kept = store.path(editor.VERSIONS, SLUG, "1.yaml")
    for target in (other, kept, other.parent, store.root / "fresh.yaml"):
        before = {p: p.read_text(encoding="utf-8") for p in (other, kept)}
        with pytest.raises(editor.EditError):
            editor.export(store, "design", str(target), overwrite=True)
        assert {p: p.read_text(encoding="utf-8") for p in (other, kept)} == before
    assert not (store.root / "fresh.yaml").exists()
    assert deck_name(store, "other") == "Other"


def test_export_refuses_a_link_into_the_data_dir(tmp_path):
    store = make_store(tmp_path)
    editor = sub("editor")
    other = write_user_deck(store, deck_doc("other", prefix="ot", license="own", name="Other"))
    link = tmp_path / "outside"
    link.symlink_to(other.parent, target_is_directory=True)
    with pytest.raises(editor.EditError):
        editor.export(store, "design", str(link / "other.yaml"), overwrite=True)
    with pytest.raises(editor.EditError):
        editor.export(store, "design", str(link))
    assert deck_name(store, "other") == "Other" and not (other.parent / "design.yaml").exists()


def test_export_refuses_the_plugin_folder(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    editor, decks = sub("editor"), sub("decks")
    plugin = tmp_path / "plugin"
    (plugin / "data" / "decks").mkdir(parents=True)
    shipped = plugin / "data" / "decks" / "coding.yaml"
    shipped.write_text(yaml_text(deck_doc("coding", prefix="co")), encoding="utf-8")
    monkeypatch.setattr(decks, "PLUGIN_ROOT", plugin)
    before = shipped.read_text(encoding="utf-8")
    with pytest.raises(editor.EditError):
        editor.export(store, "design", str(shipped), overwrite=True)
    with pytest.raises(editor.EditError):
        editor.export(store, "design", str(plugin))
    assert shipped.read_text(encoding="utf-8") == before and not (plugin / "design.yaml").exists()


def test_export_still_writes_outside(tmp_path):
    store = make_store(tmp_path)
    out = sub("editor").export(store, "design", str(tmp_path))
    assert pathlib.Path(out["written"]) == tmp_path / "design.yaml"


# --- a host-mode ctx that cannot answer the cron question ----------------

class NoCronCtx:
    """An older Hermes: the ctx has no current_cron_execution."""

    def __init__(self, surface):
        self.surface = surface

    def session_surface(self):
        return self.surface


class RaisingCronCtx(NoCronCtx):
    def current_cron_execution(self):
        raise RuntimeError("ctx call failed over the host wire")


class CronCtx(NoCronCtx):
    def current_cron_execution(self):
        return object()


HOST = {"HERMES_PLUGIN_HOST_PROCESS": "1"}


@pytest.mark.parametrize("ctx", [NoCronCtx("telegram"), RaisingCronCtx("desktop")], ids=["no_method", "raising"])
def test_host_mode_without_a_cron_answer_fails_closed_with_its_own_reason(ctx):
    bridge = sub("bridge")
    reason = bridge.unattended_reason(ctx, environ=HOST)
    assert reason is not None and reason != "a scheduled job"
    assert "could not ask Hermes whether this run is a scheduled job" in reason and "plugin host" in reason


def test_a_real_cron_run_still_says_scheduled_job():
    bridge = sub("bridge")
    assert bridge.unattended_reason(CronCtx("telegram"), environ=HOST) == "a scheduled job"
    assert bridge.unattended_reason(CronCtx("telegram"), environ={}) == "a scheduled job"


def test_in_process_without_a_cron_method_the_session_markers_decide(monkeypatch):
    bridge = sub("bridge")
    assert bridge.unattended_reason(NoCronCtx("telegram"), environ={}) is None
    monkeypatch.setenv("HERMES_CRON_SESSION", "1")
    assert bridge.unattended_reason(NoCronCtx("telegram"), environ={}) == "a scheduled job"


# --- the 422 message and "file name": short rule messages that count like problems_more ----------

def many_broken_cards(n=60):
    return [card(i, prefix="mi", human="<b>x</b>", agent="Run `ls`") for i in range(1, n + 1)]  # 2 problems each


def test_the_import_refusal_names_a_few_problems_and_counts_like_problems_more(tmp_path):
    store = make_store(tmp_path)
    editor = sub("editor")
    with pytest.raises(editor.EditError) as err:
        import_doc(store, deck_doc(SLUG, prefix="mi", cards=many_broken_cards()))
    msg, extra = str(err.value), err.value.extra
    assert len(extra["problems"]) == 50 and extra["problems_more"] == 70
    assert f"and {extra['problems_more']} more" in msg, msg
    assert "120" in msg and extra["problems"][0]["message"][:30] in msg, msg
    assert len(msg) <= 160, msg


def test_the_preview_refusal_counts_the_same_way(tmp_path):
    store = make_store(tmp_path)
    out = sub("editor").preview(store, SLUG, deck=deck_doc(SLUG, prefix="mi", cards=many_broken_cards()))
    assert out["ok"] is False and out["problems_more"] == 70
    assert "and 70 more" in out["message"] and len(out["message"]) <= 160, out["message"]


def test_a_short_refusal_names_every_problem_without_a_remainder(tmp_path):
    store = make_store(tmp_path)
    editor = sub("editor")
    with pytest.raises(editor.EditError) as err:
        import_doc(store, deck_doc(SLUG, prefix="mi", cards=[card(1, prefix="mi", human="<b>x</b>")]))
    msg = str(err.value)
    assert err.value.extra["problems"][0]["message"][:30] in msg and "more" not in msg, msg


def test_editor_messages_say_file_name_not_slug(tmp_path):
    """Fixed: the Desktop field is "File name"; the backend said "(slug)" and "deck name"."""
    store = make_store(tmp_path)
    editor = sub("editor")
    messages = []
    for call in (lambda: editor.import_text(store, yaml_text(deck_doc(SLUG, prefix="mi")), "user", slug=5),
                 lambda: import_doc(store, deck_doc("coding", prefix="co")),
                 lambda: editor.preview(store, "X", deck=deck_doc(SLUG, prefix="mi"))):
        with pytest.raises(editor.EditError) as err:
            call()
        messages.append(str(err.value))
    for msg in messages:
        assert "file name" in msg and "slug" not in msg and "deck name" not in msg, msg
