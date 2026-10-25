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
