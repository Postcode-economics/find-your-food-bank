"""duplicate_of in overrides/shelters_contacts.json must reach the built shelter data, and never drop a shelter."""
import json, os, sys
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import shelter_contacts

def test_apply_copies_duplicate_of_and_keeps_both():
    items = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
    data = {"a": {"duplicate_of": "b", "note": "same place"}, "b": {"duplicate_of": "a"}}
    shelter_contacts.apply(items, data)
    assert len(items) == 2
    assert items[0]["duplicate_of"] == "b" and items[0]["duplicate_note"] == "same place"
    assert items[1]["duplicate_of"] == "a"

def test_nightsafe_duplicate_in_published_shelters():
    t = open(os.path.join(ROOT, "shelters.js")).read()
    d = {x["id"]: x for x in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
    assert d["hl-nightsafe-blackburn"]["duplicate_of"] == "man-nightsafe-blackburn"
    assert d["man-nightsafe-blackburn"]["duplicate_of"] == "hl-nightsafe-blackburn"
