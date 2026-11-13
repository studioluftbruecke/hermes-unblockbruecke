"""What the README promises about the agent's deck edits matches what the tool does."""
from ub_fakes import FakeCtx, ROOT, load_plugin

README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_agent_can_preview_save_and_switch_a_deck_on_in_one_turn_and_the_readme_says_so(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    change = {"add": [{"human": "What is the smallest next step?",
                       "agent": "Name the smallest step that would show progress, then take it.", "tags": ["auto"]}]}
    preview = ctx.call("unblockbruecke_decks", action="preview", deck="coding", changes=change)
    assert preview["ok"], preview
    saved = ctx.call("unblockbruecke_decks", action="save", deck="coding", changes=change, confirm=preview["confirm"])
    assert saved["ok"], saved
    switched = ctx.call("unblockbruecke_decks", action="switch", deck=saved["deck"], auto=True)
    assert switched["ok"], switched
    assert "you see a preview and confirm it first" not in README
    assert "no approval card" in README and "Undo" in README


def test_the_agent_import_reads_any_path_it_is_given_and_the_readme_says_so(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    secret = tmp_path / "elsewhere" / "settings.yaml"
    secret.parent.mkdir()
    secret.write_text("api_key: value-that-must-not-echo\n", encoding="utf-8")
    out = ctx.call("unblockbruecke_decks", action="import", path=str(secret))
    assert out["ok"] is False and "value-that-must-not-echo" not in str(out)
    assert "import" in README and "reads a deck file from any path" in README
