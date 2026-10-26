"""Emergency shelter preview (plan 25 Oct 2026, Dean's final colours the same evening).

Cases follow the paper plan. The signed-off colours replace the earlier 3px outline and black-on-red
recommendation: every red is #FF3B30, text on red is white, weight 900, badge 16px, outline 2px with a 6px left edge.
"""
import datetime, json, os, tempfile, unittest
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import weather as w

ROOT = os.path.join(os.path.dirname(__file__), "..")
NOW = datetime.datetime(2026, 10, 25, 18, 0, tzinfo=datetime.timezone.utc)
ADDED = datetime.datetime(2026, 10, 25, 12, 0, tzinfo=datetime.timezone.utc)

def amber(area="West Sussex"):
    return {"source": "Met Office", "title": "Amber warning of wind affecting " + area, "level": "amber",
            "areas": [area], "link": "https://www.metoffice.gov.uk/weather/warnings-and-advice/uk-warnings"}

def centre(**kw):
    base = {"official_council": True, "name": "Littlehampton Leisure Centre", "council": "Arun District Council",
            "url": "https://www.arun.gov.uk/emergency-planning", "address": "1 Sea Road, Littlehampton",
            "added": ADDED, "open_until": NOW + datetime.timedelta(hours=12)}
    base.update(kw)
    return base

def rd(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()

class Plan(unittest.TestCase):
    def test_01_amber_banner_and_layer(self):
        out = w.compose([amber()], [], "West Sussex", NOW)
        self.assertTrue(out["banner"]["show"])
        self.assertTrue(out["layer_on"])
        self.assertIn("Severe weather warning for West Sussex", out["banner"]["text"])
        self.assertIn("999", out["banner"]["text"])
        self.assertIn(w.FLOODLINE, out["banner"]["text"])
        self.assertFalse(out["banner"]["ping"])

    def test_02_yellow_no_banner_layer_off(self):
        y = amber(); y["level"] = "yellow"; y["title"] = "Yellow warning of wind"
        out = w.compose([y], [], "West Sussex", NOW)
        self.assertFalse(out["banner"]["show"])
        self.assertFalse(out["layer_on"])
        self.assertIsNone(out["banner"]["text"])

    def test_03_severe_flood_evacuation_wording_and_ping(self):
        severe = {"source": "Environment Agency", "title": "Severe Flood Warning: Test", "level": "red",
                  "areas": ["Hampshire"], "link": "https://check-for-flooding.service.gov.uk/"}
        b = w.banner_for([severe], "Hampshire", now=NOW, updated="20:10")
        self.assertIn("Evacuation alert in Hampshire", b["text"])
        self.assertIn("999", b["text"])
        self.assertIn(w.FLOODLINE, b["text"])
        self.assertTrue(b["ping"])
        self.assertEqual(b["pings"][0]["to"], "Dean")
        self.assertFalse(b["pings"][0]["sent"])

    def test_04_cancelled_warning_banner_goes_centre_stays(self):
        src = centre()
        self.assertEqual(w.RUN_EVERY_MINUTES, 10)
        live = w.compose([amber()], [src], "West Sussex", NOW)
        self.assertTrue(live["banner"]["show"])
        gone = w.compose([], [src], "West Sussex", NOW)
        self.assertFalse(gone["banner"]["show"])
        self.assertFalse(gone["layer_on"])
        self.assertEqual([c["name"] for c in gone["cards"]], ["Littlehampton Leisure Centre"])

    def test_05_council_says_closed(self):
        rec = w.parse_announcement("The rest centre at Littlehampton Leisure Centre is now closed.", "Arun District Council", "https://www.arun.gov.uk/emergency-planning", NOW)
        self.assertTrue(rec["closed"])
        src = centre(closed=True)
        self.assertEqual(w.compose([amber()], [src], "West Sussex", NOW)["cards"], [])

    def test_06_cached_page_hides_after_open_until(self):
        until = NOW + datetime.timedelta(hours=2)
        src = centre(open_until=until)
        card = w.card_from_source(src, NOW)["card"]
        self.assertFalse(w.browser_hide(card["open_until"], NOW))
        self.assertTrue(w.browser_hide(card["open_until"], until))
        self.assertEqual(w.compose([amber()], [src], "West Sussex", until)["cards"], [])
        js = rd("emergency.js")
        self.assertIn("data-open-until", js)
        self.assertIn("now>=t", js.replace(" ", ""))

    def test_07_default_open_until(self):
        end = ADDED + datetime.timedelta(hours=2)
        self.assertEqual(w.resolve_open_until(None, ADDED, end), end + datetime.timedelta(hours=6))
        far = ADDED + datetime.timedelta(hours=30)
        self.assertEqual(w.resolve_open_until(None, ADDED, far), ADDED + datetime.timedelta(hours=24))
        stated = ADDED + datetime.timedelta(hours=3)
        self.assertEqual(w.resolve_open_until(stated, ADDED, end), stated)
        self.assertEqual(w.fmt_until("2026-10-26T08:00:00+00:00"), "08:00 Mon 26 Oct")
        card = w.card_from_source(centre(open_until=None, added=ADDED), ADDED, warning_end=end)["card"]
        self.assertEqual(w._as_dt(card["open_until"]), end + datetime.timedelta(hours=6))

    def test_08_stale_35_minutes(self):
        b = w.banner_for([amber()], "West Sussex", now=NOW, fetched_at=NOW - datetime.timedelta(minutes=35), updated="20:10")
        self.assertTrue(b["show"])
        self.assertIn("may be out of date", b["stale_note"].lower())
        self.assertIn("https://www.metoffice.gov.uk/", b["stale_note"])

    def test_09_stale_two_hours_hides_banner(self):
        b = w.banner_for([amber()], "West Sussex", now=NOW, fetched_at=NOW - datetime.timedelta(hours=2))
        self.assertFalse(b["show"])
        self.assertIsNone(b["text"])
        self.assertFalse(b["layer_on"])
        self.assertTrue(b["links"])
        self.assertEqual(b["links"][0]["name"], "Met Office")

    def test_10_watchdog_61_minutes(self):
        self.assertTrue(w.watchdog_due(NOW - datetime.timedelta(minutes=61), NOW))
        self.assertFalse(w.watchdog_due(NOW - datetime.timedelta(minutes=60), NOW))
        self.assertEqual(w.WATCHDOG_MINUTES, 60)

    def test_11_council_centre_live_at_once(self):
        d = w.card_from_source(centre(), NOW)
        self.assertEqual(d["publish"], "live")
        self.assertEqual(d["tell_dean"], "afterwards")
        self.assertTrue(d["card"]["live"])

    def test_12_non_council_held(self):
        d = w.card_from_source({"name": "Church hall", "official_council": False, "added": ADDED}, NOW)
        self.assertEqual(d["publish"], "hold")
        self.assertIn("OK", d["tell_dean"])
        self.assertIsNone(d["card"])
        out = w.compose([amber()], [{"name": "Church hall", "official_council": False}], "West Sussex", NOW)
        self.assertEqual(out["cards"], [])
        self.assertEqual(out["held"][0]["name"], "Church hall")

    def test_13_omit_pets_access_beds_when_not_stated(self):
        text = "Arun District Council has opened a rest centre at Littlehampton Leisure Centre."
        rec = w.parse_announcement(text, "Arun District Council", "https://www.arun.gov.uk/emergency-planning", NOW)
        for key in ("pets", "access", "beds", "opened_for"):
            self.assertNotIn(key, rec)
        card = w.card_from_source(centre(), NOW)["card"]
        for key in ("pets", "access", "beds", "opened_for"):
            self.assertNotIn(key, card)
        stated = w.card_from_source(centre(pets="allowed", access="step-free", beds=40), NOW)["card"]
        self.assertEqual((stated["pets"], stated["access"], stated["beds"]), ("allowed", "step-free", 40))

    def test_14_swep_badge_only_when_active(self):
        card = w.card_from_source(centre(swep_active=True), NOW)["card"]
        self.assertEqual(card["swep_badge"], w.SWEP_BADGE)
        self.assertEqual(card["badge"], "Emergency shelter")
        self.assertNotIn("swep_badge", w.card_from_source(centre(swep_active=False), NOW)["card"])

    def test_15_swep_hidden_when_page_unread_over_24h(self):
        self.assertFalse(w.swep_show(True, datetime.timedelta(hours=25)))
        self.assertTrue(w.swep_show(True, datetime.timedelta(hours=23)))
        card = w.card_from_source(centre(swep_active=True, swep_unreadable_for=datetime.timedelta(hours=25)), NOW)["card"]
        self.assertNotIn("swep_badge", card)

    def test_16_search_emergency_flood_evacuation(self):
        for q in ("emergency", "flood", "evacuation"):
            self.assertTrue(w.emergency_search(q), q)
        self.assertFalse(w.emergency_search("food bank"))
        self.assertFalse(w.emergency_search(""))

    def test_17_map_key_only_when_marker_live(self):
        self.assertIsNone(w.map_key(False))
        key = w.map_key(True)
        self.assertIn("rest centre opened by the council", key["entry"])
        self.assertTrue(key["needs_dean_ok"])
        out = w.compose([amber()], [], "West Sussex", NOW)
        self.assertIsNone(out["key"])
        with_card = w.compose([amber()], [centre()], "West Sussex", NOW)
        self.assertIsNotNone(with_card["key"])

    def test_18_northern_ireland_number(self):
        b = w.banner_for([amber("Belfast")], "Belfast", nation="Northern Ireland", postcode="BT1 1AA", now=NOW, updated="20:10")
        self.assertIn(w.NI_FLOOD, b["text"])
        self.assertIn("Flooding NI", b["text"])
        self.assertNotIn(w.FLOODLINE, b["text"])
        text = w.low_data_list("BT1 1AA", "20:10", [], nation="Northern Ireland")
        self.assertIn(w.NI_FLOOD, text)
        self.assertNotIn(w.FLOODLINE, text)

    def test_19_emergency_alert_recheck_and_ping(self):
        alert = {"source": "UK Emergency Alerts", "level": "red", "areas": ["Cornwall"], "title": "Emergency Alert: Cornwall",
                 "link": "https://www.gov.uk/alerts"}
        b = w.banner_for([alert], "Cornwall", now=NOW, updated="20:10")
        self.assertTrue(b["show"])
        self.assertTrue(b["ping"])
        self.assertTrue(b["swep_recheck"])
        self.assertIn("999", b["text"])
        self.assertIn("Emergency in Cornwall", b["text"])

    def test_20_swep_daily_from_1_nov(self):
        self.assertFalse(w.swep_daily_due("2026-10-31"))
        self.assertTrue(w.swep_daily_due("2026-11-01"))
        self.assertTrue(w.swep_daily_due("2026-10-25", alert=True))

    def test_21_low_data_list(self):
        text = w.low_data_list("BN17 5AA", "20:10", [{"name": "Hall", "address": "1 High St", "open_until_label": "08:00 Mon 26 Oct", "source_url": "https://www.arun.gov.uk/emergency-planning"}])
        lines = text.splitlines()
        self.assertEqual(lines[0], "EMERGENCY SHELTERS near BN17 5AA, checked 20:10")
        self.assertIn("999", lines[1])
        self.assertIn(w.FLOODLINE, lines[1])
        self.assertIn("1. Hall, 1 High St. Open until 08:00 Mon 26 Oct. Source: https://www.arun.gov.uk/emergency-planning", text)
        self.assertNotIn("<", text)
        page = rd("emergency.txt")
        self.assertIn("999", page)
        self.assertIn(w.FLOODLINE, page)
        self.assertNotIn("<", page)
        self.assertNotIn(w.FORBIDDEN, page)

    def test_22_banner_does_not_cover_search(self):
        css, js = rd("emergency.css"), rd("emergency.js")
        self.assertIn("position:static", css)
        self.assertNotIn("position:fixed", css)
        self.assertIn("insertAdjacentElement('afterend',banner)", js.replace(" ", ""))
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            raise unittest.SkipTest("playwright not available")
        if not os.path.exists("/usr/bin/google-chrome"):
            raise unittest.SkipTest("no chrome")
        import functools, http.server, threading
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT); h.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h); threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = "http://127.0.0.1:%d/?preview=emergency&sample=1&fresh=1&nocount=1" % srv.server_address[1]
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
                for width in (360, 390, 1366):
                    for scheme in ("light", "dark"):
                        pg = b.new_page(viewport={"width": width, "height": 844}, color_scheme=scheme, device_scale_factor=1)
                        pg.goto(url, wait_until="load")
                        pg.wait_for_selector("#em-banner")
                        if scheme == "light": pg.evaluate("document.documentElement.classList.add('light')")
                        box = pg.evaluate("""()=>{const q=document.getElementById('q').getBoundingClientRect(),a=document.getElementById('em-banner').getBoundingClientRect();
                          return {overlap:!(a.bottom<=q.top||a.top>=q.bottom||a.right<=q.left||a.left>=q.right),
                            bannerW:a.width,view:innerWidth,readable:a.width>0&&a.height>0&&a.left>=-1&&a.right<=innerWidth+1}}""")
                        self.assertFalse(box["overlap"], (width, scheme))
                        self.assertTrue(box["readable"], (width, scheme))
                        pg.close()
                b.close()
        finally:
            srv.shutdown()

    def test_23_missing_nrw_key_skips_nrw_only(self):
        called = []
        def getter(url, headers=None):
            called.append(url)
            if url == w.MET: return b'<rss><channel><item><title>Amber warning of wind affecting Wales</title><description>Amber warning of wind affecting Wales: Gwynedd valid from 1000 Sat</description><link>x</link></item></channel></rss>'
            if url == w.EA: return b'{"items":[]}'
            if url == w.SEPA: return b'<rss></rss>'
            if url == w.GOVUK: return b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
            raise AssertionError(url)
        ws, errs, notes = w.fetch_all(getter, "")
        self.assertTrue(any(i["areas"] == ["Gwynedd"] for i in ws))
        self.assertIn("Natural Resources Wales: no API key", errs)
        self.assertTrue(any("NRW skipped" in n for n in notes))
        self.assertNotIn(w.NRW, called)
        seen = []
        def getter_key(url, headers=None):
            if url == w.NRW:
                seen.append(headers.get("Ocp-Apim-Subscription-Key")); return b'{"features":[]}'
            return getter(url)
        _ws, errs2, notes2 = w.fetch_all(getter_key, "secret-key")
        self.assertEqual(seen, ["secret-key"])
        self.assertNotIn("secret-key", " ".join(errs2))
        self.assertEqual(notes2, [])

    def test_24_flood_email_is_a_trigger(self):
        feed = [{"source": "Environment Agency", "title": "Flood Warning: Littlehampton", "areas": ["Littlehampton"], "level": "flood warning"}]
        msg = {"from": "hello@helpmap.uk", "subject": "Flood warning", "body": "Flood warning for Littlehampton. Environment Agency."}
        hit = w.inbox_trigger(msg, feed)
        self.assertTrue(hit["trigger"])
        self.assertEqual(hit["matched"]["area"], "Littlehampton")
        self.assertEqual(hit["matched"]["source"], "Environment Agency")
        self.assertIsNone(w.inbox_trigger({"subject": "Hello", "body": "no warning here"}, feed))

    def test_25_rule_and_research_backup_same_day(self):
        doc = rd("docs/emergency_shelter_preview.md")
        self.assertIn("2026-10-25", doc)
        self.assertIn("2026-10-25", rd("tests/test_emergency_preview.py"))
        self.assertIn("open-until", doc)
        self.assertIn("?preview=emergency", doc)

    def test_26_drill_is_test_copy_only(self):
        ok = w.monthly_drill("test")
        self.assertTrue(ok["ok"])
        self.assertFalse(ok["ran_on_live"])
        self.assertTrue(ok["live_unchanged"])
        refused = w.monthly_drill("live")
        self.assertFalse(refused["ok"])
        self.assertFalse(refused["ran_on_live"])
        self.assertTrue(refused["live_unchanged"])

    def test_27_gas_alert_uses_the_stated_cause(self):
        alert = {"source": "UK Emergency Alerts", "level": "red", "areas": ["Example area"], "cause": "gas leak",
                 "title": "Emergency Alert: Example area", "link": "https://www.gov.uk/alerts"}
        b = w.banner_for([alert], "Example area", now=NOW, updated="20:10")
        self.assertIn("Emergency in Example area: gas leak", b["text"])
        self.assertNotIn("Severe weather warning", b["text"])
        self.assertNotIn("Evacuation alert", b["text"])
        self.assertTrue(b["swep_recheck"])
        self.assertIn("999", b["text"])

    def test_28_fire_rest_centre_badge_and_cause(self):
        text = "Arun District Council has opened a rest centre at Littlehampton Leisure Centre. Opened for: fire."
        rec = w.parse_announcement(text, "Arun District Council", "https://www.arun.gov.uk/emergency-planning", NOW)
        self.assertEqual(rec["name"], "Littlehampton Leisure Centre")
        self.assertEqual(rec["opened_for"], "fire")
        d = w.card_from_source(rec, NOW)
        self.assertEqual(d["publish"], "live")
        self.assertEqual(d["tell_dean"], "afterwards")
        self.assertEqual(d["card"]["badge"], "Emergency shelter")
        self.assertEqual(d["card"]["opened_for"], "fire")
        self.assertEqual(d["card"]["emergency_number"], "999")
        self.assertEqual(d["card"]["flood_number"], w.FLOODLINE)

    def test_29_no_cause_line_when_the_source_gives_none(self):
        card = w.card_from_source(centre(), NOW)["card"]
        self.assertEqual(card["badge"], "Emergency shelter")
        self.assertNotIn("opened_for", card)
        self.assertNotIn("cause", card)

    def test_30_power_cut_is_trigger_only(self):
        effect = w.event_effect("power", official_alert=True)
        self.assertTrue(effect["trigger"])
        self.assertTrue(effect["council_recheck"])
        self.assertFalse(effect["banner"])
        self.assertIsNone(effect["card"])
        self.assertFalse(effect["creates_card_from_event"])
        self.assertFalse(w.banner_for([w.power_trigger("National Grid", "West Sussex")], "West Sussex", now=NOW)["show"])
        self.assertFalse(w.banner_for([w.power_trigger("SSEN", "Highland")], "Highland", now=NOW)["show"])

    def test_31_earthquake_needs_an_official_alert(self):
        effect = w.event_effect("bgs")
        self.assertTrue(effect["trigger"])
        self.assertTrue(effect["council_recheck"])
        self.assertFalse(effect["banner"])
        self.assertIsNone(effect["card"])
        xml = b'<rss><channel><item><title>M 2.1 NORTH SEA</title><link>https://www.earthquakes.bgs.ac.uk/</link></item></channel></rss>'
        triggers = w.bgs_triggers(xml)
        self.assertEqual(triggers[0]["source_kind"], "bgs")
        self.assertFalse(w.banner_for(triggers, "Arun", now=NOW)["show"])

    def test_32_search_fire_rest_centre_evacuate(self):
        for q in ("fire", "rest centre", "evacuate", "emergency shelter", "storm", "gas", "power cut", "earthquake"):
            self.assertTrue(w.emergency_search(q), q)
        js = rd("emergency.js")
        for t in w.SEARCH_TERMS:
            self.assertIn(t, js)

    def test_33_evacuation_without_a_centre(self):
        pol = {"source": "Sussex Police", "source_kind": "police", "level": "red", "evacuation": True, "areas": ["Arun"],
               "title": "Evacuation in Arun", "link": "https://www.westsussex.gov.uk/fire-emergencies-and-crime/"}
        out = w.compose([pol], [], "Arun", NOW)
        self.assertTrue(out["banner"]["show"])
        self.assertIn("Evacuation alert in Arun", out["banner"]["text"])
        self.assertIn("999", out["banner"]["text"])
        self.assertEqual(out["cards"], [])
        self.assertIsNone(out["key"])

    def test_34_rejected_wording_never_shown(self):
        samples = [
            w.banner_for([amber()], "West Sussex", now=NOW)["text"],
            w.low_data_list("BN17 5AA", "20:10", []),
            json.dumps(w.card_from_source(centre(opened_for="fire", swep_active=True), NOW)["card"]),
        ]
        for text in samples:
            self.assertNotIn(w.FORBIDDEN, text)
        for name in ("emergency.js", "emergency.css", "emergency.txt", "index.html", "docs/emergency_shelter_preview.md"):
            self.assertNotIn(w.FORBIDDEN, rd(name), name)

    def test_35_outline_is_the_signed_off_red(self):
        css, js = rd("emergency.css"), rd("emergency.js")
        self.assertEqual((w.OUTLINE_PX, w.LEFT_EDGE_PX, w.RED), (2, 6, "#FF3B30"))
        self.assertIn("border:2px solid #FF3B30", css)
        self.assertIn("border-left:6px solid #FF3B30", css)
        self.assertIn('class="em-card em-pop"', js)
        self.assertIn("html.em-preview .em-card{", css)
        self.assertNotIn("#D70015", css)

    def test_36_badge_is_white_900_16px(self):
        css = rd("emergency.css")
        self.assertIn("font-size:16px;font-weight:900", css)
        self.assertIn("color:#FFFFFF", css)
        self.assertIn("background:#FF3B30", css)
        self.assertEqual((w.BADGE_PX, w.BADGE_WEIGHT, w.WHITE), (16, 900, "#FFFFFF"))
        self.assertIn(w.FONT_STACK, css)
        self.assertNotIn("#E63946", css)
        self.assertNotIn("em-preview", rd("header.css"))

    def test_37_pin_is_red_house_with_white_edge(self):
        js = rd("emergency.js")
        self.assertIn('fill="#FF3B30"', js)
        self.assertIn('stroke="#FFFFFF"', js)
        self.assertIn("M18.66437", js)
        self.assertIn("CC0", js)
        svg = rd("assets/ocha-house-white.svg")
        self.assertIn("M18.66437", svg)
        self.assertIn("CC0", svg)

    def test_preview_flag_leaves_the_live_default_unchanged(self):
        on = w.compose([amber()], [centre()], "West Sussex", NOW, preview="emergency")
        off = w.compose([amber()], [centre()], "West Sussex", NOW, preview=None)
        self.assertTrue(on["banner"]["show"])
        self.assertTrue(on["cards"])
        self.assertFalse(off["banner"]["show"])
        self.assertEqual(off["cards"], [])
        self.assertFalse(off["layer_on"])
        self.assertIsNone(off["key"])
        self.assertTrue(off["live_default_unchanged"])
        html = rd("index.html")
        self.assertIn("q.get('preview')!=='emergency'", html)
        self.assertNotIn("em-card", html)

    def test_preview_report_does_not_invent_shelters(self):
        d = tempfile.mkdtemp()
        payload = w.write_emergency_preview([amber()], ["Natural Resources Wales: no API key"], ["NRW skipped (no API key); other feeds still run"], root=d, now=NOW)
        self.assertEqual(payload["cards"], [])
        self.assertTrue(payload["preview_only"])
        self.assertTrue(payload["goes_live_only_with_dean_ok"])
        self.assertIn("999", payload["text_list"])
        self.assertNotIn(w.FORBIDDEN, payload["text_list"])
        self.assertTrue(any("NRW skipped" in n for n in payload["watchdog_notes"]))

    def test_workflow_is_manual_until_dean_oks_it(self):
        yml = rd(".github/workflows/emergency-preview.yml")
        self.assertIn("workflow_dispatch", yml)
        self.assertNotIn("schedule:", yml)
        self.assertIn("does not deploy", yml)

    def test_999_button_is_full_width(self):
        css = rd("emergency.css")
        self.assertIn("a.em-999{display:flex!important;width:100%", css)
        self.assertIn("background:#34C759", css)
        self.assertIn("background:#F5C518", css)
        self.assertIn("999 Emergency services", rd("emergency.js"))

    def test_38_every_live_centre_is_kept_for_every_visitor(self):
        """Dean 26 Oct: the list is national. Do not filter it by the visitor or the warning area."""
        js = rd("emergency.js").replace(" ", "")
        self.assertIn("return!!(c&&c.live&&!c.example)", js)
        self.assertIn("CLICK HERE FOR YOUR NEAREST SHELTER", rd("emergency.js"))
        self.assertIn("Go to nearest open rest centre", rd("emergency.js"))
        css = rd("emergency.css").replace(" ", "")
        self.assertIn("text-decoration:underline", css)
        self.assertIn("text-transform:uppercase", css)
        self.assertIn("em-banner-b#em-banner{background:#000000}", css)
        self.assertIn('fill="#FF3B30"', rd("emergency.js"))


def _centre(name, lat, lng, until="2099-01-01T12:00:00+00:00", **kw):
    row = {"id": name.lower().replace(" ", "-"), "name": name, "live": True, "lat": lat, "lng": lng,
           "open_until": until, "open_until_label": "later", "phone": "01234 000000"}
    row.update(kw)
    return row


class BannerClick(unittest.TestCase):
    """Dean 26 Oct: the red banner jumps to the nearest open rest centre. These fail on the old banner."""

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            raise unittest.SkipTest("playwright not available")
        if not os.path.exists("/usr/bin/google-chrome"):
            raise unittest.SkipTest("no chrome")
        import functools, http.server, threading
        cls._feed = os.path.join(ROOT, "reports", "emergency_preview.json")
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT); h.log_message = lambda *a: None
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        cls._pw = sync_playwright().start()
        cls.browser = cls._pw.chromium.launch(executable_path="/usr/bin/google-chrome")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "browser", None): cls.browser.close()
        if getattr(cls, "_pw", None): cls._pw.stop()
        if getattr(cls, "srv", None): cls.srv.shutdown()
        if getattr(cls, "_feed", None) and os.path.exists(cls._feed): os.remove(cls._feed)

    def setUp(self):
        if os.path.exists(self._feed): os.remove(self._feed)

    def tearDown(self):
        if os.path.exists(self._feed): os.remove(self._feed)

    def _page(self, width=390, scheme="light", geo=None):
        kw = dict(viewport={"width": width, "height": 844}, color_scheme=scheme, device_scale_factor=1)
        if geo:
            kw["permissions"] = ["geolocation"]
            kw["geolocation"] = geo
        ctx = self.browser.new_context(**kw)
        ctx.add_init_script("window.__geoCalls=0;try{const g=navigator.geolocation;const o=g.getCurrentPosition.bind(g);g.getCurrentPosition=function(){window.__geoCalls++;return o.apply(this,arguments)}}catch(e){}")
        pg = ctx.new_page()
        self.addCleanup(ctx.close)
        return pg

    def _open(self, pg, query):
        pg.goto(self.base + "/?preview=emergency&fresh=1&nocount=1" + query, wait_until="load")
        if "light" in (pg.evaluate("()=>matchMedia('(prefers-color-scheme: light)').matches") and "light" or ""):
            pass
        return pg

    def _feed_cards(self, cards, warnings=None):
        os.makedirs(os.path.dirname(self._feed), exist_ok=True)
        json.dump({"preview_only": True, "cards": cards, "warnings": warnings or []}, open(self._feed, "w"), ensure_ascii=False)

    def _theme(self, pg, scheme):
        pg.evaluate("(m)=>document.documentElement.classList.toggle('light', m==='light')", scheme)

    def _banner_info(self, pg):
        return pg.evaluate("""()=>{const b=document.getElementById('em-banner');const hit=b.querySelector('button,a.em-hit')||b;
          const cta=b.querySelector('.em-cta');const cs=cta?getComputedStyle(cta):null;const bs=getComputedStyle(b);
          const br=b.getBoundingClientRect();const cr=cta?cta.getBoundingClientRect():br;
          return {tag:hit.tagName,name:hit.getAttribute('aria-label')||'',cta:cta?cta.textContent:'',
            weight:cs?cs.fontWeight:'',deco:cs?cs.textDecorationLine:'',transform:cs?cs.textTransform:'',
            ctaColor:cs?cs.color:'',bg:bs.backgroundColor,color:bs.color,
            overflow:b.scrollWidth>b.clientWidth+1||br.right>innerWidth+1||br.left<-1||cr.right>innerWidth+1||cr.left<-1,
            icons:b.querySelectorAll('.em-ico').length,tab:hit.tabIndex}}""")

    def _go(self, pg, name):
        pg.click("#em-banner .em-cta")
        pg.wait_for_selector(".em-card.em-go h3", timeout=8000)
        got = pg.locator(".em-card.em-go h3").inner_text()
        self.assertEqual(got, name, pg.evaluate("()=>({geo:window.__geoCalls,names:[...document.querySelectorAll('.em-card h3')].map(h=>h.textContent),on:[...document.querySelectorAll('.em-card')].filter(e=>!e.hidden).map(e=>e.getAttribute('data-em'))})"))

    def _map(self, pg, name, lat, lng):
        pg.wait_for_selector(".leaflet-popup-content", timeout=8000)
        last = None
        for _ in range(50):
            last = pg.evaluate("""([n,la,ln])=>{const pop=document.querySelector('.leaflet-popup-content');const c=map.getCenter();
              return {ok:!!(pop&&pop.innerText.indexOf(n)>=0&&Math.abs(c.lat-la)<0.45&&Math.abs(c.lng-ln)<0.45),
                pop:pop?pop.innerText.slice(0,80):'',lat:c.lat,lng:c.lng}}""", [name, lat, lng])
            if last["ok"]:
                return
            pg.wait_for_timeout(100)
        self.fail(last)

    def test_banner_is_clickable(self):
        for scheme in ("dark", "light"):
            pg = self._page(390, scheme); self._open(pg, "&sample=1"); self._theme(pg, scheme)
            pg.wait_for_selector("#em-banner .em-cta")
            info = self._banner_info(pg)
            self.assertIn(info["tag"], ("BUTTON", "A"), scheme)
            self.assertEqual(info["name"], "Go to nearest open rest centre", scheme)
            self.assertGreaterEqual(info["tab"], 0, scheme)
            self.assertEqual(info["cta"], "CLICK HERE FOR YOUR NEAREST SHELTER", scheme)
            self.assertEqual(info["deco"], "underline", scheme)
            self.assertEqual(info["transform"], "uppercase", scheme)
            self.assertIn(info["weight"], ("900", "800", "bold"), scheme)
            self.assertEqual(info["ctaColor"], "rgb(255, 255, 255)", scheme)
            self.assertEqual(info["color"], "rgb(255, 255, 255)", scheme)
            self.assertEqual(info["bg"], "rgb(255, 59, 48)", scheme)
            self.assertEqual(info["icons"], 0, scheme)
            self.assertFalse(info["overflow"], scheme)
            pg.set_viewport_size({"width": 320, "height": 700})
            self.assertFalse(self._banner_info(pg)["overflow"], scheme)
            pg.locator("#em-banner button").focus()
            pg.keyboard.press("Enter")
            pg.wait_for_selector(".em-card.em-go")
            self.assertEqual(pg.locator(".em-card.em-go h3").inner_text(), "Example Leisure Centre (example)")
            pg.close()

    def test_sample_goes_to_nearest_open_centre_with_a_location(self):
        pg = self._page(); self._open(pg, "&sample=1"); pg.wait_for_selector("#em-banner .em-cta")
        pg.evaluate("()=>nearest(51.5074,-0.1278,'London')")
        self._go(pg, "Example Community Hall (example)")
        self._map(pg, "Example Community Hall (example)", 51.5074, -0.1278)
        self.assertEqual(pg.evaluate("document.activeElement&&document.activeElement.getAttribute('data-em')"), "example-hall")

    def test_goes_to_the_first_centre_without_a_location(self):
        cards = [_centre("Aberdeen Rest Centre", 57.1499, -2.0938, area="Aberdeen"),
                 _centre("Birmingham Rest Centre", 52.4793, -1.9029, area="Birmingham")]
        self._feed_cards(cards, [{"areas": ["Cornwall"], "level": "red", "title": "Severe Flood Warning: Cornwall"}])
        pg = self._page(); self._open(pg, ""); pg.wait_for_selector("#em-banner .em-cta")
        pg.wait_for_selector(".em-card h3")
        self._go(pg, "Aberdeen Rest Centre")
        self.assertEqual(pg.evaluate("window.__geoCalls"), 0)
        self._map(pg, "Aberdeen Rest Centre", 57.1499, -2.0938)

    def test_expired_centres_are_skipped(self):
        cards = [_centre("London Rest Centre", 51.50, -0.12, until="2000-01-01T00:00:00+00:00"),
                 _centre("Aberdeen Rest Centre", 57.1499, -2.0938),
                 _centre("Birmingham Rest Centre", 52.4793, -1.9029)]
        self._feed_cards(cards)
        pg = self._page(); self._open(pg, ""); pg.wait_for_selector("text=Birmingham Rest Centre")
        self.assertTrue(pg.evaluate("document.querySelector('[data-em=\"london-rest-centre\"]').hidden"))
        pg.evaluate("()=>nearest(51.5074,-0.1278,'London')")
        self._go(pg, "Birmingham Rest Centre")
        self._map(pg, "Birmingham Rest Centre", 52.4793, -1.9029)
        self.assertNotEqual(pg.locator(".em-card.em-go").get_attribute("data-em"), "london-rest-centre")

    def test_text_only_link_still_opens_emergency_txt(self):
        pg = self._page(); self._open(pg, "&sample=1"); pg.wait_for_selector("#em-banner a.em-text")
        self.assertEqual(pg.locator("#em-banner a.em-text").get_attribute("href"), "emergency.txt")
        held = self._page(); self._open(held, "&sample=1"); held.wait_for_selector("#em-banner a.em-text")
        held.evaluate("document.querySelector('#em-banner a.em-text').addEventListener('click',e=>e.preventDefault(),true)")
        held.click("#em-banner a.em-text")
        held.wait_for_timeout(400)
        self.assertEqual(held.locator(".em-card.em-go").count(), 0)
        with pg.expect_navigation(wait_until="load", timeout=8000):
            pg.click("#em-banner a.em-text")
        self.assertTrue(pg.url.endswith("emergency.txt"), pg.url)
        body = pg.locator("body").inner_text()
        self.assertIn("999", body)
        self.assertIn("Floodline", body)

    def test_all_live_centres_stay_visible(self):
        cards = [_centre("Penzance Rest Centre", 50.1186, -5.5371, area="Cornwall"),
                 _centre("Aberdeen Rest Centre", 57.1499, -2.0938, area="Aberdeen"),
                 _centre("Birmingham Rest Centre", 52.4793, -1.9029, area="Birmingham"),
                 _centre("Should Not Show", 51.5, -0.1, example=True),
                 _centre("Held Centre", 51.5, -0.1, live=False)]
        self._feed_cards(cards, [{"areas": ["Cornwall"], "level": "red", "title": "Severe Flood Warning: Cornwall"}])
        pg = self._page(); self._open(pg, ""); pg.wait_for_selector("text=Penzance Rest Centre")
        names = lambda: pg.evaluate("[...document.querySelectorAll('.em-card h3')].map(h=>h.textContent)")
        self.assertEqual(names(), ["Penzance Rest Centre", "Aberdeen Rest Centre", "Birmingham Rest Centre"])
        pg.evaluate("()=>nearest(51.5074,-0.1278,'London')")
        pg.wait_for_timeout(400)
        self.assertEqual(names(), ["Penzance Rest Centre", "Aberdeen Rest Centre", "Birmingham Rest Centre"])
        self.assertNotIn("Should Not Show", names())
        self.assertNotIn("Held Centre", names())

    def test_granted_geolocation_is_used_without_a_search(self):
        cards = [_centre("Birmingham Rest Centre", 52.4793, -1.9029), _centre("Aberdeen Rest Centre", 57.1499, -2.0938)]
        self._feed_cards(cards)
        pg = self._page(geo={"latitude": 57.15, "longitude": -2.09})
        self._open(pg, ""); pg.wait_for_selector("#em-banner .em-cta")
        self._go(pg, "Aberdeen Rest Centre")
        self.assertGreaterEqual(pg.evaluate("window.__geoCalls"), 1)

    def test_banner_variants_keep_the_map_pin_red(self):
        for kind, bg, circle in (("a", "rgb(255, 59, 48)", True), ("b", "rgb(0, 0, 0)", False)):
            for scheme in ("dark", "light"):
                pg = self._page(390, scheme); self._open(pg, "&sample=1&banner=%s" % kind); self._theme(pg, scheme)
                pg.wait_for_selector("#em-banner .em-ico")
                info = self._banner_info(pg)
                self.assertEqual(info["cta"], "CLICK HERE FOR YOUR NEAREST SHELTER", (kind, scheme))
                self.assertEqual(info["bg"], bg, (kind, scheme))
                self.assertEqual(info["ctaColor"], "rgb(255, 255, 255)", (kind, scheme))
                self.assertEqual(info["name"], "Go to nearest open rest centre", (kind, scheme))
                fills = pg.eval_on_selector_all("#em-banner .em-ico svg path", "els=>els.map(e=>e.getAttribute('fill'))")
                self.assertIn("#FF3B30", fills, (kind, scheme))
                box = pg.evaluate("""()=>{const e=document.querySelector('#em-banner .em-ico');const s=getComputedStyle(e);const r=e.getBoundingClientRect();
                  return {bg:s.backgroundColor,w:r.width,h:r.height,rad:parseFloat(s.borderTopLeftRadius)}}""")
                if circle:
                    self.assertEqual(box["bg"], "rgb(255, 255, 255)", (kind, scheme))
                    self.assertAlmostEqual(box["w"], box["h"], delta=1)
                    self.assertGreaterEqual(box["rad"], box["w"] / 2 - 1)
                else:
                    self.assertNotEqual(box["bg"], "rgb(255, 255, 255)", (kind, scheme))
                pg.set_viewport_size({"width": 320, "height": 700})
                self.assertFalse(self._banner_info(pg)["overflow"], (kind, scheme))
                pg.click("#em-banner .em-cta")
                pg.wait_for_selector(".em-card.em-go")
                self.assertEqual(pg.locator(".em-card.em-go h3").inner_text(), "Example Leisure Centre (example)")
                pg.close()

    def test_live_default_has_no_banner(self):
        pg = self._page(); pg.goto(self.base + "/?fresh=1&nocount=1", wait_until="load")
        self.assertEqual(pg.locator("#em-banner").count(), 0)
        self.assertNotIn("em-preview", pg.evaluate("document.documentElement.className"))
