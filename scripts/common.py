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
    """Keep previous entries missing from today's scan (last_verified unchanged), flag stale >7d,
    move to recently_closed after `close_after` days unseen or when flagged closed; purge closed after 30d."""
    d = lambda s: datetime.date.fromisoformat(s)
    rd = d(run_day)
    items = {x["id"]: x for x in fresh}
    closed = {x["id"]: x for x in (prev or {}).get("recently_closed", [])}
    for x in (prev or {}).get("items", []):
        if x["id"] in items: continue
        unseen = (rd - d(x["last_verified"])).days
        if unseen > close_after:
            x["closed_on"] = run_day; x["closed_reason"] = f"No longer listed by source (unseen {unseen} days)"; closed[x["id"]] = x
        else: items[x["id"]] = x
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

MANUAL_BLOCK_DAYS = 14  # Dean, 1 Nov 2026: hand-checked rows survive a blocked fetch for 14 days from the last hand-check

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
    recheck=True: every run re-fetches each entry's source page and only publishes what it confirms (scripts/recheck.py)."""
    pub, pending = [], []
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
        grace = bool((v or (unverified and x["id"] in unverified)) and recheck and is_transient(rc) and age is not None and 0 <= age <= GRACE_HOURS)
        mdays = manual_checked_days(x, now)
        blocked = bool(not grace and v and recheck and is_fetch_blocked(rc) and mdays is not None and 0 <= mdays <= MANUAL_BLOCK_DAYS)
        if blocked:
            grace = True
            LC.setdefault(x["id"], str(x["checked_on"])[:10] + "T00:00:00+00:00")
            graced.append({"id": x["id"], "name": x["name"], "reason": "kept, fetch blocked (%s)" % rc.get("reason"), "http": rc.get("http"),
                           "last_confirmed": str(x["checked_on"])[:10], "hours_since": round(mdays * 24.0, 1), "kept_fetch_blocked": True})
        elif grace:
            graced.append({"id": x["id"], "name": x["name"], "reason": rc.get("reason"), "http": rc.get("http"), "last_confirmed": LC[x["id"]], "hours_since": round(age, 1)})
        if (v or (unverified and x["id"] in unverified)) and recheck and (rc is None or not rc.get("ok")) and not grace:
            pending.append({"id": x["id"], "name": x["name"], "first_seen": run_day, "reason": "omitted this run: " + (rc or {}).get("reason", "not re-checked"),
                            "recheck": {k: (rc or {}).get(k) for k in ("url", "final_url", "fetched_at", "http", "sha256")}}); continue
        if v and has_evidence and (not valid_until or run_day <= valid_until(v)):
            x = dict(x); x["verified"] = True; x["evidence_url"] = v.get("evidence_url", ""); x["verified_on"] = v.get("verified_on", "")
            for k in ("phone", "address", "access", "postcode", "lat", "lng", "hours", "evidence_name", "scheme_start", "scheme_end", "scheme_dates"):  # pin/address fixes persist nightly
                if v.get(k): x[k] = v[k]
            x["tier"] = "verified"
            if grace: x["grace"] = True; x["fetched_at"] = LC[x["id"]]
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
        elif unverified and x["id"] in unverified and (not valid_until or run_day <= valid_until(dict(verified_on=unverified[x["id"]].get("checked_on", "2000-01-01")))) \
                and unverified[x["id"]].get("sign_url") and not x.get("ended") and not x.get("flag_closed"):
            # Tier 2: confirmed open/accessible some other way (sign of life), no stated hours or formal page.
            u = unverified[x["id"]]; x = dict(x); x["tier"] = "unverified"; x["verified"] = False
            x["sign_url"] = u["sign_url"]; x["checked_on"] = (rc or {}).get("fetched_at", "")[:10] or u.get("checked_on", "")
            if grace: x["grace"] = True; x["fetched_at"] = LC[x["id"]]; x["checked_on"] = LC[x["id"]][:10]
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
        verification_gate.graced = graced
    ok = {x["id"] for x in pub}
    if prev:
        prev = dict(prev)
        keep = {x["id"] for x in pub}  # only what was confirmed THIS run; nothing carried over
        prev["items"] = [x for x in prev.get("items", []) if x["id"] in keep]
        prev["recently_closed"] = [x for x in prev.get("recently_closed", []) if x["id"] in keep]
    return pub, prev, len(pending)
