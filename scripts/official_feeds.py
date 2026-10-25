"""Flag a new link on a host we already treat as an official source. Never fetch it and never add a place."""
import json, os, re, urllib.parse
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CFG = os.path.join(ROOT, "overrides", "official_feeds.json")
OUT = os.path.join(ROOT, "reports", "new_official_feeds.json")
LINK = re.compile(r"https?://[^\s<>\"']+")

def _host(url):
    return urllib.parse.urlparse(url or "").netloc.lower().removeprefix("www.")

def new_in(text, known, hosts):
    """URLs in `text` whose host is listed and which are not already known. The page is not stored."""
    known_set = {(u or "").rstrip("/") for u in (known or [])}
    allowed = [h.lower().removeprefix("www.") for h in (hosts or []) if h]
    found = []
    for raw in LINK.findall(text or ""):
        u = raw.rstrip(".,;)")
        host = _host(u)
        if not host or not any(host == h or host.endswith("." + h) for h in allowed): continue
        if u.rstrip("/") in known_set: continue
        if u not in found: found.append(u)
    return found

def load(path=None):
    try: cfg = json.load(open(path or CFG, encoding="utf-8"))
    except Exception: return None
    if not isinstance(cfg, dict): return None
    return cfg

def scan(text, path=None):
    """No config file: no links. Nothing is invented and nothing is fetched."""
    cfg = load(path)
    if not cfg: return []
    return new_in(text, cfg.get("known") or [], cfg.get("hosts") or [])

def write(urls, path=None):
    path = path or OUT
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump({"urls": list(urls or []), "added": False}, open(tmp, "w"), indent=0, sort_keys=True)
    os.replace(tmp, path)
