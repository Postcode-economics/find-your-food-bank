"""Public incident rest-centre file (SWEP and warm spaces never included)."""
import datetime, json, os, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MODE = "overrides/incident_rest_centre_mode.json"
STATE = "logs/incident_rest_centre_live_state.json"
OUT_JSON = "incident_rest_centre_live.json"
OUT_JS = "incident_rest_centre_live.js"


def mode_public(root=None):
    root = root or ROOT
    try:
        return bool(json.load(open(os.path.join(root, MODE), encoding="utf-8")).get("public"))
    except Exception:
        return False


def load_state(path=None):
    path = path or os.path.join(ROOT, STATE)
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {"incidents": {}}



def load_public_live(root=None):
    """Read the public live file (already on the site). Empty dict if missing."""
    root = root or ROOT
    try:
        return json.load(open(os.path.join(root, OUT_JSON), encoding="utf-8"))
    except Exception:
        return {}


def hydrate_from_public_live(root=None, now=None):
    """Rebuild gitignored watch state from the public live file when state is empty.

    After rule 97, logs/ are not committed. A new watch job therefore starts with no
    live_state / pages snapshot. Without a restore, an already-published rest centre
    would not be re-scanned or expired. Rebuild from the already-public live file only
    (rule 97). Do not use Actions cache or artifacts on this public repo. Returns a short note.
    """
    root = root or ROOT
    now = now or datetime.datetime.now(datetime.timezone.utc)
    state_path = os.path.join(root, STATE)
    state = load_state(state_path)
    if state.get("incidents"):
        return "state-present"
    payload = load_public_live(root)
    cards = list(payload.get("cards") or [])
    if not cards:
        return "no-cards"
    incidents = {}
    pages = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        url = (card.get("source_url") or "").strip()
        council = card.get("council") or card.get("opened_by") or ""
        key = "%s|%s" % (council, url or card.get("name") or "rest-centre")
        incidents[key] = {"council": council, "url": url, "card": dict(card)}
        if url:
            rc = {
                "active": True,
                "name": card.get("name") or "Rest centre",
                "quote": card.get("quote") or "",
                "location": card.get("address") or "",
            }
            pages.append({
                "council": council,
                "url": url,
                "http": 200,
                "status": None,
                "rest_centre": rc,
                "quote": card.get("quote") or "",
            })
    if not incidents:
        return "no-cards"
    state = {"incidents": incidents, "updated": now.isoformat(timespec="seconds"), "hydrated_from": OUT_JSON}
    save_state(state, state_path)
    # Seed the pages snapshot so the next fetch does not treat an already-live centre as a new switch-on.
    try:
        import incident_rest_centre_switch_on as irso
        snap = irso.load_snapshot(root)
        if not snap and pages:
            irso.save_snapshot(pages, root)
    except Exception:
        pass
    return "hydrated-%d" % len(incidents)


def save_state(state, path=None):
    path = path or os.path.join(ROOT, STATE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(state, open(path, "w"), indent=1, ensure_ascii=False)


def _geocode_postcode(pc):
    if not pc:
        return None, None
    try:
        import urllib.request

        u = "https://api.postcodes.io/postcodes/" + pc.replace(" ", "%20")
        r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "helpmap.uk"}), timeout=8).read())
        if r.get("status") == 200 and r.get("result"):
            res = r["result"]
            return res.get("latitude"), res.get("longitude")
    except Exception:
        pass
    return None, None


def incident_record(page, now=None):
    import weather
    import council_lad
    import rest_centre_scan as rcs

    rc = page.get("rest_centre") or {}
    if not rc.get("active"):
        return None
    text = page.get("_text") or rc.get("quote") or ""
    council = page.get("council") or ""
    url = page.get("url") or ""
    if not rcs.rest_centre_on(text):
        return None
    ann = weather.parse_announcement(text, council, url, now=now)
    if not ann or ann.get("closed") or ann.get("review"):
        return None
    src = dict(ann)
    src.setdefault("added", now)
    src["category"] = "incident_rest_centre"
    src["council"] = council
    src["url"] = url
    src["source_url"] = url
    src["quote"] = rc.get("quote") or text[:320]
    pc = ann.get("address") or rcs.extract_postcode(text) or rc.get("location") or ""
    if pc and not ann.get("address"):
        src["address"] = pc
    lat, lng = ann.get("lat"), ann.get("lng")
    if lat is None and pc:
        lat, lng = _geocode_postcode(pc.replace(" ", " "))
    if lat is not None:
        src["lat"], src["lng"] = lat, lng
    lad = council_lad.lad_for_council(council)
    if lad:
        src["lad"] = lad
    src["checked_label"] = weather.fmt_checked(now or datetime.datetime.now(datetime.timezone.utc))
    return src


def sync_from_pages(pages, root=None, now=None):
    """Update state from SWEP run pages; write public JSON when mode is public."""
    root = root or os.getcwd()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    sys.path.insert(0, os.path.join(root, "scripts"))
    import weather

    state = load_state(os.path.join(root, STATE))
    inc = state.get("incidents") or {}
    seen = set()
    confirmed_off = set()
    for p in pages or []:
        key = (p.get("council") or "") + "|" + (p.get("url") or "")
        rec = incident_record(dict(p, _text=p.get("_text") or ""), now=now)
        if rec:
            d = weather.card_from_source(rec, now)
            if d.get("publish") == "live" and d.get("card"):
                card = d["card"]
                card["category"] = "incident_rest_centre"
                card["council"] = p.get("council")
                card["lad"] = rec.get("lad")
                card["quote"] = rec.get("quote")
                card["last_checked"] = rec.get("checked_label") or weather.fmt_checked(now)
                card["checked_at"] = card["last_checked"]
                prev = (inc.get(key) or {}).get("card") or {}
                if not card.get("lad") and prev.get("lad"):
                    card["lad"] = prev["lad"]
                if (not card.get("opened_for") or card.get("opened_for") == "an incident") and prev.get("opened_for"):
                    card["opened_for"] = prev["opened_for"]
                if prev.get("open_until") and not weather.browser_hide(prev.get("open_until"), now):
                    card["open_until"] = prev["open_until"]
                    if prev.get("open_until_label"):
                        card["open_until_label"] = prev["open_until_label"]
                inc[key] = {"council": p.get("council"), "url": p.get("url"), "card": card}
                seen.add(key)
            elif p.get("http") in (200, None) and p.get("url"):
                confirmed_off.add(p.get("url"))
        elif p.get("http") in (200, None) and p.get("url"):
            confirmed_off.add(p.get("url"))
    for key in list(inc):
        url = (inc[key].get("url") or "")
        card = (inc[key].get("card") or {})
        if key in seen:
            continue
        if url and url in confirmed_off:
            del inc[key]
        elif weather.browser_hide(card.get("open_until"), now):
            del inc[key]
    state["incidents"] = inc
    state["updated"] = now.isoformat(timespec="seconds")
    save_state(state, os.path.join(root, STATE))
    write_public(root=root, state=state, now=now)
    return len(inc)


def write_public(root=None, state=None, now=None):
    root = root or ROOT
    now = now or datetime.datetime.now(datetime.timezone.utc)
    public = mode_public(root)
    state = state or load_state(os.path.join(root, STATE))
    cards = []
    councils = {}
    if public:
        for v in (state.get("incidents") or {}).values():
            c = v.get("card")
            if c and not weather_browser_hide(c, now):
                cards.append(c)
                if c.get("lad") and c.get("council"):
                    councils[c["lad"]] = c["council"]
    payload = {
        "public": public,
        "generated": now.isoformat(timespec="seconds"),
        "category": "incident_rest_centre",
        "cards": cards,
        "councils": councils,
    }
    jp = os.path.join(root, OUT_JSON)
    json.dump(payload, open(jp, "w"), indent=1, ensure_ascii=False)
    js = "window.incidentRestCentreLive=" + json.dumps(payload, ensure_ascii=False) + ";\n"
    open(os.path.join(root, OUT_JS), "w", encoding="utf-8").write(js)
    return payload


def weather_browser_hide(card, now):
    import weather

    return weather.browser_hide(card.get("open_until"), now)


def drop_expired(root=None, now=None):
    """Remove live cards whose open-until time has passed. Returns the removed records. Does not rewrite the file when nothing expired."""
    root = root or ROOT
    now = now or datetime.datetime.now(datetime.timezone.utc)
    import weather
    state = load_state(os.path.join(root, STATE))
    inc = state.get("incidents") or {}
    gone = []
    for key, v in list(inc.items()):
        card = v.get("card") or {}
        if weather.browser_hide(card.get("open_until"), now):
            gone.append(v)
            del inc[key]
    if not gone:
        return []
    state["incidents"] = inc
    state["updated"] = now.isoformat(timespec="seconds")
    save_state(state, os.path.join(root, STATE))
    write_public(root=root, state=state, now=now)
    return gone


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--hydrate-from-live":
        print(hydrate_from_public_live())
        raise SystemExit(0)
    raise SystemExit("usage: incident_rest_centre_live.py --hydrate-from-live")
