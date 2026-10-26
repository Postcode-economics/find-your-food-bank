"""Rule 21 (Dean, 26 Oct 2026, 08:29): a verified number on the venue's own page is shown.

That includes a named person's or personal number, with the label the page gives.
A verified own-page number dropped with no recorded reason fails this test.
Unverified or doubtful numbers stay held, with the reason recorded.
Dean's own details are never published.
"""
import json, os, re, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import phone_rule as P

def load(name):
    return json.load(open(os.path.join(ROOT, "overrides", name), encoding="utf-8"))

class Show(unittest.TestCase):
    def test_named_person_contact_is_shown_with_the_page_label(self):
        text = "The Revd. James McDonald – Team Rector 01923 903531\nChurchwardens Keith Gower 07754 997144"
        labs = P.labels_in_text(text)
        self.assertEqual(labs["01923903531"], "Team Rector")
        d = P.decide(dict(phone="01923 903531", own_page=True, verified=True, label=labs["01923903531"],
                          named_person=True, personal=True, reason="named person"))
        self.assertEqual(d["action"], "show")
        self.assertEqual(d["phone"], "01923 903531")
        self.assertEqual(d["label"], "Team Rector")
        self.assertEqual(d["reason"], "")

    def test_pastor_label_as_the_page_writes_it(self):
        labs = P.labels_in_text("please call Pastor Vaugh Thorpe on 07985 566 592")
        self.assertEqual(labs["07985566592"], "Pastor")
        d = P.decide(dict(phone="07985 566592", own_page=True, verified=True, label=labs["07985566592"], personal=True))
        self.assertEqual((d["action"], d["label"]), ("show", "Pastor"))

    def test_personal_only_hold_does_not_remove_a_checked_number(self):
        phones = {"kings-langley": "01923 903531"}
        sources = {"kings-langley": {"phone": "01923 903531", "source": "https://beneficeoflangelei.org.uk/allsaints/contact/", "note": "Confirmed live"}}
        holds = {"kings-langley": {"phone": "01923 903531", "reason": "named person", "verified": True}}
        self.assertEqual(P.phones_to_apply(phones, sources, holds)["kings-langley"], "01923 903531")

class Audit(unittest.TestCase):
    def test_verified_own_page_number_is_not_dropped_without_a_reason(self):
        bad = P.audit(P.override_candidates(ROOT))
        self.assertEqual([c["id"] for c in bad], [])
        ids = {c["id"] for c in P.override_candidates(ROOT)}
        self.assertIn("kings-langley", ids)
        self.assertNotIn("kings-langley/bennetts-end", ids)
        self.assertIn("leytonstone-seventh-day-adventist-church", ids)
        self.assertTrue(P.own_page_source({"note": "host church contact page"}))
        bare = dict(id="x", phone="01923 903531", own_page=True, verified=True, shown=False, reason="")
        self.assertEqual([c["id"] for c in P.audit([bare])], ["x"])
        self.assertEqual(len(P.audit([dict(bare, reason="personal")])), 1)
        self.assertEqual(P.audit([dict(bare, reason="displayed number conflicts with the tel link")]), [])

    def test_unverified_or_doubtful_is_held_with_a_reason(self):
        u = P.decide(dict(phone="0115 915 0285", verified=False, own_page=False))
        self.assertEqual(u["action"], "hold")
        self.assertTrue(u["reason"])
        d = P.decide(dict(phone="029 2166 0165", verified=True, own_page=True, doubtful=True,
                          reason="displayed number conflicts with the tel link"))
        self.assertEqual(d["action"], "hold")
        self.assertIn("conflict", d["reason"])
        phones = load("phones.json")
        for i, h in load("phone_holds.json").items():
            if str(i).startswith("_"): continue
            self.assertTrue((h.get("reason") or "").strip(), i)
            self.assertFalse(P.personal_only(h["reason"]), i)
            self.assertNotIn(i, phones, i)

class Dean(unittest.TestCase):
    def test_dean_details_are_never_published(self):
        block = ({"07700900123"}, {"dean.private@example.com"})
        d = P.decide(dict(phone="07700 900123", own_page=True, verified=True, label="Pastor", named_person=True), block)
        self.assertEqual(d["action"], "hold")
        self.assertEqual(d["reason"], P.DEAN_REASON)
        self.assertEqual(d["phone"], "")
        items = [{"id": "a", "phone": "07700 900123", "tel": "07700900123", "phone_label": "Pastor", "email": "dean.private@example.com"}]
        self.assertEqual(P.suppress(items, {}, block), 1)
        self.assertEqual(items[0]["phone"], "")
        self.assertEqual(items[0]["tel"], "")
        self.assertNotIn("phone_label", items[0])
        listed, emails = P.load_block()
        self.assertIn("phones", load("never_publish.json"))
        self.assertNotIn("hello@helpmap.uk", {e.lower() for e in load("never_publish.json").get("emails") or []})
        blobs = []
        for name in ("phones.json", "phone_sources.json", "warmspaces_contacts.json", "shelters_contacts.json"):
            blobs.append(json.dumps(load(name)))
        raw = "\n".join(blobs)
        for p in listed:
            self.assertNotIn(p, P.digits(raw))
        for e in emails:
            self.assertNotIn(e, raw.lower())

class Pipeline(unittest.TestCase):
    def test_no_named_person_or_personal_blocklist(self):
        bad = []
        for base in ("scripts", "overrides"):
            for dirpath, dirs, files in os.walk(os.path.join(ROOT, base)):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for f in files:
                    if not f.endswith((".py", ".json")) or f == "phone_rule.py": continue
                    rel = os.path.join(base, os.path.relpath(os.path.join(dirpath, f), os.path.join(ROOT, base)))
                    text = open(os.path.join(dirpath, f), encoding="utf-8").read()
                    if re.search(r"named_person|personal_number|hold_personal|skip_personal", text):
                        bad.append(rel)
        self.assertEqual(bad, [])

    def test_refresh_scripts_run_the_rule(self):
        for name in ("build.py", "shelter_contacts.py", "full_check.py"):
            self.assertIn("phone_rule", open(os.path.join(ROOT, "scripts", name), encoding="utf-8").read(), name)
        rules = load("auto_apply_rules.json")
        self.assertTrue(rules["phone_rule"]["show_verified_own_page"])
        self.assertTrue(rules["phone_rule"]["named_or_personal_is_not_a_reason_to_hold"])
        self.assertIn("verified own-page contact, including a named or personal number, with the page's label", rules["automatic"])
        self.assertIn("host church contact page counts as the venue's own page", rules["automatic"])
        self.assertTrue(rules["phone_rule"]["host_church_contact_counts_as_own_page"])

if __name__ == "__main__":
    unittest.main()
