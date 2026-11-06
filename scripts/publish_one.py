#!/usr/bin/env python3
"""Add or edit one food bank, shelter, or warm space without rebuilding the layer.

The card is rebuilt with the same per-id helpers the full builders already use
(overlay apply, classify.classify, place_facts.stamp, place_lock, phone_lock,
hours normalise). Only that id is written back. Scheduled full refreshes are
not called from here.

Field values come from overlay files in the repo. A new food bank is that id's
Give Food/IFAN record already on disk (foodbank_added / foodbank_approved_new,
inserted by classify) plus overlays. Its phone comes from the verified phone
overlay (phone_rule.phones_to_apply), never from a Give Food number.
"""
import argparse
import copy
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import auto_rules
import compact
import phone_lock
import phone_rule
import place_facts
import place_lock
import stamp

ROOT_DEFAULT = os.path.dirname(SCRIPTS_DIR)
LAYER_NAMES = ("foodbanks", "shelters", "warmspaces")
FILES = {
    "foodbanks": ("data.full.js", "data.js"),
    "shelters": ("shelters.js",),
    "warmspaces": ("warmspaces.js",),
}
STAMP_KIND = {"foodbanks": "refresh", "shelters": "shelters", "warmspaces": "warmspaces"}
STAMP_KEY = {"refresh": "fb", "shelters": "sh", "warmspaces": "ws"}

# Simple id-keyed overlays. A change to one of these keys is that listing.
DICT_OVERLAYS = {
    "foodbank_added.json": "foodbanks",
    "foodbank_address_fixes.json": "foodbanks",
    "foodbank_approved_new.json": "foodbanks",
    "foodbank_checks.json": "foodbanks",
    "foodbank_closed.json": "foodbanks",
    "foodbank_extra_locations.json": "foodbanks",
    "foodbank_manual.json": "foodbanks",
    "foodbank_names.json": "foodbanks",
    "foodbank_notices.json": "foodbanks",
    "foodbank_own_pages.json": "foodbanks",
    "opening_times.json": "foodbanks",
    "phones.json": "foodbanks",
    "phone_sources.json": "foodbanks",
    "phone_labels.json": "foodbanks",
    "phone_holds.json": "foodbanks",
    "facebook_pages.json": "foodbanks",
    "shelters_contacts.json": "shelters",
    "shelters_unverified.json": "shelters",
    "shelters_verified.json": "shelters",
    "warmspaces_contacts.json": "warmspaces",
    "warmspaces_unverified.json": "warmspaces",
    "warmspaces_verified.json": "warmspaces",
}
LIST_OVERLAYS = {
    "shelters_manual.json": "shelters",
    "warmspaces_exclude.json": "warmspaces",
    "warmspaces_fixes.json": "warmspaces",
    "warmspaces_manual.json": "warmspaces",
}
# Not a one-listing edit. SWEP and rest centres stay on their own workflows.
NON_LISTING = {
    "page_dates.json", "district_cache.json",
    "auto_apply_rules.json", "known_gaps.json", "known_sources.json",
    "never_publish.json", "official_feeds.json",
    "discovery_hold.json", "show_all_closed.json", "sweep_exclude.json",
    "incident_rest_centre_mode.json", "rest_centre_sources.json",
    "swep_handcheck.json", "swep_seasonal.json", "swep_sources.json",
}
REFRESH_EXACT = {
    "data.js", "data.full.js", "shelters.js", "warmspaces.js", "stamp.js",
    "index.html", "version.json", "sitemap.xml", "robots.txt", "404.html",
    "accessibility.html", "faq.html", "terms.html", "privacy.html",
}
REFRESH_PREFIXES = ("logs/", "reports/", "food-banks/", "warm-spaces/", "shelters/", "docs/", "export/")
COMMENT_KEYS = {"_about", "_comment", "_note"}
VERIFIED_KEYS = (
    "phone", "address", "access", "postcode", "lat", "lng", "hours",
    "evidence_name", "scheme_start", "scheme_end", "scheme_dates",
)
_STREET = re.compile(
    r"\b(street|st|road|rd|avenue|ave|lane|ln|drive|dr|way|close|crescent|cres|"
    r"terrace|gardens|grove|row|square|parade|walk|yard|mews|rise|broadway|"
    r"esplanade|quay|wharf|place)\b",
    re.I,
)
_BUILDING = re.compile(
    r"\b(house|hall|centre|center|building|flat|apartment|unit|court|lodge|"
    r"vicarage|cottage|chapel|church|school|library|block|mansion|chambers|"
    r"tower|farm|barn|suite|floor)\b",
    re.I,
)
_POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)


def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _stated(v):
    return v not in (None, "", [], {})


def _blank_loc(v):
    if v is None:
        return True
    return isinstance(v, str) and not v.strip()


def _norm_place(v):
    return re.sub(r"[^a-z0-9]+", " ", str(v or "").lower()).strip()


def parse_js_layer(text):
    start = text.index("{")
    end = text.rindex("}") + 1
    return text[:start], json.loads(text[start:end]), text[end:]


def read_layer(root, layer):
    path = os.path.join(root, FILES[layer][0])
    if not os.path.exists(path):
        raise FileNotFoundError("layer file not found: %s" % path)
    with open(path, encoding="utf-8") as f:
        return parse_js_layer(f.read())


def _git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)


def _show(root, rev, rel):
    r = _git(root, "show", "%s:%s" % (rev, rel))
    if r.returncode != 0:
        return None
    return r.stdout


def _parse_commit_json(text, expect, rel):
    if text is None or not str(text).strip():
        return {} if expect == "dict" else []
    try:
        data = json.loads(text)
    except Exception as e:
        raise RuntimeError("could not parse %s; listing id cannot be determined (%s)" % (rel, e)) from e
    return data


def _meta_ids(key, old_v, new_v, rel):
    """Id-bearing meta keys. Anything else that changed is not an exact listing id."""
    if old_v == new_v:
        return []
    if key in COMMENT_KEYS:
        return []
    if key == "_councils":
        raise RuntimeError("%s %s changed; listing ids cannot be determined exactly" % (rel, key))
    if key == "_remove_ids":
        old_ids = set(old_v or [])
        new_ids = set(new_v or [])
        if any(not isinstance(x, str) for x in old_ids | new_ids):
            raise RuntimeError("%s _remove_ids is not a list of listing ids" % rel)
        return sorted(old_ids ^ new_ids)
    raise RuntimeError("%s key %s changed and is not a listing id" % (rel, key))


def _changed_dict_ids(old, new, rel):
    if not isinstance(new, dict):
        raise RuntimeError("%s is not an id map; listing id cannot be determined" % rel)
    old = old if isinstance(old, dict) else {}
    ids = []
    keys = set(old) | set(new)
    for key in keys:
        if str(key).startswith("_"):
            ids.extend(_meta_ids(key, old.get(key), new.get(key), rel))
            continue
        if old.get(key) != new.get(key):
            ids.append(key)
    return ids


def _changed_list_ids(old, new, rel):
    if not isinstance(new, list):
        raise RuntimeError("%s is not a list of listings; listing id cannot be determined" % rel)
    if old is None:
        old = []
    if not isinstance(old, list):
        raise RuntimeError("%s changed shape; listing id cannot be determined" % rel)

    def index(rows):
        out = {}
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                raise RuntimeError("%s has an entry with no id; listing id cannot be determined" % rel)
            out[row["id"]] = row
        return out

    old_i, new_i = index(old), index(new)
    ids = [k for k in new_i if k not in old_i or old_i[k] != new_i[k]]
    ids.extend(k for k in old_i if k not in new_i)
    return ids


def _pairs_for(base, old_text, new_text, rel):
    if base == "approved_new_places.json":
        new = _parse_commit_json(new_text, "dict", rel)
        old = _parse_commit_json(old_text, "dict", rel)
        if not isinstance(new, dict) or not isinstance(old, dict):
            raise RuntimeError("%s is not the layer map; listing id cannot be determined" % rel)
        pairs = []
        for layer in LAYER_NAMES:
            ids = _changed_dict_ids(old.get(layer) or {}, new.get(layer) or {}, rel + ":" + layer)
            pairs.extend((layer, iid) for iid in ids)
        for key in set(old) | set(new):
            if key in LAYER_NAMES or str(key).startswith("_"):
                if str(key).startswith("_"):
                    _meta_ids(key, old.get(key), new.get(key), rel)
                continue
            if old.get(key) != new.get(key):
                raise RuntimeError("%s key %s is not a layer; listing id cannot be determined" % (rel, key))
        return pairs
    if base == "phone_baseline.json":
        new = _parse_commit_json(new_text, "dict", rel)
        old = _parse_commit_json(old_text, "dict", rel)
        if not isinstance(new, dict) or not isinstance(old, dict):
            raise RuntimeError("%s is not a phone baseline; listing id cannot be determined" % rel)
        pairs = []
        new_l = new.get("listings") if isinstance(new.get("listings"), dict) else {}
        old_l = old.get("listings") if isinstance(old.get("listings"), dict) else {}
        if "listings" in new and not isinstance(new.get("listings"), dict):
            raise RuntimeError("%s listings is not an id map" % rel)
        for iid in set(old_l) | set(new_l):
            if old_l.get(iid) == new_l.get(iid):
                continue
            rec = new_l.get(iid) if isinstance(new_l.get(iid), dict) else old_l.get(iid)
            layer = rec.get("layer") if isinstance(rec, dict) else None
            if layer not in LAYER_NAMES:
                raise RuntimeError("%s listing %s has no layer; refusing to guess a queue" % (rel, iid))
            pairs.append((layer, iid))
        for key in set(old) | set(new):
            if key in ("listings",) or str(key).startswith("_"):
                continue
            if old.get(key) != new.get(key):
                raise RuntimeError("%s key %s changed and its layer is not recorded; refusing to guess" % (rel, key))
        return pairs
    if base == "foodbank_exclude.json":
        def slugs(doc):
            if not isinstance(doc, dict):
                raise RuntimeError("%s is not an object" % rel)
            rows = doc.get("foodbanks") or []
            if not isinstance(rows, list):
                raise RuntimeError("%s foodbanks is not a list" % rel)
            out = {}
            for row in rows:
                if not isinstance(row, dict) or not row.get("slug"):
                    raise RuntimeError("%s entry has no slug; listing id cannot be determined" % rel)
                out[row["slug"]] = row
            return out
        new_s = slugs(_parse_commit_json(new_text, "dict", rel))
        old_s = slugs(_parse_commit_json(old_text, "dict", rel))
        return [("foodbanks", iid) for iid in sorted(set(old_s) | set(new_s)) if old_s.get(iid) != new_s.get(iid)]
    if base == "shelter_exclusions.json":
        new = _parse_commit_json(new_text, "dict", rel)
        old = _parse_commit_json(old_text, "dict", rel)
        if not isinstance(new, dict) or not isinstance(old, dict):
            raise RuntimeError("%s is not an object" % rel)
        new_ids = new.get("ids") if isinstance(new.get("ids"), dict) else {}
        old_ids = old.get("ids") if isinstance(old.get("ids"), dict) else {}
        if (new.get("ids") is not None and not isinstance(new.get("ids"), dict)) or (
            old.get("ids") is not None and not isinstance(old.get("ids"), dict)
        ):
            raise RuntimeError("%s ids is not an id map" % rel)
        pairs = [("shelters", iid) for iid in _changed_dict_ids(old_ids, new_ids, rel)]
        for key in set(old) | set(new):
            if key == "ids" or str(key).startswith("_"):
                if str(key).startswith("_"):
                    _meta_ids(key, old.get(key), new.get(key), rel)
                continue
            if old.get(key) != new.get(key):
                raise RuntimeError("%s key %s changed and is not a listing id" % (rel, key))
        return pairs
    if base == "man_google_handcheck.json":
        new = _parse_commit_json(new_text, "list", rel)
        old = _parse_commit_json(old_text, "list", rel)
        if not isinstance(new, list) or not isinstance(old, list):
            raise RuntimeError("%s is not a list of ids" % rel)
        if any(not isinstance(x, str) for x in list(old) + list(new)):
            raise RuntimeError("%s is not a list of listing ids" % rel)
        return [("shelters", iid) for iid in sorted(set(old) ^ set(new))]
    if base in DICT_OVERLAYS:
        new = _parse_commit_json(new_text, "dict", rel)
        old = _parse_commit_json(old_text, "dict", rel)
        return [(DICT_OVERLAYS[base], iid) for iid in _changed_dict_ids(old, new, rel)]
    if base in LIST_OVERLAYS:
        new = _parse_commit_json(new_text, "list", rel)
        old = _parse_commit_json(old_text, "list", rel)
        return [(LIST_OVERLAYS[base], iid) for iid in _changed_list_ids(old, new, rel)]
    raise RuntimeError("unknown overlay file %s; cannot determine target layer and listing id" % rel)


def _is_refresh_output(files):
    for rel in files:
        name = rel.strip()
        if name in REFRESH_EXACT or name.startswith(REFRESH_PREFIXES):
            return True
    return False


def detect_from_commit(root, commit="HEAD"):
    """(layer, id) pairs whose overlay keys changed in this commit.

    A refresh-output commit (published layer files, stamps, reports) returns
    nothing. An overlay whose listing id cannot be read exactly raises.
    Layer comes from the file's known role or from keys inside the file
    (approved_new_places, phone baseline), never from the letters in the path.
    """
    parent = "%s^" % commit
    if _git(root, "rev-parse", "--verify", "--quiet", parent).returncode != 0:
        raise RuntimeError("cannot determine the parent of %s; listing ids are not exact" % commit)
    diff = _git(root, "diff", "--name-only", parent, commit)
    if diff.returncode != 0:
        raise RuntimeError("git diff failed for %s: %s" % (commit, diff.stderr.strip()))
    files = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    if _is_refresh_output(files):
        return []
    pairs = []
    for rel in files:
        if not rel.startswith("overrides/") or not rel.endswith(".json"):
            continue
        base = os.path.basename(rel)
        if base in NON_LISTING:
            continue
        old_text = _show(root, parent, rel)
        new_text = _show(root, commit, rel)
        found = _pairs_for(base, old_text, new_text, rel)
        if not found and base not in NON_LISTING:
            # A comment-only edit has no listing id. A real edit that parsed to
            # nothing was already raised. Empty means this file did not change an id.
            pass
        pairs.extend(found)
    seen = set()
    out = []
    for layer, iid in sorted(pairs, key=lambda p: (LAYER_NAMES.index(p[0]), p[1])):
        if (layer, iid) in seen:
            continue
        seen.add((layer, iid))
        out.append((layer, iid))
    return out


def group_ids(pairs):
    out = {layer: [] for layer in LAYER_NAMES}
    for layer, iid in pairs:
        if iid not in out[layer]:
            out[layer].append(iid)
    return out


def is_street_address(addr, item):
    """True when a no-pin card's address is a street or a building, not a town line.

    Town and area text is allowed, including a comma ('Town, County') and a
    parenthetical note. A building name with no street word and no house
    number is still rejected.
    """
    raw = (addr or "").strip()
    if not raw:
        return False
    base = re.sub(r"\s*\([^)]*\)\s*", " ", raw)
    base = re.sub(r"\s+", " ", base).strip()
    paren = " ".join(re.findall(r"\(([^)]*)\)", raw))
    allowed = set()
    for key in ("town", "area"):
        n = _norm_place(item.get(key))
        if n:
            allowed.add(n)
    base_n = _norm_place(base)
    paren_bad = bool(re.search(r"\d", paren) or _STREET.search(paren) or _BUILDING.search(paren) or _POSTCODE.search(paren))
    if base_n and base_n in allowed and not paren_bad:
        return False
    bare_town = (
        not allowed
        and base
        and not paren_bad
        and not re.search(r"\d", raw)
        and "," not in base
        and not _STREET.search(raw)
        and not _BUILDING.search(raw)
        and not _POSTCODE.search(raw)
        and not base_n.startswith("the ")
    )
    if bare_town:
        words = [w for w in base_n.split() if w not in {"on", "upon", "under", "the", "and", "of", "le", "y"}]
        if 1 <= len(words) <= 4:
            return False
    return True


def location_problem(item):
    """Rules 55 and 94: a no-pin or referral-hostel card has no pin and no street."""
    if not (item.get("no_pin") or item.get("card_type") == "referral_hostel"):
        return None
    if not _blank_loc(item.get("lat")) or not _blank_loc(item.get("lng")):
        return "must not have lat/lng"
    postcode = item.get("postcode")
    if isinstance(postcode, str):
        postcode = postcode.strip()
    if postcode not in (None, ""):
        return "must not have postcode"
    if is_street_address(item.get("address") or "", item):
        return "street address not allowed: %s" % (item.get("address") or "")
    return None


def assert_no_pin(item, item_id):
    reason = location_problem(item)
    if reason:
        raise ValueError("Rejecting no_pin shelter %s: %s (rules 55 and 94)" % (item_id, reason))


def _overlay_overwrite(item, rec, skip=()):
    if not isinstance(rec, dict):
        return
    for key, value in rec.items():
        if key in skip or key == "id" or str(key).startswith("_"):
            continue
        if _stated(value):
            item[key] = copy.deepcopy(value)


def _foodbank_excluded(root, item):
    excl = _load(os.path.join(root, "overrides", "foodbank_exclude.json"), {}).get("foodbanks", [])
    host = (item.get("website") or "").split("//")[-1].split("/")[0].lower().removeprefix("www.")
    iid = item.get("id") or ""
    for entry in excl:
        if not isinstance(entry, dict):
            continue
        slug = entry.get("slug") or ""
        if iid == slug or (not entry.get("exact") and (iid.startswith(slug + "/") or (entry.get("host") and host == entry.get("host")))):
            return True
    return False


def _warm_excluded(root):
    rows = _load(os.path.join(root, "overrides", "warmspaces_exclude.json"), [])
    return {row.get("id") for row in rows if isinstance(row, dict) and row.get("id")}


def _fb_overlay(root):
    merged = {}
    base = os.path.join(root, "overrides")
    for name in ("foodbank_manual.json", "foodbank_added.json"):
        for key, value in _load(os.path.join(base, name), {}).items():
            if str(key).startswith("_") or not isinstance(value, dict):
                continue
            merged.setdefault(key, {}).update(value)
    return merged


def _apply_names(item, root):
    names = {
        k: v for k, v in _load(os.path.join(root, "overrides", "foodbank_names.json"), {}).items()
        if not str(k).startswith("_") and isinstance(v, dict)
    }
    chosen = names.get(item.get("id"))
    if not chosen:
        return
    for key in ("name", "foodbank"):
        if chosen.get(key):
            item[key] = chosen[key]


def _verified_phones(root):
    base = os.path.join(root, "overrides")
    phones = _load(os.path.join(base, "phones.json"), {})
    sources = _load(os.path.join(base, "phone_sources.json"), {})
    holds = _load(os.path.join(base, "phone_holds.json"), {})
    return phone_rule.phones_to_apply(phones, sources, holds), holds


def rebuild_foodbank(root, item_id, base_item, published_items, is_new, persist_new):
    """One food-bank card through classify, names, phones, place_facts, and the locks."""
    import classify
    from hours_fix import apply_phone
    import hours_norm
    from times import normalise

    work = copy.deepcopy(published_items)
    classify.classify(work, root)
    matches = [item for item in work if item.get("id") == item_id]
    if not matches:
        return None
    if len(matches) != 1:
        raise RuntimeError("classify produced more than one card for %s" % item_id)
    item = matches[0]
    _apply_names(item, root)
    times = _load(os.path.join(root, "overrides", "opening_times.json"), {})
    if isinstance(times, dict) and item_id in times and not str(item_id).startswith("_"):
        item["opening_times"] = normalise(times[item_id])
    manual = _load(os.path.join(root, "overrides", "foodbank_manual.json"), {})
    manual_rec = manual.get(item_id) if isinstance(manual.get(item_id), dict) else {}
    if manual_rec.get("drop_opening_times") and item.get("kind") in ("warehouse", "dropoff"):
        item["opening_times"] = None
    hours_norm.apply([item], "opening_times")
    phones, holds = _verified_phones(root)
    # The filtered overlay wins after classify, which would otherwise copy a
    # warehouse phone out of foodbank_manual.json.
    if item_id in phones:
        item["phone"] = phones[item_id]
        item["phone_checked"] = True
    elif is_new:
        item["phone"] = ""
        item["tel"] = ""
        item.pop("phone_checked", None)
    apply_phone(item)
    notices = _load(os.path.join(root, "overrides", "foodbank_notices.json"), {})
    notice = notices.get(item_id)
    if isinstance(notice, dict) and notice.get("notice"):
        item["notice"] = notice["notice"]
    pages = _load(os.path.join(root, "overrides", "facebook_pages.json"), {})
    page = pages.get(item_id)
    if isinstance(page, dict) and page.get("url"):
        item["fb_page"] = page["url"]
    labels = _load(os.path.join(root, "overrides", "phone_labels.json"), {})
    label = labels.get(item_id)
    if item.get("phone") and isinstance(label, str) and label.strip():
        item["phone_label"] = label.strip()
    phone_rule.suppress([item], holds)
    phone_lock.guard(
        [item], root, via="refresh", source="publish_one", layer="foodbanks",
        persist_new=persist_new, published=phone_lock.live_council(published_items),
    )
    apply_phone(item)
    place_lock.protect(
        [item], published_items, place_lock.hands(root, "foodbanks"), root, "foodbanks",
    )
    facts = _fb_overlay(root)
    src = facts.get(item_id) if isinstance(facts.get(item_id), dict) else {}
    # place_facts.stamp fills groups and referral only when the card lacks them.
    # Clear a stated overlay value first so an edit replaces a nonempty field.
    if src.get("groups"):
        item["groups"] = []
    referral = src.get("referral")
    if isinstance(referral, str) and referral.strip():
        item["referral"] = ""
    place_facts.stamp([item], facts, fill_missing=True)
    return item


def _reject_overlay_location(rec, base_item, item_id):
    if not isinstance(rec, dict):
        return
    probe = dict(base_item or {})
    probe.update({k: v for k, v in rec.items() if k != "id"})
    if probe.get("no_pin") or probe.get("card_type") == "referral_hostel":
        assert_no_pin(probe, item_id)


def rebuild_shelter(root, item_id, base_item, published_items, persist_new):
    import shelter_contacts
    from common import fill_referral_routes, infer_shelter_groups
    from hours_fix import apply_phone
    import hours_norm

    base = os.path.join(root, "overrides")
    manual_rows = _load(os.path.join(base, "shelters_manual.json"), [])
    manual = {row["id"]: row for row in manual_rows if isinstance(row, dict) and row.get("id")}
    verified = _load(os.path.join(base, "shelters_verified.json"), {})
    unverified = _load(os.path.join(base, "shelters_unverified.json"), {})
    _reject_overlay_location(manual.get(item_id), base_item, item_id)
    if isinstance(verified.get(item_id), dict):
        _reject_overlay_location(verified.get(item_id), base_item, item_id)
    item = copy.deepcopy(base_item) if base_item else {"id": item_id}
    item["id"] = item_id
    if item_id in manual:
        _overlay_overwrite(item, manual[item_id])
        item.setdefault("groups", [])
        item.setdefault("season", "Not stated")
    verified_rec = verified.get(item_id) if isinstance(verified.get(item_id), dict) else None
    if verified_rec:
        no_pin = item.get("no_pin") or item.get("card_type") == "referral_hostel"
        for key in VERIFIED_KEYS:
            if not verified_rec.get(key):
                continue
            if no_pin and key in ("lat", "lng", "postcode", "address"):
                continue
            item[key] = copy.deepcopy(verified_rec[key])
        if verified_rec.get("verified_on"):
            item["verified"] = True
            item["verified_on"] = verified_rec.get("verified_on", "")
            item["evidence_url"] = verified_rec.get("evidence_url", "")
            item["tier"] = "verified"
        if verified_rec.get("access_type"):
            item["access_type"] = verified_rec["access_type"]
        if verified_rec.get("phone_source"):
            item["phone_source"] = verified_rec["phone_source"]
        if verified_rec.get("phone_label"):
            item["phone_label"] = verified_rec["phone_label"]
        if verified_rec.get("groups"):
            item["groups"] = list(verified_rec["groups"])
            if verified_rec.get("groups_source"):
                item["groups_source"] = verified_rec["groups_source"]
        elif not item.get("groups"):
            inferred = infer_shelter_groups(item, verified_rec)
            if inferred:
                item["groups"] = inferred
                item["groups_source"] = verified_rec.get("evidence_url") or verified_rec.get("evidence_name") or ""
        if verified_rec.get("access"):
            item["referral"] = verified_rec["access"][0].upper() + verified_rec["access"][1:]
        place_facts.copy_wheelchair(item, verified_rec)
    unverified_rec = unverified.get(item_id) if isinstance(unverified.get(item_id), dict) else None
    if unverified_rec and not verified_rec:
        _overlay_overwrite(item, unverified_rec, skip=("sign_url",))
        if unverified_rec.get("sign_url"):
            item["tier"] = item.get("tier") or "unverified"
            item["sign_url"] = unverified_rec["sign_url"]
        place_facts.copy_wheelchair(item, unverified_rec)
    contacts = shelter_contacts.load(os.path.join(base, "shelters_contacts.json"))
    contact = contacts.get(item_id) if isinstance(contacts, dict) else None
    if isinstance(contact, dict):
        if _stated(contact.get("phone_fix")):
            item["phone"] = contact["phone_fix"]
        elif _stated(contact.get("phone")):
            item["phone"] = contact["phone"]
        if contact.get("groups"):
            item["groups"] = list(contact["groups"])
    shelter_contacts.apply([item], contacts)
    place_facts.stamp([item], manual)
    hours_norm.apply([item], "hours")
    apply_phone(item)
    phone_lock.settle_council(item)
    phone_lock.guard(
        [item], root, via="refresh", source="publish_one", layer="shelters",
        persist_new=persist_new, published=phone_lock.live_council(published_items),
    )
    apply_phone(item)
    assert_no_pin(item, item_id)
    place_lock.protect(
        [item], published_items, place_lock.hands(root, "shelters"), root, "shelters",
    )
    guarded = place_lock.snapshot([item])
    fill_referral_routes([item])
    place_lock.final_lock(
        [item], published_items, place_lock.hands(root, "shelters"), "shelters", guarded=guarded,
    )
    return item


def rebuild_warmspace(root, item_id, base_item, published_items, persist_new):
    import shelter_contacts
    from hours_fix import apply_phone, fix_hours
    import hours_norm

    base = os.path.join(root, "overrides")
    manual_rows = _load(os.path.join(base, "warmspaces_manual.json"), [])
    manual = {row["id"]: row for row in manual_rows if isinstance(row, dict) and row.get("id")}
    fixes_rows = _load(os.path.join(base, "warmspaces_fixes.json"), [])
    fixes = {row["id"]: row for row in fixes_rows if isinstance(row, dict) and row.get("id")}
    verified = _load(os.path.join(base, "warmspaces_verified.json"), {})
    item = copy.deepcopy(base_item) if base_item else {"id": item_id}
    item["id"] = item_id
    if item_id in manual:
        _overlay_overwrite(item, manual[item_id], skip=("reason",))
    if item_id in fixes:
        rec = fixes[item_id]
        for key in ("lat", "lng", "postcode", "address"):
            if key in rec:
                item[key] = copy.deepcopy(rec[key])
        _overlay_overwrite(item, rec, skip=("reason", "lat", "lng", "postcode", "address"))
    verified_rec = verified.get(item_id) if isinstance(verified.get(item_id), dict) else None
    if verified_rec:
        for key in VERIFIED_KEYS:
            if verified_rec.get(key):
                item[key] = copy.deepcopy(verified_rec[key])
        if verified_rec.get("verified_on"):
            item["verified"] = True
            item["verified_on"] = verified_rec.get("verified_on", "")
            item["evidence_url"] = verified_rec.get("evidence_url", "")
            item["tier"] = "verified"
        if verified_rec.get("phone_source"):
            item["phone_source"] = verified_rec["phone_source"]
        if verified_rec.get("phone_label"):
            item["phone_label"] = verified_rec["phone_label"]
        place_facts.copy_wheelchair(item, verified_rec)
    contacts_path = os.path.join(base, "warmspaces_contacts.json")
    contacts = shelter_contacts.load(contacts_path)
    contact = contacts.get(item_id) if isinstance(contacts, dict) else None
    if isinstance(contact, dict):
        if _stated(contact.get("phone_fix")):
            item["phone"] = contact["phone_fix"]
        elif _stated(contact.get("phone")):
            item["phone"] = contact["phone"]
    shelter_contacts.apply([item], contacts)
    facts = dict(manual)
    for key, rec in fixes.items():
        if isinstance(rec, dict) and any(name in rec for name in ("wheelchair", "wheelchair_quote", "wheelchair_source", "groups", "referral")):
            merged = dict(facts.get(key) or {"id": key})
            merged.update(rec)
            facts[key] = merged
    src = facts.get(item_id) if isinstance(facts.get(item_id), dict) else {}
    if src.get("groups"):
        item["groups"] = []
    referral = src.get("referral")
    if isinstance(referral, str) and referral.strip():
        item["referral"] = ""
    place_facts.stamp([item], facts, fill_missing=True)
    hours, changed = fix_hours(item.get("hours"))
    if changed:
        item["hours"] = hours
    hours_norm.apply([item], "hours")
    apply_phone(item)
    phone_lock.settle_council(item)
    phone_lock.guard(
        [item], root, via="refresh", source="publish_one", layer="warmspaces",
        persist_new=persist_new, published=phone_lock.live_council(published_items),
    )
    apply_phone(item)
    place_lock.protect(
        [item], published_items, place_lock.hands(root, "warmspaces"), root, "warmspaces",
    )
    return item


def rebuild_card(root, layer, item_id, base_item, published_items, is_new, persist_new):
    if layer == "foodbanks":
        return rebuild_foodbank(root, item_id, base_item, published_items, is_new, persist_new)
    if layer == "shelters":
        return rebuild_shelter(root, item_id, base_item, published_items, persist_new)
    if layer == "warmspaces":
        return rebuild_warmspace(root, item_id, base_item, published_items, persist_new)
    raise ValueError("unknown layer %s" % layer)


def _refuge(item):
    import shelter_sources
    blob = " ".join(str(item.get(key) or "") for key in ("name", "address", "referral", "groups", "who_for", "notes", "description"))
    if shelter_sources.is_refuge(item.get("name", ""), blob):
        return True
    return bool(re.search(r"domestic (?:abuse|violence)|\brefuge\b|women'?s\s+aid", item.get("name") or "", re.I))


def validate_card_gates(root, layer, item, is_new):
    import publish_gate
    item_id = item.get("id")
    if _refuge(item):
        raise ValueError("Rejecting %s: matches refuge or domestic abuse service (rule 85)" % item_id)
    if layer == "shelters":
        import google_handcheck
        import shelter_sources
        why = google_handcheck.held_reason(item, root=root)
        if why:
            raise ValueError("Rejecting %s: %s" % (item_id, why))
        if item_id in shelter_sources.excluded_shelter_ids(root):
            raise ValueError("Rejecting %s: shelter exclusion" % item_id)
        assert_no_pin(item, item_id)
    if layer == "foodbanks" and _foodbank_excluded(root, item):
        raise ValueError("Rejecting %s: food bank exclusion" % item_id)
    if layer == "warmspaces" and item_id in _warm_excluded(root):
        raise ValueError("Rejecting %s: warm space exclusion" % item_id)
    if not publish_gate.has_phone(layer, item):
        raise ValueError("Rejecting %s: no verified phone (rule 88)" % item_id)
    if layer == "shelters":
        who = item.get("who_for")
        if not item.get("groups") and who in (None, "", [], {}):
            raise ValueError("Rejecting shelter %s: no sourced who-it's-for" % item_id)
    if not is_new:
        return
    approved = auto_rules.approved(layer, root)
    if layer == "warmspaces":
        if item.get("verified") or publish_gate.council_listed_warmspace(item, root=root) or item_id in approved:
            return
        raise ValueError("Rejecting unapproved new warm space listing %s" % item_id)
    if item_id not in approved:
        raise ValueError("Rejecting unapproved new %s listing %s (not in approved_new_places.json)" % (layer, item_id))


def assert_whole_file(original_items, updated_items, item_id, is_new):
    expected = len(original_items) + (1 if is_new else 0)
    if len(updated_items) != expected:
        raise RuntimeError(
            "whole-file guard failed: count change was %s, expected %s"
            % (len(updated_items) - len(original_items), 1 if is_new else 0)
        )
    by_id = {}
    for item in updated_items:
        iid = item.get("id")
        if iid in by_id:
            raise RuntimeError("whole-file guard failed: duplicate id %s" % iid)
        by_id[iid] = item
    if is_new and item_id not in by_id:
        raise RuntimeError("whole-file guard failed: new id %s missing" % item_id)
    original_ids = []
    for item in original_items:
        iid = item.get("id")
        original_ids.append(iid)
        if iid == item_id:
            continue
        if iid not in by_id:
            raise RuntimeError("whole-file guard failed: id %s was removed" % iid)
        if by_id[iid] != item:
            raise RuntimeError("whole-file guard failed: other id %s was modified" % iid)
    if len(original_ids) != len(set(original_ids)):
        raise RuntimeError("whole-file guard failed: published file already has duplicate ids")
    return expected


def _read_stamp(root):
    path = os.path.join(root, "stamp.js")
    if not os.path.exists(path):
        raise RuntimeError("stamp.js is missing; refusing to write a stamp from an empty dict")
    text = open(path, encoding="utf-8").read()
    try:
        prev = stamp._load_text(text)
    except Exception as e:
        raise RuntimeError("stamp.js did not parse; refusing to rewrite other layers from {}") from e
    if not isinstance(prev, dict) or not isinstance(prev.get("layers"), dict):
        raise RuntimeError("stamp.js has no layers object; refusing to start from {}")
    return path, prev


def bump_stamp(root, layer, now=None):
    """Move only this layer's stamp. A parse error raises and does not write."""
    path, prev = _read_stamp(root)
    kind = STAMP_KIND[layer]
    key = STAMP_KEY[kind]
    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo("Europe/London")
    except Exception:
        zone = datetime.timezone.utc
    when = now or datetime.datetime.now(zone)
    if when.tzinfo is None:
        when = when.replace(tzinfo=zone)
    run = when.isoformat(timespec="seconds")
    label = "%s %s, %s" % (when.day, when.strftime("%b %Y"), when.strftime("%H:%M"))
    layers = dict(prev.get("layers") or {})
    layers[key] = {"run": run, "label": label}
    updated = dict(prev)
    updated["run"] = run
    updated["kind"] = kind
    updated["label"] = label
    updated["layers"] = layers
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.FB_STAMP=" + json.dumps(updated) + ";\n")
    os.replace(tmp, path)
    return updated


def _write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _write_layer(root, layer, prefix, data, postfix):
    path = os.path.join(root, FILES[layer][0])
    if layer == "foodbanks":
        body = json.dumps(data)
    else:
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    _write_text(path, prefix + body + postfix)
    if layer != "foodbanks":
        return
    js_path = os.path.join(root, FILES["foodbanks"][1])
    _write_text(js_path, compact.encode(data))


def _verify_written(root, layer, original_items, item_id, expected):
    _, data, _ = read_layer(root, layer)
    items = data.get("items", [])
    assert_whole_file(original_items, items, item_id, expected == len(original_items) + 1)
    if len(items) != expected:
        raise RuntimeError("post-write verify failed: expected %s items, found %s" % (expected, len(items)))
    found = [item for item in items if item.get("id") == item_id]
    if len(found) != 1:
        raise RuntimeError("post-write verify failed: %s not in the re-parsed layer" % item_id)
    if layer == "foodbanks":
        js_path = os.path.join(root, FILES["foodbanks"][1])
        if not os.path.exists(js_path):
            raise RuntimeError("post-write verify failed: data.js was not written")
        js_text = open(js_path, encoding="utf-8").read()
        if item_id not in js_text:
            raise RuntimeError("post-write verify failed: data.js does not contain %s" % item_id)
        if js_text != compact.encode(data):
            raise RuntimeError("post-write verify failed: data.js does not match data.full.js for this layer")
    return found[0]


def _publish(root, layer, item_id, dry_run, now=None):
    if layer not in LAYER_NAMES:
        raise ValueError("unknown layer %s" % layer)
    if not dry_run:
        _read_stamp(root)
    prefix, data, postfix = read_layer(root, layer)
    items = list(data.get("items") or [])
    base_item = None
    index = None
    for i, item in enumerate(items):
        if item.get("id") == item_id:
            if index is not None:
                raise RuntimeError("published %s already contains %s more than once" % (layer, item_id))
            index = i
            base_item = copy.deepcopy(item)
    is_new = index is None
    card = rebuild_card(
        root, layer, item_id, base_item, items, is_new, persist_new=not dry_run,
    )
    if card is None:
        if is_new and item_id not in auto_rules.approved(layer, root):
            raise ValueError("Rejecting unapproved new %s listing %s (not in approved_new_places.json)" % (layer, item_id))
        raise ValueError("Rejecting %s: no Give Food/IFAN record or overlay to build this card" % item_id)
    if not card.get("name"):
        raise ValueError("Rejecting %s: rebuilt card has no name" % item_id)
    validate_card_gates(root, layer, card, is_new)
    updated = list(items)
    if is_new:
        updated.append(card)
    else:
        updated[index] = card
    expected = assert_whole_file(items, updated, item_id, is_new)
    if dry_run:
        print("DRY RUN: validated publish_one for %s:%s" % (layer, item_id), file=sys.stderr)
        return card
    originals = {}
    for rel in FILES[layer]:
        path = os.path.join(root, rel)
        originals[path] = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    data["items"] = updated
    try:
        _write_layer(root, layer, prefix, data, postfix)
        _verify_written(root, layer, items, item_id, expected)
    except Exception:
        for path, text in originals.items():
            if text is None:
                if os.path.exists(path):
                    os.remove(path)
            else:
                _write_text(path, text)
        raise
    bump_stamp(root, layer, now=now)
    print("publish_one: published %s:%s" % (layer, item_id), file=sys.stderr)
    return card


def _sandbox(root):
    dst = tempfile.mkdtemp(prefix="publish_one_dry_")
    for name in ("overrides", "data.full.js", "data.js", "shelters.js", "warmspaces.js", "stamp.js"):
        src = os.path.join(root, name)
        if not os.path.exists(src):
            continue
        target = os.path.join(dst, name)
        if os.path.isdir(src):
            shutil.copytree(src, target)
        else:
            shutil.copy2(src, target)
    return dst


def publish_one(root, layer, item_id, dry_run=False, now=None):
    """Publish one id. A dry run rebuilds with persist_new=False and writes nothing in root."""
    root = os.path.abspath(root)
    if not dry_run:
        return _publish(root, layer, item_id, dry_run=False, now=now)
    sandbox = _sandbox(root)
    try:
        return _publish(sandbox, layer, item_id, dry_run=True, now=now)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def emit_list(grouped, github_output=False):
    text = json.dumps(grouped, sort_keys=True)
    print(text)
    if not github_output:
        return
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        raise RuntimeError("GITHUB_OUTPUT is not set")
    with open(path, "a", encoding="utf-8") as f:
        f.write("foodbank_ids=%s\n" % json.dumps(grouped["foodbanks"]))
        f.write("shelter_ids=%s\n" % json.dumps(grouped["shelters"]))
        f.write("warmspace_ids=%s\n" % json.dumps(grouped["warmspaces"]))
        for layer in LAYER_NAMES:
            f.write("run_%s=%s\n" % (layer, "true" if grouped[layer] else "false"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Add or edit one listing without rebuilding the layer.")
    parser.add_argument("--layer", choices=LAYER_NAMES)
    parser.add_argument("--id", dest="item_id")
    parser.add_argument("--commit", default="")
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true", help="print layer ids as JSON and do not publish")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.list:
        if args.layer or args.item_id:
            if not args.layer or not args.item_id:
                print("layer and id are both required", file=sys.stderr)
                return 1
            grouped = {layer: [] for layer in LAYER_NAMES}
            grouped[args.layer] = [args.item_id]
        else:
            grouped = group_ids(detect_from_commit(root, args.commit or "HEAD"))
        emit_list(grouped, args.github_output)
        return 0
    if args.layer and args.item_id:
        publish_one(root, args.layer, args.item_id, dry_run=args.dry_run)
        return 0
    pairs = detect_from_commit(root, args.commit or "HEAD")
    if not pairs:
        print("No listing overlay changes detected in commit.", file=sys.stderr)
        return 0
    print("Detected %s listing(s): %s" % (len(pairs), pairs), file=sys.stderr)
    for layer, iid in pairs:
        publish_one(root, layer, iid, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
