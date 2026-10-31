"""Notify Dean when a council incident rest centre or SWEP page switches on.

Uses scripts/alert.py (label rest-centre-switch-on). Separate from digest weather alerts (key weather).
Never blocks the refresh."""
import datetime, json, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TAG = "rest centre switch-on"
STATE = "logs/incident_rest_centre_switch_state.json"
RUN = f"{os.environ.get('GITHUB_SERVER_URL','https://github.com')}/{os.environ.get('GITHUB_REPOSITORY','')}/actions/runs/{os.environ.get('GITHUB_RUN_ID','')}"

SWEP_LABEL = "Severe weather shelter (SWEP)"
INCIDENT_LABEL = "Rest centres (incidents)"


def _quote_excerpt(quote, limit=320):
    q = re.sub(r"\s+", " ", quote or "").strip()
    return q[:limit] + ("…" if len(q) > limit else "")


def _location(text):
    import rest_centre_scan as rcs
    return rcs.extract_postcode(text)


def _alert_label(kind):
    return SWEP_LABEL if kind == "swep" else INCIDENT_LABEL


def rest_centre_activation(text, council, url):
    """Return an activation dict if visible text says a rest centre is open."""
    import rest_centre_scan as rcs
    if rcs.is_planning_page(text, url):
        return None
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
            "category_label": INCIDENT_LABEL,
        }
    if not rcs.rest_centre_on(text):
        return None
    q = _quote_excerpt(text)
    return {
        "kind": "rest_centre",
        "label": "Rest centre",
        "quote": q,
        "url": url,
        "location": _location(text),
        "category_label": INCIDENT_LABEL,
    }


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
            "category_label": SWEP_LABEL,
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
            "category_label": INCIDENT_LABEL,
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
        cat = w.get("category_label") or _alert_label(w.get("kind"))
        lines.append(
            f"- **{w['council']}** — [{cat}] {w['label']}{loc} — {w.get('url') or ''} — “{_quote_excerpt(w.get('quote',''), 160)}”"
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
            "## Rest centre and SWEP switch-ons (waiting for Dean)",
            "",
            "Council pages say these are ON. Incident rest centres go live when overrides/incident_rest_centre_mode.json has public true. A GitHub issue was also opened for each switch-on.",
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
    cat = act.get("category_label") or _alert_label(act.get("kind"))
    body = "\n".join(
        [
            f"**Category:** {cat}",
            f"**Council:** {act['council']}",
            f"**Place:** {act['label']}" + (f" ({loc})" if loc else ""),
            f"**Council wording (excerpt):** “{act.get('quote') or ''}”",
            f"**Source:** {act.get('url') or ''}",
        ]
    )
    if detected_at:
        body += f"\n**Detected (UK):** {detected_at:%d %b %Y %H:%M %Z}"
    alert.switch_on_open(act["council"], act["label"], body, category=cat)


def close_activation(council, label, comment=None, category=None):
    import alert
    comment = comment or f"Switch-off: no longer active on the council page. {RUN}"
    alert.switch_on_close(council, label, comment, category=category)


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
            close_activation(act["council"], act["label"], category=act.get("category_label"))
            waiting.pop(key, None)
        state["waiting"] = waiting
        state["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        save_state(state, os.path.join(root, STATE))
        sync_pending_dean(waiting, root=root)
        try:
            import incident_rest_centre_live as live
            pages = []
            for p in new_pages or []:
                pages.append(dict(p))
            live.sync_from_pages(pages, root=root, now=detected_at or datetime.datetime.now(datetime.timezone.utc))
        except Exception as e:
            print(f"incident_rest_centre_live (non-fatal): {type(e).__name__}: {e}", file=sys.stderr)
        return {"opened": len(on), "closed": len(off), "waiting": len(waiting)}
    except Exception as e:
        print(f"incident_rest_centre_switch_on (non-fatal): {type(e).__name__}: {e}", file=sys.stderr)
        return {"error": str(e)}


def enrich_page(page, visible_text, run_day=None):
    import rest_centre_scan as rcs
    page["_text"] = visible_text
    url = page.get("url") or ""
    if rcs.is_planning_page(visible_text, url):
        page["rest_centre"] = None
        return page
    rc = rest_centre_activation(visible_text, page.get("council") or "", url)
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
