"""Stop a publish when a hand file is broken or suddenly much smaller. Dean confirms a real shrink."""
import json, os
FILES = ("overrides/phones.json", "overrides/foodbank_notices.json", "overrides/foodbank_closed.json")

def count_keys(text):
    try: data = json.loads(text)
    except Exception: return None
    if isinstance(data, dict): return len([k for k in data if not str(k).startswith("_")])
    if isinstance(data, list): return len(data)
    return None

def decide(keys, previous, confirmed):
    """previous None: first sight, accept and record. A shrink below half is held unless Dean confirmed that size."""
    if keys is None: return False, "not valid JSON - held for Dean"
    if previous is None: return True, "first count recorded"
    if keys >= previous * 0.5: return True, "ok"
    if confirmed is not None and keys >= int(confirmed): return True, "shrink confirmed by Dean"
    return False, "shrank from %d keys to %d - held for Dean" % (previous, keys)

def assess(root):
    """True means the publish may continue. A missing hand file is skipped. The map is not edited here."""
    sizes_path = os.path.join(root, "reports", "override_sizes.json")
    try: sizes = json.load(open(sizes_path))
    except Exception: sizes = {}
    try: confirmed = json.load(open(os.path.join(root, "overrides", "shrink_ok.json")))
    except Exception: confirmed = {}
    if not isinstance(sizes, dict): sizes = {}
    if not isinstance(confirmed, dict): confirmed = {}
    nxt, held, reasons = dict(sizes), [], []
    for rel in FILES:
        path = os.path.join(root, rel)
        if not os.path.exists(path): continue
        keys = count_keys(open(path, encoding="utf-8").read())
        ok, reason = decide(keys, sizes.get(rel), confirmed.get(rel))
        if not ok: held.append("%s: %s" % (rel, reason))
        else:
            reasons.append(reason)
            if keys is not None: nxt[rel] = keys
    if held:
        os.makedirs(os.path.join(root, "reports"), exist_ok=True)
        open(os.path.join(root, "reports", "override_check.md"), "w", encoding="utf-8").write("# Hand files held\n\n" + "\n".join("- " + h for h in held) + "\n\nNothing was published from this check.\n")
        return False, "; ".join(held)
    if nxt != sizes:
        os.makedirs(os.path.join(root, "reports"), exist_ok=True)
        tmp = sizes_path + ".tmp"
        json.dump(nxt, open(tmp, "w"), indent=0, sort_keys=True); os.replace(tmp, sizes_path)
    return True, "; ".join(reasons) or "ok"
