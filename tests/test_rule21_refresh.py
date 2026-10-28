"""Rule 21 on the scheduled sweep and refresh (Dean, 26 Oct 2026, 08:29).

A dry run / fixture. The verified named-person numbers stay, with the venue labels
the source pages give:

  kings-langley                         01923 903531   Team Rector
  leytonstone-seventh-day-adventist-church  07985 566592  Pastor

The daily sweep (scripts/sweep_daily.py, write=False), learning.py, and the
food-bank phone steps in build.py must not drop them. An older hold whose only
reason is that the number is a named person's does not drop them either.
"""
import json, os, re, shutil, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import phone_rule as P
import refresh_guard
import full_check
import learning
import learning_signals
import sweep_daily
import compact
import publish_gate
import shelter_contacts
from hours_fix import apply_phone

VENUES = {
    "kings-langley": ("01923 903531", "01923903531", "Team Rector"),
    "leytonstone-seventh-day-adventist-church": ("07985 566592", "07985566592", "Pastor"),
}
PHONE_FILES = (
    "overrides/phones.json",
    "overrides/phone_labels.json",
    "overrides/phone_sources.json",
    "overrides/phone_holds.json",
)
REMOVALS = (
    "overrides/phone_holds.json",
    "overrides/foodbank_exclude.json",
    "overrides/foodbank_closed.json",
    "overrides/discovery_hold.json",
    "overrides/guard_allow_remove.json",
)
WORKFLOWS = (
    ".github/workflows/refresh.yml",
    ".github/workflows/refresh-shelters.yml",
    ".github/workflows/refresh-warmspaces.yml",
    ".github/workflows/sweep-daily.yml",
)
DROP = re.compile(r"\b(named_person|personal_number|hold_personal|skip_personal)\b")


def load(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


def snap():
    out = {}
    for n in PHONE_FILES:
        with open(os.path.join(ROOT, n), "rb") as f:
            out[n] = f.read()
    return out


def apply_refresh_phones(items, phones, sources, holds, labels):
    """The phone steps build.py runs on every food-bank refresh."""
    chosen = P.phones_to_apply(phones, sources, holds)
    for i in items:
        if i["id"] in chosen:
            i["phone"] = chosen[i["id"]]
            i["phone_checked"] = True
        apply_phone(i)
        lab = labels.get(i["id"])
        if i.get("phone") and isinstance(lab, str) and lab.strip():
            i["phone_label"] = lab.strip()
    P.suppress(items, holds)
    return chosen


class Rule21Refresh(unittest.TestCase):
    def test_build_steps_keep_named_person_numbers_and_labels(self):
        phones, labels = load("overrides/phones.json"), load("overrides/phone_labels.json")
        sources, holds = load("overrides/phone_sources.json"), load("overrides/phone_holds.json")
        items = []
        for n, (i, (num, tel, lab)) in enumerate(VENUES.items()):
            self.assertEqual(phones[i], num)
            self.assertEqual(labels[i], lab)
            self.assertTrue(P.own_page_source(sources[i]), i)
            items.append({"id": i, "type": "foodbank", "name": i, "phone": "" if n else "00000 000000", "website": sources[i]["source"]})
        apply_refresh_phones(items, phones, sources, holds, labels)
        for i in items:
            num, tel, lab = VENUES[i["id"]]
            self.assertEqual(i["phone"], num)
            self.assertEqual(i["tel"], tel)
            self.assertEqual(i["phone_label"], lab)
            self.assertTrue(i["phone_checked"])
        packed = compact.encode({"fetched": "2026-10-26", "source": "fixture", "items": items})
        for num, _, lab in VENUES.values():
            self.assertIn(num, packed)
            self.assertIn(lab, packed)
        for i in items:
            self.assertEqual(publish_gate.problems("foodbanks", i), [])

    def test_older_named_person_hold_does_not_drop_them(self):
        phones, labels = load("overrides/phones.json"), load("overrides/phone_labels.json")
        sources = load("overrides/phone_sources.json")
        holds = load("overrides/phone_holds.json")
        reasons = ("named person", "personal", "personal number")
        for i, reason in zip(VENUES, reasons):
            holds[i] = {"phone": VENUES[i][0], "reason": reason, "verified": True, "source": sources[i]["source"]}
        items = [{"id": i, "type": "foodbank", "name": i, "phone": "", "website": sources[i]["source"]} for i in VENUES]
        chosen = apply_refresh_phones(items, phones, sources, holds, labels)
        for i in items:
            num, tel, lab = VENUES[i["id"]]
            self.assertEqual(chosen[i["id"]], num)
            self.assertEqual((i["phone"], i["tel"], i["phone_label"]), (num, tel, lab))
        # The shelter/warm-space refresh uses the same rule when an old drop_phone says "named person".
        pastor = "leytonstone-seventh-day-adventist-church"
        row = [{"id": pastor, "phone": "", "tel": ""}]
        shelter_contacts.apply(row, {pastor: {
            "drop_phone": True, "drop_reason": "named person", "own_page": True,
            "phone": VENUES[pastor][0], "phone_source": sources[pastor]["source"], "phone_label": "Pastor"}})
        self.assertEqual(row[0]["phone"], VENUES[pastor][0])
        self.assertEqual(row[0]["tel"], VENUES[pastor][1])
        self.assertEqual(row[0]["phone_label"], "Pastor")

    def test_not_on_a_removal_or_hold_list(self):
        flagged = []
        for rel in REMOVALS:
            p = os.path.join(ROOT, rel)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    text = f.read()
            else:
                text = ""
            for i in VENUES:
                if i in text:
                    flagged.append("%s lists %s" % (rel, i))
        self.assertEqual(flagged, [])

    def test_refresh_guard_puts_back_the_number_and_the_venue_label(self):
        old = [{"id": i, "name": i, "lat": 51.7, "lng": -0.4, "phone": num, "tel": tel, "phone_label": lab, "phone_source": "https://example.test/" + i}
               for i, (num, tel, lab) in VENUES.items()]
        blanked = [{"id": i, "name": i, "lat": 51.7, "lng": -0.4, "phone": "", "tel": "", "hours": ""} for i in VENUES]
        out, rep = refresh_guard.guard("foodbanks", old, blanked)
        self.assertEqual(rep["phones"], list(VENUES))
        self.assertNotIn("phone_labels", rep)
        by = {i["id"]: i for i in out}
        for i, (num, tel, lab) in VENUES.items():
            self.assertEqual((by[i]["phone"], by[i]["tel"], by[i]["phone_label"]), (num, tel, lab))
        # Same number kept, label stripped by a later step.
        kept = [{"id": i, "name": i, "lat": 51.7, "lng": -0.4, "phone": num, "tel": tel} for i, (num, tel, lab) in VENUES.items()]
        out, rep = refresh_guard.guard("foodbanks", old, kept)
        self.assertEqual(rep["phones"], [])
        self.assertEqual(rep["phone_labels"], list(VENUES))
        for i in out:
            self.assertEqual(i["phone_label"], VENUES[i["id"]][2])
        # A different number does not inherit the old venue label.
        other = [{"id": "kings-langley", "name": "kings-langley", "lat": 51.7, "lng": -0.4, "phone": "020 7946 0991", "tel": "02079460991"}]
        out, rep = refresh_guard.guard("foodbanks", old[:1], other)
        self.assertNotIn("phone_label", out[0])
        self.assertNotIn("phone_labels", rep)
        # A deliberate drop (phone_was) stays dropped.
        dropped = [{"id": "kings-langley", "name": "kings-langley", "lat": 51.7, "lng": -0.4, "phone": "", "tel": "", "phone_was": VENUES["kings-langley"][0]}]
        out, rep = refresh_guard.guard("foodbanks", old[:1], dropped)
        self.assertEqual(rep["phones"], [])
        self.assertEqual(out[0]["phone"], "")
        self.assertNotIn("phone_label", out[0])

    def test_full_check_does_not_replace_a_checked_named_person_number(self):
        # All Saints lists the Team Rector number among other people's numbers. The stored one is on the page.
        rector_page = ["01923903531", "07754997144", "07595217168", "07503950315"]
        self.assertFalse(full_check.own_site_misses_stored({full_check.norm_phone("01923 903531")}, rector_page))
        self.assertFalse(full_check.own_site_misses_stored({full_check.norm_phone("07985 566592")}, ["07985566592"]))
        flagged = {}
        def flag(key, cat, **kw):
            flagged[cat + "|" + key] = kw
        url = "https://beneficeoflangelei.org.uk/allsaints/contact/"
        item = {"id": "kings-langley", "name": "Kings Langley", "phone": "01923 903531", "tel": "01923903531",
                "phone_label": "Team Rector", "phone_checked": True}
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "overrides"))
            shutil.copy(os.path.join(ROOT, "overrides", "phone_baseline.json"), os.path.join(d, "overrides"))
            n = full_check.apply_phone_fixes(
                {url: [item]},
                {url: {"old": "01923903531", "new": "07754997144", "source": url, "label": "Churchwarden"}},
                flag, d)
            with open(os.path.join(d, "reports", "pending_dean.md"), encoding="utf-8") as f:
                self.assertIn("kings-langley | phone | via phone fix | source " + url, f.read())
        self.assertEqual(n, 0)
        self.assertEqual(item["phone"], "01923 903531")
        self.assertEqual(item["tel"], "01923903531")
        self.assertEqual(item["phone_label"], "Team Rector")
        self.assertTrue(any(k.startswith("phone change skipped") for k in flagged))

    def test_learning_orders_checks_and_does_not_edit_the_numbers(self):
        before = snap()
        state = learning.load(os.devnull)
        order, skipped, _ = learning.plan(state, list(VENUES), "2026-10-26")
        self.assertEqual(set(order), set(VENUES))
        self.assertEqual(skipped, [])
        for i in VENUES:
            learning.record(state, i, "2026-10-26", True, finds=0, method="own_site", kind="foodbank_site")
        ids, _ = learning_signals.corrections([{"id": i, "type": "foodbank", "givefood": "x"} for i in VENUES])
        for i in VENUES:
            self.assertIn(i, ids)
        self.assertEqual(snap(), before)
        with open(os.path.join(ROOT, "scripts", "learning.py"), encoding="utf-8") as f:
            self.assertNotIn("phones.json", f.read())

    def test_sweep_dry_run_leaves_the_overrides_unchanged(self):
        before = snap()
        os.environ["SWEEP_TODAY"] = "2026-10-26"
        try:
            report = sweep_daily.run(
                sources={"councils": [], "lists": [{
                    "url": "https://example.test/rule21-sweep", "name": "Rule 21 fixture",
                    "layer": "warmspaces", "auto_add": True}]},
                fetcher=lambda u: {"http": 200, "text": (
                    "Warm spaces winter 2026-27. Fixture Hall – 1 Test Road, Ely, CB7 4JF. "
                    "Opens: Thursday, 9.30am – 12pm"), "final_url": u, "last_modified": ""},
                geocoder=lambda pcs: {p: {"latitude": 52.4, "longitude": 0.26} for p in pcs},
                write=False)
        finally:
            os.environ.pop("SWEEP_TODAY", None)
        self.assertEqual(snap(), before)
        added = {a.get("id") for a in report.get("added") or []}
        self.assertTrue(set(VENUES).isdisjoint(added))
        e = {"name": "Fixture Hall", "address": "1 Test Road", "postcode": "CB7 4JF",
             "source_url": "https://example.test/rule21-sweep", "source": "Rule 21 fixture",
             "times_text": "Thursday, 9.30am – 12pm", "layer": "warmspaces", "hours": {"Thu": "09:30 - 12:00"},
             "tier": "verified", "page_date": "fixture"}
        _i, man, _ov = sweep_daily.to_records(e, {"latitude": 52.4, "longitude": 0.26}, "2026-10-26")
        self.assertEqual(man["phone"], "")
        self.assertNotIn(_i, VENUES)

    def test_scheduled_scripts_have_no_personal_drop_filter(self):
        names = {"scripts/learning.py"}
        for rel in WORKFLOWS:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
                names.update(re.findall(r"scripts/[A-Za-z0-9_]+\.py", f.read()))
        self.assertIn("scripts/sweep_daily.py", names)
        self.assertIn("scripts/learning_signals.py", names)
        self.assertIn("scripts/refresh_guard.py", names)
        self.assertIn("scripts/full_check.py", names)
        flagged = []
        for rel in sorted(names):
            if rel.endswith("/phone_rule.py"):
                continue
            p = os.path.join(ROOT, rel)
            if not os.path.exists(p):
                flagged.append(rel + " missing")
                continue
            with open(p, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if DROP.search(line):
                        flagged.append("%s:%d: %s" % (rel, n, line.strip()))
        self.assertEqual(flagged, [])


if __name__ == "__main__":
    unittest.main()
