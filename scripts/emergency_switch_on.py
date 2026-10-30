"""Immediate Dean email when a council emergency shelter switches ON (SWEP or rest centre).

Uses scripts/alert.py (label emergency-switch-on). Separate from digest weather alerts (key weather).
Never blocks the refresh."""
import datetime, json, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TAG = "emergency switch-on"
STATE = "logs/emergency_switch_state.json"
RUN = f"{os.environ.get('GITHUB_SERVER_URL','https://github.com')}/{os.environ.get('GITHUB_REPOSITORY','')}/actions/runs/{os.environ.get('GITHUB_RUN_ID','')}"

REST_OPEN = re.compile(
    r"\b(rest centre|reception centre|evacuation centre|emergency shelter)\b[^.\n]{0,160}\b("
    r"is (now )?open|has opened|has been opened|opened|opens)\b",
    re.I,
)
POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[\dA-Z]?\s*\d[A-Z]{2})\b")


def _quote_excerpt(quote, limit=320):
    q = re.sub(r"\s+", " ", quote or "").strip()
    return q[:limit] + ("…" if len(q) > limit else "")


def _location(text):
    m = POSTCODE.search(text or "")
    return m.group(1).upper() if m else ""


def rest_centre_activation(text, council, url):
    """Return an activation dict if visible text says a rest centre / emergency shelter is open."""
    try:
        import weather
        ann = weather.parse_announcement(text, council, url)
    except Exception:
        ann = None
    if ann and ann.get("closed"):
        return None
    if ann and ann.get("name"):
        return {
            "kind": "rest_centre",
            "label": ann["name"],
            "quote": _quote_excerpt(text),
            "url": url,
            "location": ann.get("address") or _location(text),
        }
    m = REST_OPEN.search(text or "")
    if not m:
        return None
    q = _quote_excerpt(text[max(0, m.start() - 40) : m.end() + 120])
    name = m.group(1).strip().title()
    return {"kind": "rest_centre", "label": name, "quote": q, "url": url, "location": _location(text)}


def activations_for_page(page, run_day=None):
    council = page.get("council") or ""
    url = page.get("url") or ""
    text = page.get("_text") or ""
    out = {}
    if page.get("status") == "active":
        out[f"{council}|SWEP"] = {
            "council": council,
            "label": "SWEP",
            "kind": "swep",
            "quote": page.get("quote") or _quote_excerpt(text),
            "url": url,
            "location": _location(text),
        }
    rc = page.get("rest_centre")
    if isinstance(rc, dict) and rc.get("active"):
        key = f"{council}|{rc.get('name') or rc.get('label') or 'rest centre'}"
        out[key] = {
            "council": council,
            "label": rc.get("name") or rc.get("label") or "rest centre",
            "kind": "rest_centre",
            "quote": rc.get("quote") or _quote_excerpt(text),
            "url": url,
            "location": rc.get("location") or _location(text),
        }
    return out


def merge_pages(pages, run_day=None):
    all_a = {}
    for p in pages or []:
        all_a.update(activations_for_page(p, run_day))
    return all_a


def load_state(path=None):
    path = path or os.path.join(ROOT, STATE)
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {"waiting": {}}


def save_state(state, path=None):
    path = path or os.path.join(ROOT, STATE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(state, open(path, "w"), indent=1, ensure_ascii=False)


def pending_lines(waiting):
    lines = []
    for key in sorted(waiting):
        w = waiting[key]
        loc = f" ({w['location']})" if w.get("location") else ""
        lines.append(
            f"- **{w['council']}** — {w['label']}{loc} — {w.get('url') or ''} — “{_quote_excerpt(w.get('quote',''), 160)}”"
        )
    return lines


def sync_pending_dean(waiting, root=None):
    root = root or ROOT
    path = os.path.join(root, "reports", "pending_dean.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    original = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    prev = re.sub(r"(?s)\n*<!-- %s -->.*?<!-- /%s -->\n*" % (re.escape(TAG), re.escape(TAG)), "\n", original).rstrip("\n")
    lines = pending_lines(waiting)
    if not lines:
        text = (prev + "\n") if prev.strip() else ""
    else:
        body = [
            "<!-- %s -->" % TAG,
            "## Emergency shelter switch-ons (waiting for Dean)",
            "",
            "Council pages say these are ON. They are not on the map until you OK them. A GitHub issue was also opened for each switch-on.",
            "",
        ]
        body.extend(lines)
        body.append("<!-- /%s -->" % TAG)
        base = prev if prev.strip() else "# Pending for Dean"
        text = base + "\n\n" + "\n".join(body) + "\n"
    if text != original:
        open(path, "w", encoding="utf-8").write(text)


def open_activation(act, detected_at=None):
    import alert
    loc = act.get("location") or ""
    body = "\n".join(
        [
            f"**Council:** {act['council']}",
            f"**Shelter / centre:** {act['label']}" + (f" ({loc})" if loc else ""),
            f"**Council wording (excerpt):** “{act.get('quote') or ''}”",
            f"**Source:** {act.get('url') or ''}",
        ]
    )
    if detected_at:
        body += f"\n**Detected (UK):** {detected_at:%d %b %Y %H:%M %Z}"
    alert.switch_on_open(act["council"], act["label"], body)


def close_activation(council, label, comment=None):
    import alert
    comment = comment or f"Emergency shelter switched OFF (no longer active on the council page). {RUN}"
    alert.switch_on_close(council, label, comment)


def transitions(prev_pages, new_pages, run_day=None):
    if not prev_pages:
        return [], []
    prev = merge_pages(prev_pages, run_day)
    new = merge_pages(new_pages, run_day)
    on = [act for key, act in new.items() if key not in prev]
    off = [act for key, act in prev.items() if key not in new]
    return on, off


def apply(prev_pages, new_pages, run_day=None, root=None, detected_at=None):
    root = root or os.getcwd()
    try:
        on, off = transitions(prev_pages, new_pages, run_day)
        state = load_state(os.path.join(root, STATE))
        waiting = state.get("waiting") or {}
        for act in on:
            key = f"{act['council']}|{act['label']}"
            open_activation(act, detected_at=detected_at)
            waiting[key] = act
        for act in off:
            key = f"{act['council']}|{act['label']}"
            close_activation(act["council"], act["label"])
            waiting.pop(key, None)
        state["waiting"] = waiting
        state["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        save_state(state, os.path.join(root, STATE))
        sync_pending_dean(waiting, root=root)
        return {"opened": len(on), "closed": len(off), "waiting": len(waiting)}
    except Exception as e:
        print(f"emergency_switch_on (non-fatal): {type(e).__name__}: {e}", file=sys.stderr)
        return {"error": str(e)}


def enrich_page(page, visible_text, run_day=None):
    page["_text"] = visible_text
    rc = rest_centre_activation(visible_text, page.get("council") or "", page.get("url") or "")
    if rc:
        page["rest_centre"] = {
            "active": True,
            "name": rc["label"],
            "quote": rc["quote"],
            "location": rc.get("location") or "",
        }
    else:
        page["rest_centre"] = None
    return page
