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
                card["checked_at"] = now.isoformat(timespec="seconds")
                inc[key] = {"council": p.get("council"), "url": p.get("url"), "card": card}
                seen.add(key)
    for key in list(inc):
        if key not in seen:
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
