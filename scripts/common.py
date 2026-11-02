import json, os, re, time, urllib.request, datetime
UA = {"User-Agent": "postcode-economics-map/1.0 (+https://postcode-economics.github.io/find-your-food-bank/)"}
PC_RE = re.compile(r"\b([A-Z]{1,2}[0-9][0-9A-Z]?)\s*([0-9][A-Z]{2})\b", re.I)
def today(): return datetime.date.today().isoformat()
def get(url, data=None, tries=3, timeout=90):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()
        except Exception as e:
            err = e; time.sleep(5 * (k + 1))
    raise err
def postcode(s):
    m = PC_RE.search(s or "")
    return (m.group(1) + " " + m.group(2)).upper() if m else ""
def reverse_postcodes(points):
    """points: list of (key, lat, lng) -> {key: postcode} via postcodes.io bulk reverse (free)."""
    out = {}
    for i in range(0, len(points), 100):
        chunk = points[i:i+100]
        body = json.dumps({"geolocations": [{"latitude": la, "longitude": ln, "limit": 1, "radius": 500} for _, la, ln in chunk]}).encode()
        try:
            req = urllib.request.Request("https://api.postcodes.io/postcodes", data=body, headers={**UA, "Content-Type": "application/json"})
            res = json.load(urllib.request.urlopen(req, timeout=60))["result"]
            for (k, _, _), r in zip(chunk, res):
                if r["result"]: out[k] = r["result"][0]["postcode"]
        except Exception: pass
    return out
def load_js(path, var):
    if not os.path.exists(path): return None
    t = open(path, encoding="utf-8").read()
    return json.loads(t[t.index("=") + 1:].strip().rstrip(";"))
def write_js(path, var, obj):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"var {var}=" + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + ";\n")
def merge_lifecycle(prev, fresh, run_day, stale_days=7, close_after=14, keep_closed=30):
    """Keep previous entries missing from today's scan (last_verified unchanged), flag stale >7d.
    A place that simply disappeared from a feed stays, with its last good data: days unseen are not a closure.
    `close_after` is unused for that reason (2 Nov 2026). flag_closed still moves a place to recently_closed; closed rows purge after 30d."""
    d = lambda s: datetime.date.fromisoformat(s)
    rd = d(run_day)
    items = {x["id"]: x for x in fresh}
    closed = {x["id"]: x for x in (prev or {}).get("recently_closed", [])}
    for x in (prev or {}).get("items", []):
        if x["id"] in items: continue
        items[x["id"]] = x
    for k, x in list(items.items()):
        if x.get("flag_closed"):
            x.setdefault("closed_on", run_day); closed[k] = items.pop(k)
    for k in list(closed):
        if k in items and not items[k].get("flag_closed"): closed.pop(k)  # re-listed
        elif (rd - d(closed[k]["closed_on"])).days > keep_closed: closed.pop(k)
    for x in items.values():
        x["stale"] = (rd - d(x["last_verified"])).days > stale_days
    return sorted(items.values(), key=lambda x: x["name"].lower()), sorted(closed.values(), key=lambda x: x["closed_on"], reverse=True)
def append_log(path, entry):
    log = json.load(open(path)) if os.path.exists(path) else []
    log.insert(0, entry); json.dump(log[:120], open(path, "w"), indent=1)

# ---- Verification gate (added 2026-10-21, Dean: "100% categorically" verified only) ----
# Only entries on the layer's allowlist (overrides/<layer>_verified.json) are published.
# Everything else the daily scrape finds goes into logs/<layer>_pending.json (not shown on the map)
# with the result of an automatic pre-check. The pre-check never publishes anything by itself:
# a human adds the evidence (URL + quote) to the allowlist file.
def load_verified(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
GRACE_HOURS = 48  # Dean, 23 Oct 2026: keep a place through a brief outage if confirmed in the last 48h

def is_transient(rc):
    """Source briefly unreachable (bot check, 429, timeout, 5xx, empty/JS-only page) - not a content failure."""
    if not rc or rc.get("ok"): return False
    h = rc.get("http")
    if h == 200: return "no readable text" in (rc.get("reason") or "")
    if h in ("error", None): return True
    return isinstance(h, int) and (h in (403, 408, 425, 429) or h >= 500 or 200 <= h < 300)

MANUAL_BLOCK_DAYS = 14  # Dean, 1 Nov 2026: a hand-checked row already on the map survives a blocked fetch for 14 days from the last hand-check
HELD_TAG = "shelter fetch held"  # this run's held shelters, in reports/manual_review.md; rewritten every shelter refresh

def _published_ids(prev):
    """Ids on the map in the file the build started from. A list or missing file is nothing published."""
    if not isinstance(prev, dict): return set()
    return {i.get("id") for i in (prev.get("items") or []) if isinstance(i, dict) and i.get("id")}

CLOSED_REASONS = ("source now says closed/ended", "feed says ended")

def source_says_closed(rc=None, entry=None):
    """True only when this run's own source says the place has closed. A broken, blocked, 404 or unread page is not closed."""
    entry = entry or {}
    if entry.get("flag_closed"): return True
    reason = ((rc or {}).get("reason") or "")
    if reason in CLOSED_REASONS or "flagged closed" in reason: return True
    return False

def record_layer_holds(rows, layer="shelters", root=".", replace=False):
    """Places left off THIS run (never published, or the source said closed). The next refresh rewrites the list.
    replace=True is the build. replace=False adds verify_fresh drops. A previous day's file is ignored by the guard."""
    import datetime
    root = root or "."
    run = datetime.date.today().isoformat()
    path = os.path.join(root, "logs", "%s_held.json" % layer)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cur = {}
    if not replace:
        try: cur = json.load(open(path, encoding="utf-8"))
        except Exception: cur = {}
        if cur.get("run") != run: cur = {}
    by = {} if replace or cur.get("run") != run else {r["id"]: r for r in (cur.get("held") or []) if isinstance(r, dict) and r.get("id")}
    for r in rows or []:
        if r.get("id"): by[r["id"]] = {"id": r["id"], "name": r.get("name") or r["id"], "reason": r.get("reason") or "held this run"}
    held = [by[k] for k in sorted(by)]
    json.dump({"run": run, "held": held}, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    _write_hold_report(held, root, layer)
    return held

def record_shelter_holds(rows, root=".", replace=False):
    return record_layer_holds(rows, "shelters", root, replace)

def _write_hold_report(held, root, layer="shelters"):
    """Replace one layer's held section of reports/manual_review.md. Hand-written text and the auto-discovery queue stay."""
    path = os.path.join(root, "reports", "manual_review.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tag = HELD_TAG if layer == "shelters" else "fetch held %s" % layer
    start, end = "<!-- %s -->" % tag, "<!-- /%s -->" % tag
    title = {"shelters": "Shelters", "warmspaces": "Warm spaces", "foodbanks": "Food banks"}.get(layer, layer)
    lines = ["## %s held this run (not on the map)" % title, "",
             "Left out of this run because this place was not already on the map and its page could not be read, or its own source says it has closed. A live listing whose page is blocked, broken or unread stays on the map. Tried again on the next refresh. Not a freeze and not a skip list.", ""]
    lines += ["- %s (%s): %s" % (r.get("name") or r["id"], r["id"], r.get("reason") or "held this run") for r in held] or ["None this run."]
    block = start + "\n" + "\n".join(lines) + "\n" + end
    prev = open(path, encoding="utf-8").read() if os.path.exists(path) else "# Manual review queue (not on the map)\n"
    if start in prev and end in prev:
        text = re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block, prev, count=1, flags=re.S)
    else:
        marker = "<!-- AUTO-DISCOVERY QUEUE"
        if marker in prev:
            pre, post = prev.split(marker, 1)
            text = pre.rstrip() + "\n\n" + block + "\n\n" + marker + post
        else:
            text = prev.rstrip() + "\n\n" + block + "\n"
    if not text.endswith("\n"): text += "\n"
    open(path, "w", encoding="utf-8").write(text)

def is_fetch_blocked(rc):
    """Source fetch blocked or server failing (403, 429, 5xx, timeout/network error) - never a page that loaded."""
    if not rc or rc.get("ok"): return False
    h = rc.get("http")
    if h in ("error", "timeout", None): return True
    return isinstance(h, int) and (h in (403, 408, 429) or h >= 500)

def manual_checked_days(x, now):
    """Days since a hand-checked shelters_manual row's checked_on, else None."""
    import datetime
    if not str(x.get("source", "")).startswith("Manual") or not x.get("checked_on"): return None
    try: d = datetime.date.fromisoformat(str(x["checked_on"])[:10])
    except ValueError: return None
    return (now.date() - d).days

def _hours_since(ts, now):
    import datetime
    try:
        t = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None: t = t.replace(tzinfo=datetime.timezone.utc)
        return (now - t).total_seconds() / 3600
    except Exception: return None

def infer_shelter_groups(entry, verified=None):
    """Who-it's-for for hand-verified manual rows when groups were left empty but quote/access state it (Dean 30 Oct 2026)."""
    if entry.get("groups"):
        return list(entry["groups"])
    v = verified or {}
    if v.get("groups"):
        return list(v["groups"])
    blob = " ".join(str(x or "") for x in (entry.get("referral"), v.get("quote"), v.get("access"), entry.get("name"))).lower()
    if "single homeless adult" in blob:
        return ["Single adults"]
    if "rough sleep" in blob or "single homeless" in blob:
        return ["Single homeless people"]
    if re.search(r"adults?\s+(over|aged)\s*18", blob) or "adults over 18" in blob:
        return ["Adults 18+"]
    if "young people" in blob or re.search(r"aged?\s*18\s*(to|-)\s*30", blob):
        return ["Young people"]
    return []

def verification_gate(fresh, prev, verified, run_day, pending_path, autocheck=None, valid_until=None, unverified=None, recheck=True, now=None):
    """Returns (published_fresh, filtered_prev). Writes pending list.
    recheck=True: every run re-fetches each entry's source page.
    A place already on the map stays, with its last good data, when this run's page is blocked, broken, 404, timed out or unread.
    There is no 48-hour or 14-day expiry on that keep. It is left off only when its own source says it has closed.
    A place that was not on the map, and whose read failed, is held for this run and tried again next run."""
    pub, pending, held = [], [], []
    layer_name = os.path.basename(pending_path).replace("_pending.json", "")
    published_ids = _published_ids(prev)
    prev_by_id = {}
    if isinstance(prev, dict):
        for it in prev.get("items") or []:
            if isinstance(it, dict) and it.get("id"): prev_by_id[it["id"]] = it
    RC = {}
    if recheck:
        from recheck import recheck_all
        RC = recheck_all(fresh, verified, unverified, pending_path.replace("_pending.json", "_recheck.json"))
        RC.pop("_run", None)
    import datetime
    now = now or datetime.datetime.now(datetime.timezone.utc)
    lc_path = pending_path.replace("_pending.json", "_last_confirmed.json")
    LC = json.load(open(lc_path)) if os.path.exists(lc_path) else {}
    for x in (prev or {}).get("items", []):  # seed from what is live now (its last confirmed fetch)
        if x.get("fetched_at") and x["id"] not in LC and not x.get("grace"): LC[x["id"]] = x["fetched_at"]
    graced = []
    import place_facts
    for x in fresh:
        v = verified.get(x["id"])
        has_evidence = bool(v and v.get("evidence_url") and (v.get("day_time_quote") or v.get("quote")))
        rc = RC.get(x["id"]) if recheck else None
        if recheck and rc and rc.get("ok"): LC[x["id"]] = rc.get("fetched_at") or now.replace(microsecond=0).isoformat()
        age = _hours_since(LC.get(x["id"]), now) if recheck else None
        failed = bool(recheck and (rc is None or not rc.get("ok")))
        closed_src = bool(failed and source_says_closed(rc, x))
        grace = blocked = False
        if failed and closed_src:
            reason = "omitted this run: " + ((rc or {}).get("reason") or "source says closed")
            pending.append({"id": x["id"], "name": x.get("name") or x["id"], "first_seen": run_day, "reason": reason,
                            "recheck": {k: (rc or {}).get(k) for k in ("url", "final_url", "fetched_at", "http", "sha256")}})
            held.append({"id": x["id"], "name": x.get("name") or x["id"], "reason": reason})
            continue
        if failed and x["id"] in published_ids:
            # Live listing: keep the last published copy. No 48-hour or 14-day expiry.
            old = dict(prev_by_id.get(x["id"]) or x)
            old["grace"] = True; old["kept_fetch_blocked"] = True
            if old.get("fetched_at"): LC.setdefault(x["id"], old["fetched_at"])
            graced.append({"id": x["id"], "name": old.get("name") or x.get("name"), "reason": "kept, fetch blocked (%s)" % ((rc or {}).get("reason") or (rc or {}).get("http")),
                           "http": (rc or {}).get("http"), "last_confirmed": str(old.get("fetched_at") or old.get("checked_on") or "")[:10],
                           "hours_since": round(age, 1) if age is not None else None, "kept_fetch_blocked": True})
            pub.append(old)
            continue
        if failed:
            reason = "held this run: read failed, not published before"
            held.append({"id": x["id"], "name": x.get("name") or x["id"], "reason": reason})
            pending.append({"id": x["id"], "name": x.get("name") or x["id"], "first_seen": run_day, "reason": reason,
                            "recheck": {k: (rc or {}).get(k) for k in ("url", "final_url", "fetched_at", "http", "sha256")}})
            continue
        if v and has_evidence and (x["id"] in published_ids or not valid_until or run_day <= valid_until(v)):
            x = dict(x); x["verified"] = True; x["evidence_url"] = v.get("evidence_url", ""); x["verified_on"] = v.get("verified_on", "")
            for k in ("phone", "address", "access", "postcode", "lat", "lng", "hours", "evidence_name", "scheme_start", "scheme_end", "scheme_dates"):  # pin/address fixes persist nightly
                if v.get(k): x[k] = v[k]
            x["tier"] = "verified"
            if grace:
                x["grace"] = True; x["fetched_at"] = LC[x["id"]]
                if blocked: x["kept_fetch_blocked"] = True  # internal marker read by verify_fresh; no public label
            elif rc and rc.get("ok"):  # Dean: every successful re-check moves the shown checked date forward
                x["first_verified_on"] = v.get("verified_on", ""); x["verified_on"] = x["last_verified"] = run_day
            if not grace and rc: x["fetched_at"] = rc.get("fetched_at"); x["recheck"] = {k: rc.get(k) for k in ("times_found", "days_found", "postcode_found", "referral_found")}
            if v.get("access_type"): x["access_type"] = v["access_type"]
            if v.get("phone_source"): x["phone_source"] = v["phone_source"]
            if v.get("phone_label"): x["phone_label"] = v["phone_label"]
            if not x.get("groups"):
                g = infer_shelter_groups(x, v)
                if g:
                    x["groups"] = g
                    x["groups_source"] = v.get("evidence_url") or v.get("evidence_name") or ""
            if v.get("access"): x["referral"] = v["access"][0].upper() + v["access"][1:]
            place_facts.copy_wheelchair(x, v)  # explicit only; a missing wheelchair stays missing
            pub.append(x)
        elif unverified and x["id"] in unverified and (x["id"] in published_ids or not valid_until or run_day <= valid_until(dict(verified_on=unverified[x["id"]].get("checked_on", "2000-01-01")))) \
                and unverified[x["id"]].get("sign_url") and not x.get("ended") and not x.get("flag_closed"):
            # Tier 2: confirmed open/accessible some other way (sign of life), no stated hours or formal page.
            u = unverified[x["id"]]; x = dict(x); x["tier"] = "unverified"; x["verified"] = False
            x["sign_url"] = u["sign_url"]; x["checked_on"] = (rc or {}).get("fetched_at", "")[:10] or u.get("checked_on", "")
            if grace:
                x["grace"] = True; x["fetched_at"] = LC[x["id"]]; x["checked_on"] = LC[x["id"]][:10]
                if blocked: x["kept_fetch_blocked"] = True
            elif rc: x["fetched_at"] = rc.get("fetched_at")
            if rc and rc.get("ok") and not grace: x["last_verified"] = run_day
            if u.get("access_type"): x["access_type"] = u["access_type"]
            place_facts.copy_wheelchair(x, u)
            for k in ("phone", "scheme_start", "scheme_end", "scheme_dates", "call_check"):  # hand-checked fixes on tier-2 entries persist every run
                if u.get(k): x[k] = u[k]
            pub.append(x)
        else:
            p = {"id": x["id"], "name": x["name"], "address": x.get("address", ""), "postcode": x.get("postcode", ""),
                 "source_url": x.get("source_url", ""), "website": x.get("website", ""), "first_seen": run_day,
                 "reason": ("allowlisted but missing evidence_url/day_time_quote" if v and not has_evidence else "verification expired") if v else "not on allowlist"}
            if autocheck:
                try: p["autocheck"] = autocheck(x)
                except Exception as e: p["autocheck"] = {"result": "error", "detail": str(e)[:120]}
            pending.append(p)
    old = {p["id"]: p for p in (json.load(open(pending_path)) if os.path.exists(pending_path) else [])}
    for p in pending:
        if p["id"] in old: p["first_seen"] = old[p["id"]].get("first_seen", run_day)
    json.dump(sorted(pending, key=lambda p: p["first_seen"], reverse=True), open(pending_path, "w"), indent=1, ensure_ascii=False)
    if recheck:
        json.dump(dict(sorted(LC.items())), open(lc_path, "w"), indent=0, ensure_ascii=False)
        layer = os.path.basename(pending_path).replace("_pending.json", "")
        os.makedirs("reports", exist_ok=True)
        with open(f"reports/{layer}_grace.md", "w") as f:
            f.write(f"# {layer}: kept on 48-hour grace ({now.replace(microsecond=0).isoformat()})\n\n")
            f.write("Source page briefly unreachable this run; kept because it was confirmed within the last %d hours.\n\n" % GRACE_HOURS)
            f.write("".join(f"- {g['name']} ({g['id']}): {g['reason']}; last confirmed {g['last_confirmed']} ({g['hours_since']}h ago)\n" for g in graced) or "None this run.\n")
            f.write("\n## Held this run (not published)\n\n")
            f.write("A place that was not on the map, whose page could not be read, is left out of this run. A place already on the map stays until its own source says it has closed. There is no 48-hour or 14-day expiry.\n\n")
            f.write("".join("- %s (%s): %s\n" % (h["name"], h["id"], h["reason"]) for h in held) or "None this run.\n")
        record_layer_holds(held, layer_name, replace=True)
        verification_gate.graced = graced
    verification_gate.held = held
    ok = {x["id"] for x in pub}
    if isinstance(prev, dict):
        prev = dict(prev)
        keep = {x["id"] for x in pub}
        examined = {x.get("id") for x in fresh if isinstance(x, dict)}
        # A live place missing from this scrape stays. One this run read and then held or closed does not.
        prev["items"] = [x for x in prev.get("items", []) if x["id"] in keep or x["id"] not in examined]
        prev["recently_closed"] = [x for x in prev.get("recently_closed", []) if x["id"] in keep or x["id"] not in examined]
    return pub, prev, len(pending)
