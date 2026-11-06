"""publish_one: one-card add/edit path for food banks, shelters and warm spaces.
Updates or adds exactly one listing safely and quickly without rebuilding the whole layer.
Base files:
  foodbanks: data.full.js and data.js
  shelters: shelters.js
  warmspaces: warmspaces.js
"""
import argparse
import copy
import datetime
import json
import os
import re
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import auto_rules
import compact
from hours_fix import apply_phone, fix_hours
import phone_lock
import phone_rule
import place_facts
import place_lock
import publish_gate
import shelter_contacts
import shelter_sources

ROOT_DEFAULT = os.path.dirname(SCRIPTS_DIR)
FILES = {
    "foodbanks": ("data.full.js", "data.js"),
    "shelters": ("shelters.js",),
    "warmspaces": ("warmspaces.js",),
}
LAYER_NAMES = ("foodbanks", "shelters", "warmspaces")

# Overlay file to layer mapping
OVERLAY_LAYER_MAP = {
    "foodbank_added.json": "foodbanks",
    "foodbank_address_fixes.json": "foodbanks",
    "foodbank_approved_new.json": "foodbanks",
    "foodbank_checks.json": "foodbanks",
    "foodbank_closed.json": "foodbanks",
    "foodbank_exclude.json": "foodbanks",
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
    "shelter_exclusions.json": "shelters",
    "shelters_contacts.json": "shelters",
    "shelters_manual.json": "shelters",
    "shelters_unverified.json": "shelters",
    "shelters_verified.json": "shelters",
    "warmspaces_contacts.json": "warmspaces",
    "warmspaces_exclude.json": "warmspaces",
    "warmspaces_fixes.json": "warmspaces",
    "warmspaces_manual.json": "warmspaces",
    "warmspaces_unverified.json": "warmspaces",
    "warmspaces_verified.json": "warmspaces",
    "arcgis_warmspaces.json": "warmspaces",
}


def load_json_file(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def parse_js_layer(text):
    """Splits prefix, json object, postfix from layer js."""
    start = text.index("{")
    end = text.rindex("}") + 1
    prefix = text[:start]
    data = json.loads(text[start:end])
    postfix = text[end:]
    return prefix, data, postfix


def read_layer(root, layer):
    main_rel = FILES[layer][0]
    p = os.path.join(root, main_rel)
    if not os.path.exists(p):
        raise FileNotFoundError(f"Layer file not found: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return parse_js_layer(f.read())


def write_layer_raw(root, layer, prefix, data, postfix):
    main_rel = FILES[layer][0]
    p = os.path.join(root, main_rel)
    tmp = p + ".tmp"
    if layer == "foodbanks":
        body = json.dumps(data)
    else:
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(prefix + body + postfix)
    os.replace(tmp, p)

    if layer == "foodbanks":
        # Generate data.js via compact.py
        data_js_path = os.path.join(root, FILES["foodbanks"][1])
        out_text = compact.encode(data)
        tmp_compact = data_js_path + ".tmp"
        with open(tmp_compact, "w", encoding="utf-8") as f:
            f.write(out_text)
        os.replace(tmp_compact, data_js_path)


def bump_stamp(root, layer, now=None):
    """Bumps only that layer's stamp (rule 19)."""
    stamp_path = os.path.join(root, "stamp.js")
    if not os.path.exists(stamp_path):
        return
    try:
        from zoneinfo import ZoneInfo
        now_dt = now or datetime.datetime.now(ZoneInfo("Europe/London"))
    except Exception:
        now_dt = now or datetime.datetime.now(datetime.timezone.utc)

    k_map = {"foodbanks": "fb", "shelters": "sh", "warmspaces": "ws"}
    k = k_map.get(layer)
    if not k:
        return

    run_iso = now_dt.isoformat(timespec="seconds")
    label = f"{now_dt.day} {now_dt:%b %Y}, {now_dt:%H:%M}"

    try:
        with open(stamp_path, "r", encoding="utf-8") as f:
            txt = f.read()
        _, s, _ = parse_js_layer(txt)
    except Exception:
        s = {}

    layers = dict(s.get("layers") or {})
    layers[k] = {"run": run_iso, "label": label}
    s["layers"] = layers
    s["run"] = run_iso
    s["kind"] = layer
    s["label"] = label

    tmp = stamp_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.FB_STAMP=" + json.dumps(s) + ";\n")
    os.replace(tmp, stamp_path)


def _get_commit_file_content(root, commit_ref, rel_path):
    r = subprocess.run(
        ["git", "-C", root, "show", f"{commit_ref}:{rel_path}"],
        capture_output=True,
    )
    if r.returncode == 0:
        return r.stdout.decode("utf-8", "replace")
    return None


def _find_changed_ids_in_objects(old_obj, new_obj):
    """Compare old and new object dictionaries or lists to extract changed IDs."""
    changed_ids = set()
    if isinstance(new_obj, dict):
        old_dict = old_obj if isinstance(old_obj, dict) else {}
        for k, v in new_obj.items():
            if str(k).startswith("_"):
                continue
            if k not in old_dict or old_dict[k] != v:
                changed_ids.add(k)
    elif isinstance(new_obj, list):
        old_map = {}
        if isinstance(old_obj, list):
            for it in old_obj:
                if isinstance(it, dict) and it.get("id"):
                    old_map[it["id"]] = it
        for it in new_obj:
            if isinstance(it, dict) and it.get("id"):
                iid = it["id"]
                if iid not in old_map or old_map[iid] != it:
                    changed_ids.add(iid)
    return changed_ids


def detect_from_commit(root, commit="HEAD"):
    """Determines layer and id(s) from git commit diff.
    - If refresh output / non-overlay change: returns empty list.
    - If overlay changes but IDs cannot be determined exactly: raises RuntimeError.
    - Otherwise returns list of (layer, id) pairs.
    """
    parent = f"{commit}^"
    # Check if parent commit exists
    p_check = subprocess.run(["git", "-C", root, "rev-parse", "--verify", "--quiet", parent], capture_output=True)
    has_parent = (p_check.returncode == 0)

    if has_parent:
        diff_cmd = ["git", "-C", root, "diff-tree", "--no-commit-id", "--name-only", "-r", parent, commit]
    else:
        diff_cmd = ["git", "-C", root, "show", "--name-only", "--pretty=format:", commit]

    r = subprocess.run(diff_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git diff inspection failed for {commit}: {r.stderr}")

    files = [line.strip() for line in r.stdout.splitlines() if line.strip()]

    # Ignore build/refresh artifacts, reports, stamps, compiled layers, learning state, etc.
    ignore_prefixes = (
        "logs/", "reports/", "food-banks/", "warm-spaces/", "shelters/", "docs/",
    )
    ignore_exact = (
        "data.js", "data.full.js", "shelters.js", "warmspaces.js",
        "stamp.js", "index.html", "version.json", "sitemap.xml",
        "robots.txt", "404.html", "accessibility.html", "faq.html",
        "terms.html", "privacy.html"
    )

    overlay_files = []
    for f in files:
        f_clean = f.strip()
        if f_clean.startswith(ignore_prefixes) or f_clean in ignore_exact:
            continue
        if "overrides/page_dates.json" in f_clean or "overrides/district_cache.json" in f_clean:
            continue
        if f_clean.startswith("overrides/"):
            overlay_files.append(f_clean)

    if not overlay_files:
        # Commit is refresh output, docs, tests, etc. - do nothing.
        return []

    detected_pairs = []
    for f in overlay_files:
        basename = os.path.basename(f)
        new_content = _get_commit_file_content(root, commit, f) or ""
        old_content = _get_commit_file_content(root, parent, f) if has_parent else ""

        try:
            new_obj = json.loads(new_content) if new_content.strip() else None
        except Exception:
            new_obj = None

        try:
            old_obj = json.loads(old_content) if old_content.strip() else None
        except Exception:
            old_obj = None

        if basename == "approved_new_places.json":
            # Keys in approved_new_places.json are organized by layer: {"foodbanks": {...}, "shelters": {...}, "warmspaces": {...}}
            if not isinstance(new_obj, dict):
                raise RuntimeError(f"Could not parse valid JSON in {f} to determine changed listing id(s).")
            old_dict = old_obj if isinstance(old_obj, dict) else {}
            found_any = False
            for lay in LAYER_NAMES:
                lay_new = new_obj.get(lay) or {}
                lay_old = old_dict.get(lay) or {}
                for k, v in lay_new.items():
                    if k not in lay_old or lay_old[k] != v:
                        detected_pairs.append((lay, k))
                        found_any = True
            if not found_any:
                raise RuntimeError(f"Changes in {f} could not be resolved to any listing id.")
            continue

        layer = OVERLAY_LAYER_MAP.get(basename)
        if not layer:
            raise RuntimeError(f"Unknown overlay file {f}; cannot determine target layer.")

        changed_ids = _find_changed_ids_in_objects(old_obj, new_obj)
        if not changed_ids:
            # Listing overlay changed but no IDs could be determined exactly -> fail visibly
            raise RuntimeError(f"Changes in overlay {f} could not be resolved to any listing id.")

        for iid in sorted(changed_ids):
            detected_pairs.append((layer, iid))

    # De-duplicate while preserving order
    seen = set()
    result = []
    for pair in detected_pairs:
        if pair not in seen:
            seen.add(pair)
            result.append(pair)
    return result


def find_overlay_source(root, layer, item_id):
    """Finds initial data for item_id from overlay files."""
    overrides_dir = os.path.join(root, "overrides")
    if layer == "foodbanks":
        for fn in ("foodbank_approved_new.json", "foodbank_added.json", "foodbank_extra_locations.json", "foodbank_own_pages.json"):
            data = load_json_file(os.path.join(overrides_dir, fn))
            if item_id in data and isinstance(data[item_id], dict):
                rec = copy.deepcopy(data[item_id])
                rec.setdefault("id", item_id)
                rec.setdefault("type", "foodbank")
                return rec
        man = load_json_file(os.path.join(overrides_dir, "foodbank_manual.json"))
        if item_id in man and isinstance(man[item_id], dict):
            rec = copy.deepcopy(man[item_id])
            rec.setdefault("id", item_id)
            rec.setdefault("type", "foodbank")
            return rec
    elif layer == "shelters":
        for fn in ("shelters_manual.json",):
            items = load_json_file(os.path.join(overrides_dir, fn), [])
            for it in items:
                if isinstance(it, dict) and it.get("id") == item_id:
                    return copy.deepcopy(it)
        for fn in ("shelters_verified.json", "shelters_unverified.json"):
            v_dict = load_json_file(os.path.join(overrides_dir, fn), {})
            if item_id in v_dict and isinstance(v_dict[item_id], dict):
                rec = copy.deepcopy(v_dict[item_id])
                rec["id"] = item_id
                return rec
    elif layer == "warmspaces":
        for fn in ("warmspaces_manual.json", "warmspaces_fixes.json"):
            items = load_json_file(os.path.join(overrides_dir, fn), [])
            for it in items:
                if isinstance(it, dict) and it.get("id") == item_id:
                    return copy.deepcopy(it)
        for fn in ("warmspaces_verified.json", "warmspaces_unverified.json"):
            v_dict = load_json_file(os.path.join(overrides_dir, fn), {})
            if item_id in v_dict and isinstance(v_dict[item_id], dict):
                rec = copy.deepcopy(v_dict[item_id])
                rec["id"] = item_id
                return rec
    return None


def rebuild_card(root, layer, item_id, base_item=None):
    """Rebuilds the whole card for item_id through the same helpers used by builders."""
    overrides_dir = os.path.join(root, "overrides")
    item = copy.deepcopy(base_item) if base_item else {}
    item["id"] = item_id

    # If new, populate from overlay source if available
    ov_src = find_overlay_source(root, layer, item_id)
    if ov_src:
        for k, v in ov_src.items():
            if k not in item or item[k] in (None, "", [], {}):
                item[k] = copy.deepcopy(v)

    if layer == "foodbanks":
        if not item.get("name") and ov_src and ov_src.get("name"):
            item["name"] = ov_src["name"]
        item.setdefault("type", "foodbank")
        item.setdefault("foodbank", item.get("name", ""))

        # Address fixes
        addr_fixes = load_json_file(os.path.join(overrides_dir, "foodbank_address_fixes.json"))
        if item_id in addr_fixes:
            for k in ("address", "postcode", "lat", "lng"):
                if k in addr_fixes[item_id]:
                    item[k] = addr_fixes[item_id][k]

        # Verified phones: phone ALWAYS comes from verified overlay, never Give Food
        phones = load_json_file(os.path.join(overrides_dir, "phones.json"))
        holds = load_json_file(os.path.join(overrides_dir, "phone_holds.json"))
        sources = load_json_file(os.path.join(overrides_dir, "phone_sources.json"))
        phones = phone_rule.phones_to_apply(phones, sources, holds)
        if item_id in phones:
            item["phone"] = phones[item_id]
            item["phone_checked"] = True

        apply_phone(item)

        plabels = load_json_file(os.path.join(overrides_dir, "phone_labels.json"))
        if item_id in plabels and item.get("phone"):
            lab = plabels[item_id]
            if isinstance(lab, str) and lab.strip():
                item["phone_label"] = lab.strip()

        # Opening times: only if verified from own source
        times_ov = load_json_file(os.path.join(overrides_dir, "opening_times.json"))
        if item_id in times_ov:
            from times import normalise
            item.update({"opening_times": normalise(times_ov[item_id])})

        # Notices
        notices = load_json_file(os.path.join(overrides_dir, "foodbank_notices.json"))
        if item_id in notices and isinstance(notices[item_id], dict) and notices[item_id].get("notice"):
            item["notice"] = notices[item_id]["notice"]

        # Place facts (wheelchair, groups, referral)
        fb_ov = {}
        for fn in ("foodbank_manual.json", "foodbank_added.json"):
            for k, v in load_json_file(os.path.join(overrides_dir, fn)).items():
                if str(k).startswith("_") or not isinstance(v, dict):
                    continue
                fb_ov.setdefault(k, {}).update(v)
        place_facts.stamp([item], fb_ov, fill_missing=True)

        # Classify client-facing vs warehouse/dropoff (manual locks in foodbank_manual.json)
        fb_man = load_json_file(os.path.join(overrides_dir, "foodbank_manual.json"))
        if item_id in fb_man and isinstance(fb_man[item_id], dict):
            m = fb_man[item_id]
            if m.get("kind") in ("warehouse", "dropoff"):
                item["kind"] = m["kind"]
                item["label_en"] = m.get("label_en", "")
                item["label_cy"] = m.get("label_cy", "")
                if m.get("locked"):
                    item["locked"] = True
                if m.get("phone"):
                    item["phone"] = m["phone"]
                    apply_phone(item)
                if m.get("drop_opening_times"):
                    item.update({"opening_times": None})

        # Phone lock guard
        phone_lock.guard(
            [item],
            root,
            via="refresh",
            source="publish_one",
            layer="foodbanks",
            persist_new=True,
            published=phone_lock.live_council([base_item] if base_item else []),
        )

        # Place lock protect
        if base_item:
            place_lock.protect(
                [item],
                [base_item],
                place_lock.hands(root, "foodbanks"),
                root,
                "foodbanks",
            )

    elif layer == "shelters":
        man_list = load_json_file(os.path.join(overrides_dir, "shelters_manual.json"), [])
        man_map = {m["id"]: m for m in man_list if isinstance(m, dict) and m.get("id")}
        if item_id in man_map:
            for k, v in man_map[item_id].items():
                if v not in (None, "", [], {}):
                    item[k] = copy.deepcopy(v)

        ver_map = load_json_file(os.path.join(overrides_dir, "shelters_verified.json"), {})
        if item_id in ver_map and isinstance(ver_map[item_id], dict):
            v = ver_map[item_id]
            for k in ("phone", "address", "access", "postcode", "lat", "lng", "hours", "evidence_name", "scheme_start", "scheme_end", "scheme_dates"):
                if v.get(k):
                    item[k] = v[k]
            if v.get("verified_on"):
                item["verified"] = True
                item["verified_on"] = v["verified_on"]
                item["evidence_url"] = v.get("evidence_url", "")
                item["tier"] = "verified"
            if v.get("phone_source"):
                item["phone_source"] = v["phone_source"]
            if v.get("phone_label"):
                item["phone_label"] = v["phone_label"]
            if v.get("access"):
                item["referral"] = v["access"][0].upper() + v["access"][1:]
            if not item.get("groups"):
                from common import infer_shelter_groups
                g = infer_shelter_groups(item, v)
                if g:
                    item["groups"] = g
                    item["groups_source"] = v.get("evidence_url") or v.get("evidence_name") or ""

        # Contacts & council lines
        sh_contacts = shelter_contacts.load(os.path.join(overrides_dir, "shelters_contacts.json"))
        shelter_contacts.apply([item], sh_contacts)

        # Place facts
        place_facts.stamp([item], man_map, fill_missing=True)

        apply_phone(item)

        # Phone lock
        phone_lock.settle_council(item)
        phone_lock.guard(
            [item],
            root,
            via="refresh",
            source="publish_one",
            layer="shelters",
            persist_new=True,
            published=phone_lock.live_council([base_item] if base_item else []),
        )

        # Place lock protect & final lock
        if base_item:
            place_lock.protect(
                [item],
                [base_item],
                place_lock.hands(root, "shelters"),
                root,
                "shelters",
            )
        guarded = place_lock.snapshot([item])
        common_mod = sys.modules.get("common")
        if common_mod and hasattr(common_mod, "fill_referral_routes"):
            common_mod.fill_referral_routes([item])
        else:
            if item.get("card_type") == "referral_hostel" and not item.get("referral_route") and item.get("referral"):
                item["referral_route"] = item["referral"]

        place_lock.final_lock(
            [item],
            [base_item] if base_item else [],
            place_lock.hands(root, "shelters"),
            "shelters",
            guarded=guarded,
        )

    elif layer == "warmspaces":
        man_list = load_json_file(os.path.join(overrides_dir, "warmspaces_manual.json"), [])
        man_map = {m["id"]: m for m in man_list if isinstance(m, dict) and m.get("id")}
        if item_id in man_map:
            for k, v in man_map[item_id].items():
                if v not in (None, "", [], {}):
                    item[k] = copy.deepcopy(v)

        fixes_list = load_json_file(os.path.join(overrides_dir, "warmspaces_fixes.json"), [])
        fixes_map = {m["id"]: m for m in fixes_list if isinstance(m, dict) and m.get("id")}
        if item_id in fixes_map:
            for k, v in fixes_map[item_id].items():
                if k != "reason" and v not in (None, "", [], {}):
                    item[k] = copy.deepcopy(v)

        ver_map = load_json_file(os.path.join(overrides_dir, "warmspaces_verified.json"), {})
        if item_id in ver_map and isinstance(ver_map[item_id], dict):
            v = ver_map[item_id]
            for k in ("phone", "address", "postcode", "lat", "lng", "hours", "evidence_name", "scheme_start", "scheme_end", "scheme_dates"):
                if v.get(k):
                    item[k] = v[k]
            if v.get("verified_on"):
                item["verified"] = True
                item["verified_on"] = v["verified_on"]
                item["evidence_url"] = v.get("evidence_url", "")
                item["tier"] = "verified"
            if v.get("phone_source"):
                item["phone_source"] = v["phone_source"]
            if v.get("phone_label"):
                item["phone_label"] = v["phone_label"]

        # Contacts
        ws_contacts = shelter_contacts.load(os.path.join(overrides_dir, "warmspaces_contacts.json"))
        shelter_contacts.apply([item], ws_contacts)

        # Place facts
        ws_ov = dict(man_map)
        for _k, _v in fixes_map.items():
            if isinstance(_v, dict) and any(x in _v for x in ("wheelchair", "wheelchair_quote", "wheelchair_source", "groups", "referral")):
                _b = dict(ws_ov.get(_k) or {"id": _k})
                _b.update(_v)
                ws_ov[_k] = _b
        place_facts.stamp([item], ws_ov, fill_missing=True)

        apply_phone(item)

        # Phone lock
        phone_lock.settle_council(item)
        phone_lock.guard(
            [item],
            root,
            via="refresh",
            source="publish_one",
            layer="warmspaces",
            persist_new=True,
            published=phone_lock.live_council([base_item] if base_item else []),
        )

        # Place lock protect
        if base_item:
            place_lock.protect(
                [item],
                [base_item],
                place_lock.hands(root, "warmspaces"),
                root,
                "warmspaces",
            )

    return item


def validate_card_gates(root, layer, item, is_new=False):
    """Enforces all card-level gates."""
    item_id = item.get("id")

    # 1. Domestic-abuse / women's refuge check: NEVER list refuges or domestic-abuse services
    text_blob = " ".join(
        str(item.get(k) or "")
        for k in ("name", "address", "referral", "groups", "who_for", "notes", "description")
    )
    if shelter_sources.is_refuge(item.get("name", ""), text_blob):
        raise ValueError(f"Rejecting {item_id}: matches refuge or domestic abuse service (rule 85)")
    if re.search(r"domestic (?:abuse|violence)|\brefuge\b|women'?s\s+aid", item.get("name", ""), re.I):
        raise ValueError(f"Rejecting {item_id}: matches refuge or domestic abuse service name (rule 85)")

    # 2. Verified phone check (rule 88) on all three layers
    if not publish_gate.has_phone(layer, item):
        ok_approved = auto_rules.approved(layer, root)
        if not (layer == "foodbanks" and item_id in ok_approved):
            raise ValueError(f"Rejecting {item_id}: no verified phone (rule 88)")

    # 3. Shelters: reject only when there is no sourced groups list and no sourced who-it's-for
    if layer == "shelters":
        has_groups = bool(item.get("groups"))
        has_who_for = item.get("who_for") not in (None, "", [], {})
        if not has_groups and not has_who_for:
            raise ValueError(f"Rejecting shelter {item_id}: no sourced who-it's-for")

    # 4. New places approval check
    if is_new:
        if layer in ("foodbanks", "shelters"):
            approved_ids = auto_rules.approved(layer, root)
            rules = auto_rules.load()
            auto_hostel = (
                layer == "shelters"
                and item.get("card_type") == "referral_hostel"
                and (rules.get("referral_hostel_auto_add") or {}).get("on")
                and item.get("phone")
                and (item.get("town") or item.get("area"))
                and not item.get("postcode")
                and not isinstance(item.get("lat"), (int, float))
                and not isinstance(item.get("lng"), (int, float))
            )
            if not auto_hostel and item_id not in approved_ids:
                raise ValueError(
                    f"Rejecting unapproved new {layer} listing {item_id} (not in approved_new_places.json)"
                )
        elif layer == "warmspaces":
            approved_ids = auto_rules.approved(layer, root)
            if not (item.get("verified") or publish_gate.council_listed_warmspace(item, root=root) or item_id in approved_ids):
                raise ValueError(
                    f"Rejecting unapproved new warm space listing {item_id}"
                )

    # 5. Shelter-specific no_pin / referral hostel invariants (rules 55 and 94)
    if layer == "shelters":
        if item.get("no_pin") or item.get("card_type") == "referral_hostel":
            if item.get("lat") not in (None, "") or item.get("lng") not in (None, ""):
                raise ValueError(
                    f"Rejecting no_pin shelter {item_id}: must not have lat/lng (rules 55 and 94)"
                )
            if item.get("postcode") not in (None, ""):
                raise ValueError(
                    f"Rejecting no_pin shelter {item_id}: must not have postcode (rules 55 and 94)"
                )
            addr = item.get("address", "")
            if re.search(r"\b\d+\s+[A-Za-z]+|\b(street|road|avenue|lane|drive|way|close)\b", addr, re.I):
                raise ValueError(
                    f"Rejecting no_pin shelter {item_id}: street address not allowed (rules 55 and 94): {addr}"
                )


def publish_one(root, layer, item_id, dry_run=False, now=None):
    """Executes the publish_one path for the given layer and item_id."""
    if layer not in LAYER_NAMES:
        raise ValueError(f"Unknown layer {layer}. Allowed: {LAYER_NAMES}")

    # Read published layer data
    prefix, data, postfix = read_layer(root, layer)
    items = data.get("items", [])
    existing_idx = None
    base_item = None
    for idx, it in enumerate(items):
        if it.get("id") == item_id:
            existing_idx = idx
            base_item = copy.deepcopy(it)
            break

    is_new = existing_idx is None

    # Pre-check overlays for invariant violations (e.g. no_pin rules 55 and 94)
    raw_overlay = find_overlay_source(root, layer, item_id)
    if layer == "shelters" and raw_overlay:
        if raw_overlay.get("no_pin") or raw_overlay.get("card_type") == "referral_hostel":
            if raw_overlay.get("lat") not in (None, "") or raw_overlay.get("lng") not in (None, ""):
                raise ValueError(
                    f"Rejecting no_pin shelter {item_id}: must not have lat/lng (rules 55 and 94)"
                )
            if raw_overlay.get("postcode") not in (None, ""):
                raise ValueError(
                    f"Rejecting no_pin shelter {item_id}: must not have postcode (rules 55 and 94)"
                )
            addr = raw_overlay.get("address", "")
            if re.search(r"\b\d+\s+[A-Za-z]+|\b(street|road|avenue|lane|drive|way|close)\b", addr, re.I):
                raise ValueError(
                    f"Rejecting no_pin shelter {item_id}: street address not allowed (rules 55 and 94): {addr}"
                )

    # Rebuild card through identical per-id helpers
    new_card = rebuild_card(root, layer, item_id, base_item=base_item)

    # Gate checks
    validate_card_gates(root, layer, new_card, is_new=is_new)

    # Update item in list
    if is_new:
        updated_items = items + [new_card]
    else:
        updated_items = list(items)
        updated_items[existing_idx] = new_card

    # Whole-file guards:
    # 1. Net count changed by 0 (update) or +1 (new id)
    expected_count = len(items) + (1 if is_new else 0)
    if len(updated_items) != expected_count:
        raise RuntimeError(
            f"Whole-file guard failed: count change was {len(updated_items) - len(items)}, expected {1 if is_new else 0}"
        )

    # 2. Every other id unchanged; no removals
    for it_orig in items:
        orig_id = it_orig.get("id")
        if orig_id == item_id:
            continue
        # Find in updated
        found = [x for x in updated_items if x.get("id") == orig_id]
        if not found:
            raise RuntimeError(f"Whole-file guard failed: id {orig_id} was removed")
        if found[0] != it_orig:
            raise RuntimeError(f"Whole-file guard failed: other id {orig_id} was modified")

    if dry_run:
        print(f"DRY RUN: successfully validated publish_one for {layer}:{item_id}")
        return new_card

    # Apply changes to published file(s)
    data["items"] = updated_items
    write_layer_raw(root, layer, prefix, data, postfix)

    # After writing published file(s), parse them again and fail if any other id moved or count is wrong
    re_prefix, re_data, _ = read_layer(root, layer)
    re_items = re_data.get("items", [])
    if len(re_items) != expected_count:
        raise RuntimeError(f"Post-write verify failed: expected {expected_count} items, found {len(re_items)}")
    for it_orig in items:
        orig_id = it_orig.get("id")
        if orig_id == item_id:
            continue
        matching = [x for x in re_items if x.get("id") == orig_id]
        if not matching or matching[0] != it_orig:
            raise RuntimeError(f"Post-write verify failed: other id {orig_id} was moved or corrupted")

    if layer == "foodbanks":
        # Also parse data.js and verify the id is in it
        data_js_path = os.path.join(root, FILES["foodbanks"][1])
        if not os.path.exists(data_js_path):
            raise RuntimeError("Post-write verify failed: data.js was not written")
        data_js_content = open(data_js_path, encoding="utf-8").read()
        if item_id not in data_js_content:
            raise RuntimeError(f"Post-write verify failed: data.js does not contain {item_id}")

    # Bump stamp for this layer only (rule 19)
    bump_stamp(root, layer, now=now)

    print(f"publish_one: successfully published {layer}:{item_id}")
    return new_card


def main(argv=None):
    parser = argparse.ArgumentParser(description="Add or edit one listing safely without rebuilding the whole layer.")
    parser.add_argument("--layer", choices=LAYER_NAMES, help="foodbanks | shelters | warmspaces")
    parser.add_argument("--id", help="listing id to add or edit")
    parser.add_argument("--commit", default="", help="Git commit to inspect when auto-detecting layer and id")
    parser.add_argument("--root", default=ROOT_DEFAULT, help="Repository root path")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing files")

    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)

    if args.layer and args.id:
        publish_one(root, args.layer, args.id, dry_run=args.dry_run)
        return 0

    if args.commit or (not args.layer and not args.id):
        commit = args.commit or "HEAD"
        candidates = detect_from_commit(root, commit)
        if not candidates:
            print("No listing overlay changes detected in commit.")
            return 0
        print(f"Detected {len(candidates)} listing(s) from commit {commit}: {candidates}")
        for lay, iid in candidates:
            publish_one(root, lay, iid, dry_run=args.dry_run)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
