"""Build and check the frozen phone baseline.

  python3 scripts/phone_baseline.py generate

Writes overrides/phone_baseline.json from the published listings plus the
contact overrides (the verified corrections). Run this again after the reviewed
batch 2 combine (PRs 207 and 208) so those reviewed council-number changes
become the freeze and are not held. That includes Perth, Redbridge, Runnymede,
Trafford, Kingston, Birmingham and Bolton.

  python3 scripts/phone_baseline.py compare origin/batch-2a-listings origin/batch-2b-content

Lists contact numbers on this checkout that differ from those branches.
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phone_lock
ROOT = phone_lock.ROOT
ABOUT = (
    "Frozen listing phone numbers, keyed by id (Dean, 27 Oct 2026). "
    "Automatic jobs must not change them; a different number is held for Dean. "
    "Hand edits belong in this file, in a reviewed PR. "
    "Regenerate: python3 scripts/phone_baseline.py generate. "
    "After the reviewed batch 2 combine (PRs 207 and 208), run generate again so the reviewed "
    "council-number changes are the new freeze and are not held "
    "(Perth, Redbridge, Runnymede, Trafford, Kingston, Birmingham, Bolton). "
    "Compare with batch 2: python3 scripts/phone_baseline.py compare origin/batch-2a-listings origin/batch-2b-content."
)
CONTACTS = (
    ("shelters", "shelters.js", "overrides/shelters_contacts.json"),
    ("warmspaces", "warmspaces.js", "overrides/warmspaces_contacts.json"),
)
NUMBER_KEYS = ("phone", "phone_fix", "council_phone", "council_ooh", "council_label", "council_label_cy")

def _js(path):
    t = open(path, encoding="utf-8").read()
    return json.loads(t[t.index("{"):t.rindex("}") + 1])

def generate(root=None):
    """Published numbers, then the contact overrides. Council lines are the published bytes."""
    root = root or ROOT
    import shelter_contacts
    listings = {}
    fb = _js(os.path.join(root, "data.full.js"))
    for it in fb["items"]:
        if it.get("id"):
            listings[it["id"]] = phone_lock.snap(it, "foodbanks")
    for layer, fn, contacts in CONTACTS:
        d = _js(os.path.join(root, fn))
        live = phone_lock.live_council(d["items"])  # council lines are frozen as published, never derived
        shelter_contacts.apply(d["items"], shelter_contacts.load(os.path.join(root, contacts)))
        for it in d["items"]:
            if it.get("id"):
                for k in phone_lock.COUNCIL_FIELDS:
                    it.pop(k, None)
                it.update(live.get(it["id"], {}))
                listings[it["id"]] = phone_lock.snap(it, layer)
    overlap = set()
    # food-bank ids replaced by a shelter/warm-space id would hide a frozen food-bank number
    fb_ids = {it["id"] for it in fb["items"] if it.get("id")}
    for layer, fn, _c in CONTACTS:
        d = _js(os.path.join(root, fn))
        overlap |= fb_ids & {it.get("id") for it in d["items"]}
    if overlap:
        raise SystemExit("listing id used on two layers: " + ", ".join(sorted(overlap)[:10]))
    data = {"_about": ABOUT, "listings": {k: listings[k] for k in sorted(listings)}}
    phone_lock.save(data, root)
    return len(listings)

def _contact_map(data):
    out = {}
    if not isinstance(data, dict):
        return out
    for k, v in data.items():
        if k == "_councils" and isinstance(v, dict):
            for area, c in v.items():
                if isinstance(c, dict):
                    rec = {f: c[f] for f in NUMBER_KEYS if isinstance(c.get(f), str)}
                    if rec:
                        out["area:" + area] = rec
            continue
        if not isinstance(v, dict) or str(k).startswith("_"):
            continue
        rec = {f: v[f] for f in NUMBER_KEYS if isinstance(v.get(f), str)}
        if rec:
            out[k] = rec
    return out

def diff_maps(ours, theirs, ref):
    """Rows where a contact number or label differs. Blank sides are shown."""
    rows = []
    for iid in sorted(set(ours) | set(theirs)):
        a, b = ours.get(iid) or {}, theirs.get(iid) or {}
        for field in sorted(set(a) | set(b)):
            if a.get(field) != b.get(field):
                rows.append((iid, field, a.get(field) or "", b.get(field) or "", ref))
    return rows

def load_contacts(root):
    merged = {}
    for _layer, _fn, rel in CONTACTS:
        merged.update(_contact_map(json.load(open(os.path.join(root, rel), encoding="utf-8"))))
    return merged

def git_contacts(ref, root=None):
    root = root or ROOT
    merged = {}
    for _layer, _fn, rel in CONTACTS:
        raw = subprocess.check_output(["git", "show", "%s:%s" % (ref, rel)], cwd=root, text=True)
        merged.update(_contact_map(json.loads(raw)))
    return merged

def compare(refs, root=None):
    root = root or ROOT
    ours = load_contacts(root)
    rows = []
    for ref in refs:
        rows += diff_maps(ours, git_contacts(ref, root), ref)
    return rows

def project_council(entry):
    """Council line a place override sets, byte for byte (nothing copied between fields)."""
    return {k: entry[k] for k in phone_lock.COUNCIL_FIELDS if isinstance(entry.get(k), str) and entry[k].strip()}

def unreviewed(root=None):
    """Place-level council lines that are not the reviewed baseline bytes.
    A hand edit passes once the baseline records the same bytes."""
    root = root or ROOT
    data = phone_lock.load(root)
    if not data:
        return ["no baseline"]
    listings = data["listings"]
    diffs = []
    for _layer, _fn, rel in CONTACTS:
        raw = json.load(open(os.path.join(root, rel), encoding="utf-8"))
        for iid, entry in raw.items():
            if not isinstance(entry, dict) or str(iid).startswith("_"):
                continue
            if not any(isinstance(entry.get(k), str) for k in phone_lock.COUNCIL_FIELDS):
                continue
            if iid not in listings:
                diffs.append((iid, "(missing from baseline)", "", ""))
                continue
            projected = project_council(entry)
            frozen = listings[iid]
            fields = set(projected) | {k for k in phone_lock.COUNCIL_FIELDS if k in entry and k in frozen}
            for field in sorted(fields):
                if projected.get(field, "") != frozen.get(field, ""):
                    diffs.append((iid, field, projected.get(field, ""), frozen.get(field, "")))
    return diffs

def main(argv):
    cmd = argv[1] if len(argv) > 1 else "generate"
    if cmd == "generate":
        n = generate()
        print("phone baseline: %d listings -> %s" % (n, phone_lock.baseline_path()))
        return 0
    if cmd == "compare":
        refs = argv[2:] or ["origin/batch-2a-listings", "origin/batch-2b-content"]
        rows = compare(refs)
        if not rows:
            print("no contact-number differences")
            return 0
        for iid, field, ours, theirs, ref in rows:
            print("%s %s ours=%r %s=%r" % (iid, field, ours, ref, theirs))
        print("%d differences" % len(rows))
        return 0
    print(__doc__)
    return 2

if __name__ == "__main__":
    sys.exit(main(sys.argv))
