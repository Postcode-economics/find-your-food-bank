"""Regression: eighteen warm-space cross_check auto-applies (29 Oct 2026 14:47 UTC) must stay held."""
import hashlib, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover as D

R1, R2 = "2026-10-29T05:39:35+00:00", "2026-10-29T14:47:47+00:00"
ON = {"times_auto_apply": True}
FILL = " lorem ipsum" * 40
SIG = lambda st: json.dumps(st, sort_keys=True) if st else None
LOG = json.load(open(os.path.join(os.path.dirname(__file__), "..", "reports", "times_auto_applied.json")))


def _rec(iid):
    return next(r for r in LOG if r.get("path") == "cross_check" and r.get("kind") == "ws" and r["id"] == iid
                and (r.get("second_run_at") or "").startswith("2026-10-29T14:47"))


def gate(item, new, texts, url, old=None, run_at=R2, blocked=None):
    old = old if old is not None else item.get("hours")
    item = dict(item, hours=old)
    seen = {("ws:" + item["id"]): {"sig": SIG((new or {}).get("structured")), "source_url": url, "run_at": R1}}
    return D.times_gate_reasons(item, "ws", "hours", new, texts, {"final_url": url}, seen, blocked or {}, True, run_at)


def pg(html, url="https://example.org/"):
    return {"http": 200, "final_url": url, "html": html, "etag": "e", "last_modified": "",
            "sha256": hashlib.sha256(html.encode()).hexdigest()}


def fetch(pages):
    def f(u):
        for k, v in pages.items():
            if u.rstrip("/") == k.rstrip("/"):
                return v
        return {"http": 404, "final_url": u, "html": ""}
    return f


class EighteenGateReasons(unittest.TestCase):
    def test_museum_general_week(self):
        r = _rec("ww-55473898")
        new = {"status": "TIMES_FOUND", "structured": r["new_structured"], "raw": "Mon-Sun 10am-5pm museum opening hours"}
        item = {"id": r["id"], "name": r["name"], "postcode": "E2 8EA", "website": r["source_url"]}
        why = gate(item, new, ["Museum of the Home E2 8EA visitor opening hours. " + new["raw"]], r["source_url"], r["old"])
        self.assertTrue(any("general venue" in w or "office/centre" in w for w in why), why)

    def test_bistro_page_not_warm_space(self):
        r = _rec("ww-55472899")
        new = {"status": "TIMES_FOUND", "structured": r["new_structured"], "raw": "Wed 12:00 - 14:00"}
        item = {"id": r["id"], "name": r["name"], "postcode": "PL27 6EX", "website": "https://wayfarerspark.co.uk/"}
        why = gate(item, new, [new["raw"]], r["source_url"], r["old"])
        self.assertTrue(any("session page" in w or "postcode not matched" in w for w in why), why)

    def test_council_warm_hub_directory(self):
        r = _rec("cmn-carway-hall")
        new = {"status": "TIMES_FOUND", "structured": r["new_structured"], "raw": "Tue Thu 10-2"}
        item = {"id": r["id"], "name": r["name"], "postcode": "SA17 4LW", "website": r["source_url"]}
        why = gate(item, new, [new["raw"]], r["source_url"], r["old"])
        self.assertTrue(any("postcode not matched" in w or "directory" in w or "session page" in w for w in why), why)

    def test_sports_hub_general_hours(self):
        r = _rec("ww-69189528")
        new = {"status": "TIMES_FOUND", "structured": r["new_structured"], "raw": "Mon-Fri 9-5 sports hub opening"}
        item = {"id": r["id"], "name": r["name"], "postcode": "EX39 3UT", "website": r["source_url"]}
        why = gate(item, new, ["Holford Sports Hub opening hours. " + new["raw"]], r["source_url"], r["old"])
        self.assertTrue(any("general venue" in w or "office/centre" in w or "session page" in w for w in why), why)

    def test_life_community_office_pattern(self):
        r = _rec("ww-57953101")
        new = {"status": "TIMES_FOUND", "structured": r["new_structured"], "raw": "Tue-Fri 9-5"}
        item = {"id": r["id"], "name": r["name"], "postcode": "MK45 2PP", "website": r["source_url"]}
        why = gate(item, new, [item["postcode"] + " Life Community Lunch Cafe " + new["raw"]], r["source_url"], r["old"])
        self.assertTrue(any("general venue" in w or "office/centre" in w or "fewer" in w for w in why), why)

    def test_undone_blocked(self):
        r = _rec("ww-55475042")
        new = {"status": "TIMES_FOUND", "structured": r["new_structured"], "raw": "Mon-Fri 9-1"}
        item = {"id": r["id"], "name": r["name"], "postcode": "PE21 6HP", "website": r["source_url"]}
        blk = {"ws:" + r["id"]: SIG(r["new_structured"])}
        why = gate(item, new, ["Centenary Methodist PE21 6HP " + new["raw"]], r["source_url"], r["old"], blocked=blk)
        self.assertIn("undone by Dean", "; ".join(why))


class EighteenCrossCheckEndToEnd(unittest.TestCase):
    def test_museum_two_runs_stays_held(self):
        r = _rec("ww-55473898")
        old = r["old"]
        url = r["source_url"]
        html = "<html><body><h1>Museum opening hours</h1><p>E2 8EA plan your visit Mon-Sun 10am-5pm.%s</body></html>" % FILL
        item = {"id": r["id"], "name": r["name"], "postcode": "E2 8EA", "website": url, "hours": dict(old)}
        root = tempfile.mkdtemp()
        f = fetch({url: pg(html, url)})
        D.cross_check_times([dict(item)], "ws", "hours", f, state_root=root, rules=ON, run_at=R1)
        log = D.cross_check_times([item], "ws", "hours", f, state_root=root, rules=ON, run_at=R2)
        self.assertIn(log[r["id"]]["status"], ("held_for_dean", "differs_review"))
        self.assertEqual(item["hours"], old)


if __name__ == "__main__":
    unittest.main()
