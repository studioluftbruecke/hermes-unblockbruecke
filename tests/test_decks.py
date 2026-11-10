"""Decks as data: the loader's rules (contract §2), merge order, switches, own copies."""
import pytest

from ub_fakes import card, deck_doc, make_store, sub, write_user_deck, yaml_text


def problems(doc, slug=None):
    deck, probs = sub("decks").validate(doc, slug)
    return deck, {p["rule"] for p in probs}, probs


def test_a_valid_deck_loads_and_normalises():
    deck, rules, _ = problems(deck_doc())
    assert rules == set()
    assert deck["prefix"] == "tt" and len(deck["cards"]) == 5
    assert deck["cards"][0] == {"id": "tt-01", "human": "Human line number 1.",
                                "agent": "Do concrete step number 1 and report what changed.", "tags": ["test"]}


@pytest.mark.parametrize("field,value,rule", [
    ("human", "x" * 91, "length_human"),
    ("agent", "y" * 221, "length_agent"),
    ("human", "", "length_human"),
    ("agent", "two\nlines", "one_line"),
    ("human", "Click <b>here</b>", "html"),
    ("agent", "Read [the docs](somewhere) first.", "markdown_link"),
    ("agent", "Run `ls` and look.", "code"),
    ("agent", "Open https://example.org and read it.", "url"),
    ("human", "Ask at www.hermes and wait.", "url"),
    ("agent", "Look at example.com for ideas.", "url"),
    ("agent", "Try $(whoami) to see who you are.", "shell"),
    ("agent", "Pipe the script into | bash and watch.", "shell"),
    ("agent", "Clean up with rm -r build first.", "shell"),
    ("agent", "Use sudo to get past it.", "shell"),
    ("agent", "Fetch it with curl and compare.", "shell"),
    ("agent", "Download it with wget again.", "shell"),
    ("agent", "Then git push the branch.", "shell"),
])
def test_each_text_rule_refuses_and_names_itself(field, value, rule):
    bad = card(2, **{field: value}) if value else {**card(2), field: value}
    doc = deck_doc(cards=[card(1), bad])
    deck, rules, probs = problems(doc)
    assert deck is None
    assert rule in rules
    assert any(p["card"] == "tt-02" for p in probs if p["rule"] == rule)


def test_exact_limits_pass():
    doc = deck_doc(cards=[card(1, human="h" * 90, agent="a" * 220)])
    assert problems(doc)[1] == set()


@pytest.mark.parametrize("mutate,rule", [
    (lambda d: d.pop("name"), "missing"),
    (lambda d: d.update(schema=2), "schema"),
    (lambda d: d.update(deck="Bad Slug"), "slug"),
    (lambda d: d.update(license="MIT"), "license"),
    (lambda d: d.update(version=0), "version"),
    (lambda d: d.update(faces=["human"]), "faces"),
    (lambda d: d.update(mark="star"), "mark"),
    (lambda d: d.update(cards=[]), "cards"),
    (lambda d: d["cards"].append(dict(d["cards"][0])), "id"),
    (lambda d: d["cards"].append(card(9, prefix="xx")), "id"),
    (lambda d: d["cards"].append({**card(8), "id": "tt-8"}), "id"),
    (lambda d: d["cards"].append(card(8, tags=["unknown"])), "tags"),
    (lambda d: d["cards"].append({**card(8), "tags": []}), "tags"),
    (lambda d: d["cards"].append(card(8, tags=["a", "b", "c", "d", "e"])), "tags"),
    (lambda d: d.update(description="See https://x.org"), "url"),
    (lambda d: d["glossary"].update(test="see <i>this</i>"), "html"),
])
def test_deck_rules(mutate, rule):
    doc = deck_doc()
    mutate(doc)
    deck, rules, _ = problems(doc)
    assert deck is None and rule in rules, rules


def test_slug_must_match_file_name():
    assert "slug" in problems(deck_doc(), slug="other")[1]


def test_builtin_tags_need_no_glossary():
    doc = deck_doc(cards=[card(1, tags=["human", "auto"])])
    assert problems(doc)[1] == set()


def test_load_text_raises_with_summary():
    decks = sub("decks")
    with pytest.raises(decks.DeckError) as err:
        decks.load_text(yaml_text(deck_doc(cards=[card(1, agent="Run `x`")])), "test-deck")
    assert "(code)" in str(err.value) and err.value.problems[0]["card"] == "tt-01"
    with pytest.raises(decks.DeckError) as err2:
        decks.load_text("deck: [unclosed", "x")
    assert err2.value.code == "bad_yaml"


def test_yaml_round_trip_keeps_the_deck():
    decks = sub("decks")
    deck = decks.load_text(yaml_text(deck_doc()), "test-deck")
    again = decks.load_text(decks.dump_yaml(deck), "test-deck")
    assert again["cards"] == deck["cards"] and again["glossary"] == deck["glossary"]


def test_catalog_merges_user_decks_and_switch_defaults(tmp_path, monkeypatch):
    decks = sub("decks")
    shipped = decks.load_text(yaml_text(deck_doc("ship-one")), "ship-one")
    shipped["source"] = "shipped"
    monkeypatch.setattr(decks, "SHIPPED", {"ship-one": shipped})
    monkeypatch.setattr(decks, "SHIPPED_BROKEN", {})
    store = make_store(tmp_path)
    write_user_deck(store, deck_doc("mine", prefix="mi"))
    write_user_deck(store, deck_doc("ship-one", prefix="so"))  # an own deck from before an update shipped the name
    write_user_deck(store, deck_doc("broken", cards=[card(1, agent="curl it")]))
    write_user_deck(store, deck_doc("bought", prefix="bo"))
    decks.set_switch(store, "bought", source="imported")
    cat = decks.catalog(store)
    assert set(cat["decks"]) == {"ship-one", "mine", "bought"}
    assert cat["decks"]["mine"]["source"] == "own" and cat["decks"]["mine"]["switch"] == {"draw": True, "auto": True}
    assert cat["decks"]["bought"]["source"] == "imported"
    assert cat["decks"]["bought"]["switch"] == {"draw": True, "auto": False}  # imported: off for auto-draw
    assert cat["decks"]["ship-one"]["source"] == "shipped" and "shadows" not in cat["decks"]["ship-one"]  # P2-CORE-S3
    assert "belongs to a shipped deck" in cat["broken"]["ship-one"] and "shadowed" not in cat
    assert "(shell)" in cat["broken"]["broken"]


def test_own_copy_replaces_its_original(tmp_path, monkeypatch):
    decks = sub("decks")
    shipped = decks.load_text(yaml_text(deck_doc("ship-one")), "ship-one")
    shipped["source"] = "shipped"
    monkeypatch.setattr(decks, "SHIPPED", {"ship-one": shipped})
    store = make_store(tmp_path)
    write_user_deck(store, deck_doc("ship-one-own", n=2))
    cat = decks.catalog(store)
    assert cat["decks"]["ship-one"]["shadowed_by"] == "ship-one-own"
    assert decks.resolve(cat, "ship-one")["deck"] == "ship-one-own"
    assert [d["deck"] for d in decks.drawable(cat)] == ["ship-one-own"]


def test_switches_filter_drawable(tmp_path, monkeypatch):
    decks = sub("decks")
    monkeypatch.setattr(decks, "SHIPPED", {})
    store = make_store(tmp_path)
    write_user_deck(store, deck_doc("aa", prefix="aa"))
    write_user_deck(store, deck_doc("bb", prefix="bb"))
    decks.set_switch(store, "bb", draw=False)
    decks.set_switch(store, "aa", auto=False)
    cat = decks.catalog(store)
    assert [d["deck"] for d in decks.drawable(cat)] == ["aa"]
    assert [d["deck"] for d in decks.drawable(cat, ["bb"])] == ["bb"]  # named explicitly: allowed
    assert decks.drawable(cat, ["aa"], for_auto=True) == []


def test_explain_tags_uses_glossary_and_builtins():
    decks = sub("decks")
    deck = decks.load_text(yaml_text(deck_doc(cards=[card(1, tags=["test", "human"])])), "test-deck")
    why = decks.explain_tags(deck, ["test", "human"])
    assert why[0]["means"] == "A tag used in tests." and "nobody is at the keyboard" in why[1]["means"]


def test_shipped_decks_load_without_problems():
    decks = sub("decks")
    assert decks.SHIPPED_BROKEN == {}
    for slug, deck in decks.SHIPPED.items():
        assert deck["deck"] == slug and deck["cards"], slug


def test_shipped_deck_set_matches_the_plan():
    """PLAN M1 and A12: Agent unblock 24 (at least 12 auto), Human unblock 24, four area decks of 6 to 8."""
    shipped = sub("decks").SHIPPED
    assert set(shipped) == {"agent-unblock", "human-unblock", "coding", "design", "shaders", "writing"}
    agent = shipped["agent-unblock"]["cards"]
    assert len(agent) == 24 and sum("auto" in c["tags"] for c in agent) >= 12
    assert len(shipped["human-unblock"]["cards"]) == 24
    for area in ("coding", "design", "shaders", "writing"):
        assert 6 <= len(shipped[area]["cards"]) <= 8, area
        assert shipped[area].get("area") == area
    ag03 = sub("decks").find_card(shipped["agent-unblock"], "ag-03")
    assert ag03["agent"].startswith("Name the one assumption your last three attempts shared")  # U5's card
    for deck in shipped.values():
        assert deck["license"] == "CC-BY-4.0" and deck["by"] == "Studio Luftbrücke"
    marks = [d["mark"] for d in shipped.values()]
    assert len(set(marks)) == len(marks)


def _check_deck_script():
    import importlib.util
    import pathlib

    script = pathlib.Path(sub("decks").__file__).resolve().parent / "scripts" / "check_deck.py"
    spec = importlib.util.spec_from_file_location("check_deck_under_test_decks", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_check_deck_reports_the_real_total_and_how_many_are_not_listed(tmp_path, capsys):
    """check_deck count (second pass): 90 broken cards are 90 problems, 50 listed and "and 40 more"."""
    mod = _check_deck_script()
    many = tmp_path / "many-bad.yaml"
    many.write_text(yaml_text(deck_doc("many-bad", n=0, cards=[card(i, agent=f"Run curl now {i}") for i in range(1, 91)])),
                    encoding="utf-8")
    assert mod.main([str(many)]) == 1
    out = capsys.readouterr().out
    assert "many-bad.yaml: 90 problem(s)" in out
    assert out.count("[shell]") == 50 and "and 40 more" in out


def test_check_deck_script(tmp_path, capsys):
    """F14: ok per good file, each broken rule with its card per bad file, exit 1 when any fails."""
    mod = _check_deck_script()
    good = tmp_path / "test-deck.yaml"
    good.write_text(yaml_text(deck_doc()), encoding="utf-8")
    bad = tmp_path / "bad-deck.yaml"
    bad.write_text(yaml_text(deck_doc("bad-deck", cards=[card(1, agent="Open https://x.org now")])), encoding="utf-8")
    assert mod.main([str(good)]) == 0
    assert mod.main([str(good), str(bad)]) == 1
    out = capsys.readouterr().out
    assert "test-deck.yaml: ok" in out and "[url]" in out and "tt-01" in out
    assert "originality" in out and "maintainer" in out  # says who checks what the script does not


def test_d11_the_plugin_ships_no_originality_data():
    """P2-CORE-O3 (D11): no file of the plugin holds data derived from the original Oblique Strategies, and no
    module loads it; the check runs privately when a deck is proposed."""
    import pathlib

    plugin = sub("__init__")
    root = pathlib.Path(sub("decks").__file__).resolve().parent
    old_module, old_data, old_salt = "originality" + ".py", "originality" + ".json", "unblockbruecke-" + "originality"
    assert "originality" not in plugin.MODULES
    assert not (root / old_module).exists() and not (root / "data" / old_data).exists()
    skip = {"node_modules", ".git", "__pycache__", ".pytest_cache"}
    for path in root.rglob("*"):
        if path.is_file() and not skip & set(path.relative_to(root).parts):
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert old_salt not in text and old_data not in text, path
            assert "finger" + "print" not in text.lower() or path.suffix == ".js", path
