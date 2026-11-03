"""One summary email when a refresh or watch run puts a new place on the map.

The only address this script will ever mail is help@helpmap.uk. The email folder
holds the signature logo (email/logo.png) and does not name another inbox.
HANDOFF-209 does not name one either. There is no recipient argument, and an
environment variable cannot change the address.

A place counts as new when its id is in the published file at HEAD and was not
in that file at the baseline commit the run started from (the map that was
already live). Food banks, warm spaces and shelters come from their layer
files, including a SWEP shelter the watch has published into shelters.js.
Incident rest centres come from incident_rest_centre_live.json, and only while
that file is public. Nothing is sent when that diff is empty.

Sending uses Brevo's transactional API (POST https://api.brevo.com/v3/smtp/email).
The key is the repository secret BREVO_API_KEY. Without --send this is a dry
run: it prints the summary and does not contact Brevo.
"""
import argparse, json, os, re, subprocess, sys, urllib.error, urllib.parse, urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RECIPIENT = "help@helpmap.uk"
SITE = "https://helpmap.uk"
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
API_KEY_ENV = "BREVO_API_KEY"

FILES = {
    "foodbanks": "data.full.js",
    "warmspaces": "warmspaces.js",
    "shelters": "shelters.js",
    "emergency": "incident_rest_centre_live.json",
}
TYPE_LABELS = {
    "foodbanks": "Food bank",
    "warmspaces": "Warm space",
    "shelters": "Shelter",
    "emergency": "Emergency provision",
}
LAYER_QUERY = {"warmspaces": "ws=1", "shelters": "sh=1"}
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PC = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)
_LAD_CODE = re.compile(r"^[A-Z]\d{8}$")


class MailError(Exception):
    pass


def plain(value):
    """Visible text with any address removed, so the message cannot name another inbox."""
    text = _EMAIL.sub("", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" ,;:-")
    return text


def norm_pc(pc):
    m = _PC.search(pc or "")
    if not m:
        return ""
    return (m.group(1) + " " + m.group(2)).upper()


def postcode_of(item):
    pc = norm_pc(item.get("postcode") or "")
    if pc:
        return pc
    return norm_pc(item.get("address") or "") or norm_pc(item.get("location") or "")


def town_of(item, districts):
    for key in ("town", "area"):
        text = plain(item.get(key))
        if text:
            return text
    lad = plain(item.get("lad"))
    if lad and not _LAD_CODE.match(lad):
        return lad
    pc = postcode_of(item)
    if pc and districts.get(pc):
        return plain(districts[pc]) or pc
    for key in ("council", "opened_by"):
        text = plain(item.get(key))
        if text and not _LAD_CODE.match(text):
            return text
    address = plain(item.get("address"))
    if address:
        parts = [p.strip() for p in _PC.sub("", address).split(",") if p.strip()]
        if parts:
            return parts[-1]
    return pc or "not stated"


def type_label(item, layer):
    cat = str(item.get("category") or "").lower()
    kind = str(item.get("kind") or "").lower()
    if cat == "swep" or kind == "swep" or item.get("swep_badge"):
        return "SWEP"
    if layer == "emergency" or cat == "incident_rest_centre":
        return "Emergency provision"
    return TYPE_LABELS[layer]


def on_map(item, layer):
    if not isinstance(item, dict) or item.get("flag_closed") or item.get("example"):
        return False
    if layer == "emergency" and item.get("live") is False:
        return False
    return bool(plain(item.get("name")))


def place_id(item, layer):
    if item.get("id"):
        return str(item["id"])
    return "|".join([
        layer,
        plain(item.get("name")).lower(),
        plain(item.get("source_url") or item.get("url")),
        plain(item.get("council") or item.get("opened_by")).lower(),
    ])


def map_link(postcode, town, layer):
    q = postcode or (town if town and town != "not stated" else "")
    parts = []
    if q:
        parts.append("q=" + urllib.parse.quote(q))
    extra = LAYER_QUERY.get(layer)
    if extra:
        parts.append(extra)
    return SITE + ("/?" + "&".join(parts) if parts else "/")


def newly_live(current, previous, layer, districts):
    """Places in current whose id was not published in previous."""
    prev = {place_id(i, layer) for i in previous or [] if isinstance(i, dict)}
    seen, out = set(), []
    for item in current or []:
        if not on_map(item, layer):
            continue
        pid = place_id(item, layer)
        if not pid or pid in prev or pid in seen:
            continue
        seen.add(pid)
        town = town_of(item, districts or {})
        pc = postcode_of(item)
        out.append({
            "id": pid,
            "name": plain(item.get("name")) or "Unnamed place",
            "type": type_label(item, layer),
            "town": town,
            "postcode": pc,
            "layer": layer,
            "link": map_link(pc, town, layer),
        })
    out.sort(key=lambda p: (p["type"], p["town"].lower(), p["name"].lower(), p["id"]))
    return out


def _json_body(text):
    text = (text or "").strip().lstrip("\ufeff")
    if not text:
        return None
    if not text.startswith("{") and not text.startswith("["):
        eq = text.find("=")
        if eq < 0:
            return None
        text = text[eq + 1:].strip()
    if text.endswith(";"):
        text = text[:-1].strip()
    return json.loads(text)


def parse_layer(text, layer):
    try:
        data = _json_body(text)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    if layer == "emergency":
        if not data.get("public"):
            return []
        return [c for c in (data.get("cards") or []) if isinstance(c, dict)]
    return [i for i in (data.get("items") or []) if isinstance(i, dict)]


def load_districts(root):
    path = os.path.join(root, "overrides", "district_cache.json")
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {norm_pc(k) or k: v for k, v in raw.items() if isinstance(k, str) and not k.startswith("_") and isinstance(v, str)}


def verify_ref(root, ref):
    r = subprocess.run(["git", "-C", root, "rev-parse", "--verify", "--quiet", ref + "^{commit}"], capture_output=True)
    if r.returncode != 0:
        raise MailError("baseline %s is not a commit" % ref)


def git_file(root, ref, rel):
    r = subprocess.run(["git", "-C", root, "show", "%s:%s" % (ref, rel)], capture_output=True)
    if r.returncode == 0:
        return r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace").lower()
    if "does not exist" in err or "exists on disk" in err or "not in" in err:
        return ""
    raise MailError("could not read %s at %s" % (rel, ref))


def collect(root, baseline, layers):
    if not baseline:
        raise MailError("no baseline commit")
    verify_ref(root, baseline)
    verify_ref(root, "HEAD")
    districts = load_districts(root)
    places = []
    for layer in layers:
        rel = FILES[layer]
        # An unreadable previous file must not look like an empty map, or one run would
        # mail every place already on it.
        raw_prev = git_file(root, baseline, rel)
        if not raw_prev.strip():
            raise MailError("no previous %s at the baseline; no email sent" % rel)
        current = parse_layer(git_file(root, "HEAD", rel), layer)
        previous = parse_layer(raw_prev, layer)
        places.extend(newly_live(current, previous, layer, districts))
    places.sort(key=lambda p: (p["type"], p["town"].lower(), p["name"].lower(), p["id"]))
    return places


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def compose(places):
    n = len(places)
    noun = "place" if n == 1 else "places"
    wf = plain(os.environ.get("GITHUB_WORKFLOW")) or "A refresh"
    if wf == "A refresh":
        lead = "A refresh put %d new %s on the helpmap.uk map." % (n, noun)
    else:
        lead = "%s put %d new %s on the helpmap.uk map." % (wf, n, noun)
    lines = [lead, ""]
    html = ["<p>%s</p>" % _esc(lead), "<ul>"]
    for p in places:
        lines.append("%s" % p["name"])
        lines.append("Type: %s" % p["type"])
        lines.append("Town: %s" % p["town"])
        lines.append("Map: %s" % p["link"])
        lines.append("")
        html.append(
            "<li><strong>%s</strong><br>Type: %s<br>Town: %s<br>Map: <a href=\"%s\">%s</a></li>"
            % (_esc(p["name"]), _esc(p["type"]), _esc(p["town"]), _esc(p["link"]), _esc(p["link"]))
        )
    html.append("</ul>")
    run = ""
    server, repo, rid = os.environ.get("GITHUB_SERVER_URL"), os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    if server and repo and rid:
        run = "%s/%s/actions/runs/%s" % (server.rstrip("/"), repo, rid)
        lines += ["Run: " + run, ""]
        html.append("<p>Run: <a href=\"%s\">%s</a></p>" % (_esc(run), _esc(run)))
    text = "\n".join(lines).rstrip() + "\n"
    message = {
        "subject": "New on the helpmap.uk map: %d %s" % (n, noun),
        "text": text,
        "html": "\n".join(html),
    }
    found = _EMAIL.findall(message["subject"] + "\n" + message["text"] + "\n" + message["html"])
    if found:
        raise MailError("summary named an address and was not sent")
    return message


def payload(message):
    """Brevo body. The to and sender addresses are the help address and nothing else."""
    body = {
        "sender": {"name": "helpmap.uk", "email": RECIPIENT},
        "to": [{"email": RECIPIENT, "name": "helpmap.uk"}],
        "subject": message["subject"],
        "textContent": message["text"],
        "htmlContent": message["html"],
    }
    found = set(_EMAIL.findall(json.dumps(body)))
    if found != {RECIPIENT}:
        raise MailError("refusing to send: the message is not addressed only to the help address")
    return body


def brevo_send(message, api_key, opener=None):
    if not api_key or not str(api_key).strip():
        raise MailError("BREVO_API_KEY is not set")
    body = payload(message)
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        BREVO_URL,
        data=raw,
        headers={"api-key": str(api_key).strip(), "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = opener or urllib.request.urlopen
    try:
        with opener(req, timeout=30) as resp:
            resp.read()
            code = getattr(resp, "status", None) or resp.getcode()
    except urllib.error.HTTPError as e:
        raise MailError("Brevo refused the email (HTTP %s)" % e.code)
    except MailError:
        raise
    except Exception as e:
        raise MailError("Brevo could not be reached (%s)" % type(e).__name__)
    if code and int(code) >= 300:
        raise MailError("Brevo refused the email (HTTP %s)" % code)
    return code


def deliver(places, send=False, api_key=None, opener=None):
    """Send one summary, or nothing. send=False is the dry run and never calls opener."""
    if not places:
        print("No new place went live. No email sent.")
        return {"sent": False, "reason": "nothing-new", "places": []}
    message = compose(places)
    if not send:
        print("DRY RUN. No email sent.")
        print("To: %s" % RECIPIENT)
        print("Subject: %s" % message["subject"])
        print(message["text"], end="")
        return {"sent": False, "reason": "dry-run", "message": message, "places": places}
    key = api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")
    if not str(key or "").strip():
        print("::error::BREVO_API_KEY is not set, so the new-place email was not sent.")
        return {"sent": False, "reason": "no-key", "places": places, "message": message}
    brevo_send(message, key, opener=opener)
    print("Sent one summary to %s (%d)." % (RECIPIENT, len(places)))
    return {"sent": True, "reason": "sent", "places": places, "message": message}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Email help@helpmap.uk when new places went live.")
    parser.add_argument("--layers", required=True, help="comma-separated: foodbanks,warmspaces,shelters,emergency")
    parser.add_argument("--baseline", default="", help="commit that was already live at the start of this run")
    parser.add_argument("--send", action="store_true", help="post the summary to Brevo; omitted, this is a dry run")
    parser.add_argument("--root", default=ROOT)
    args = parser.parse_args(argv)
    layers = [x.strip() for x in args.layers.split(",") if x.strip()]
    unknown = [x for x in layers if x not in FILES]
    if unknown or not layers:
        print("::error::unknown layer %s" % ",".join(unknown or ["(none)"]), file=sys.stderr)
        return 2
    if not args.baseline:
        print("No baseline commit. No email sent.")
        return 0
    try:
        places = collect(args.root, args.baseline, layers)
        result = deliver(places, send=args.send)
    except MailError as e:
        print("::error::%s" % e, file=sys.stderr)
        return 1
    if result.get("reason") == "no-key":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
