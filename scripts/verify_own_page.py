"""Independent second read of own-page mismatch claims (read-only; never writes data files).

Input CSV columns: listing id, own-page URL, our phone, own-page phone, our times, own-page times;
optional: listing name, postcode.
Each URL is opened twice in Playwright Chromium. A phone is CONFIRMED only when the claimed number is
written on both reads (digits run together across two numbers never count). Times are CONFIRMED only
when both reads show the same timetable and it matches the claimed own-page times.

Output adds verdict columns, a quote, action (AUTO_APPLY or REVIEW), and review_reason. AUTO_APPLY when
the own site shows the value identically on both reads, listing rows do not conflict, and applying would
not replace known session times with closed or empty. A one-line REVIEW summary is printed to stderr.

A confirmed phone is still REVIEW (phone audit, Dean 28 Oct 2026) when:
  - the page is a host page and the food bank has its own site (overrides/own_location_pages.json
    "_food_bank_own_sites"; rule 21 as narrowed by rule change E);
  - our current number is still on either read;
  - the page never mentions a food bank (or the listing name);
  - a shop, office, helpline or similar label sits beside the number (phone_rule.other_label);
  - the page has more than one number, or the listing is a centre pin (id with "/"), and the number is
    not in the same block as the listing name or postcode.

Usage:
  python scripts/verify_own_page.py claims.csv > results.csv
  python scripts/verify_own_page.py --fixture-dir tests/fixtures/verify_own_page claims.csv

Fixtures are *.saved (not .html) so map-credit policy tests ignore them.
"""
import argparse
import csv
import io
import os
import re
import sys
import time

COLS = (
    "listing id",
    "own-page URL",
    "our phone",
    "own-page phone",
    "our times",
    "own-page times",
)
OUT_EXTRA = (
    "phone_verdict",
    "phone_quote",
    "times_verdict",
    "times_quote",
    "verdict",
    "quote",
    "action",
    "review_reason",
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.6668.29 Safari/537.36 helpmap-own-page-verify"
)
SESSION_TIME = re.compile(
    r"\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:to|–|-)\s*\d{1,2}",
    re.I,
)
PHONE_RX = re.compile(r"(?<!\d)(?:\+44\s?\(?0?\)?|0)(?:\d[\s-]?){9,10}(?!\d)")


def norm_header(h):
    return re.sub(r"\s+", " ", (h or "").strip().lower())


def row_key(row):
    return {norm_header(k): (v or "").strip() for k, v in row.items()}


def pick(row, name):
    want = norm_header(name)
    if want in row:
        return (row.get(want) or "").strip()
    for k, v in row.items():
        if norm_header(k) == want:
            return (v or "").strip()
    return ""


def digits_only(s):
    d = re.sub(r"\D", "", s or "")
    if len(d) > 10 and d.startswith("44"):
        d = "0" + d[2:]
    if d.startswith("00"):
        d = d[1:]
    return d


def norm_ws(s):
    return re.sub(r"\s+", " ", (s or "").strip())


RENDER_WAIT_MS = 4000
READY_SELECTOR = (
    "text=/Collection times|Opening times|Get directions|Call us|telephone|Contact|"
    "food bank|foodbank|We are open|Opening Hours/i"
)


def html_to_text(html):
    t = re.sub(r"(?is)<(script|style|svg).*?</\1>", " ", html or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def page_text_after_render(page, url):
    """Read visible text after scripts run (same approach as render_fetch)."""
    resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_selector(READY_SELECTOR, timeout=12000)
    except Exception:
        page.wait_for_timeout(RENDER_WAIT_MS)
    try:
        text = page.inner_text("body")
    except Exception:
        text = html_to_text(page.content())
    text = norm_ws(text)
    status = resp.status if resp else 0
    ok = bool(text) and status < 400
    return text, ok


def phone_quote(text, claimed):
    want = digits_only(claimed)
    if not want:
        return ""
    for m in PHONE_RX.finditer(text or ""):
        if digits_only(m.group()) == want:
            a = max(0, m.start() - 30)
            return norm_ws(text[a : m.end() + 40])
    return ""


def phone_in_read(claimed, text):
    """Only a whole number written on the page counts. Digits run together across two numbers never match."""
    want = digits_only(claimed)
    if len(want) < 10:
        return False
    for m in PHONE_RX.finditer(text or ""):
        if digits_only(m.group()) == want:
            return True
    return False


def numbers_on(text):
    return {digits_only(m.group()) for m in PHONE_RX.finditer(text or "")} - {""}


def _squash(s):
    return re.sub(r"[\s\u2019'.,-]+", "", (s or "").lower())


BLOCK = 250


def in_listing_block(text, claimed, name="", postcode=""):
    """True when the listing's name or postcode is written in the same block as the claimed number:
    within BLOCK characters either side, not past a different number."""
    want = digits_only(claimed)
    keys = [k for k in (_squash(name), _squash(postcode)) if len(k) >= 4]
    if not want or not keys:
        return False
    ms = list(PHONE_RX.finditer(text or ""))
    for k, m in enumerate(ms):
        if digits_only(m.group()) != want:
            continue
        lo = max(m.start() - BLOCK, 0)
        for p in reversed(ms[:k]):
            if digits_only(p.group()) != want:
                lo = max(lo, p.end())
                break
        hi = min(m.end() + BLOCK, len(text))
        for n in ms[k + 1 :]:
            if digits_only(n.group()) != want:
                hi = min(hi, n.start())
                break
        seg = _squash(text[lo:hi])
        if any(key in seg for key in keys):
            return True
    return False


OWN_SITES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "overrides", "own_location_pages.json")


def load_own_sites(path=None):
    """Listing id -> the food bank's own site, where its listing website is a host page (rule change E)."""
    try:
        import json

        with open(path or OWN_SITES, encoding="utf-8") as f:
            raw = json.load(f).get("_food_bank_own_sites") or {}
    except Exception:
        return {}
    return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, str) and v.startswith("http")}


def _host(u):
    from urllib.parse import urlparse

    h = urlparse(u or "").netloc.lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h


def phone_review_reason(row, text1, text2, own_sites=None):
    """Why a number that is on both reads still needs a person (phone audit 28 Oct 2026, fix F). '' = none."""
    import phone_rule

    lid = pick(row, "listing id")
    claimed = pick(row, "own-page phone")
    ours = pick(row, "our phone")
    name = pick(row, "listing name")
    postcode = pick(row, "postcode")
    want = digits_only(claimed)
    own = (own_sites or {}).get(lid)
    if own and _host(own) != _host(pick(row, "own-page URL")):
        return "host page does not count: the food bank has its own site (%s)" % own
    if digits_only(ours) and digits_only(ours) != want and (phone_in_read(ours, text1) or phone_in_read(ours, text2)):
        return "our current number is still on the page"
    if not phone_rule.mentions_food_bank(text1 + "\n" + text2, [name]):
        return "page does not mention a food bank"
    for t in (text1, text2):
        lab = phone_rule.other_label(t, claimed)
        if lab:
            return "number sits beside another label (%s)" % lab
    many = len(numbers_on(text1) | numbers_on(text2)) > 1
    if "/" in lid or many:
        if not (in_listing_block(text1, claimed, name, postcode) and in_listing_block(text2, claimed, name, postcode)):
            if "/" in lid:
                return "centre pin needs a centre-scoped read (number not in the centre's own block)"
            return "more than one number on the page and this one is not in the listing's own block"
    return ""


def assess_phone(claimed, text1, text2, fetch_ok):
    if not (claimed or "").strip():
        return "UNSURE", "", ""
    if not fetch_ok:
        return "UNSURE", "", "page could not be read"
    in1, in2 = phone_in_read(claimed, text1), phone_in_read(claimed, text2)
    q = phone_quote(text1 if in1 else text2, claimed) or phone_quote(text2, claimed)
    if in1 and in2:
        return "CONFIRMED", q, ""
    if not in1 and not in2:
        return "REJECTED", q, "digits not on page"
    return "UNSURE", q, "number not on both reads"


def times_fingerprint(text):
    t = norm_ws(text).lower()
    m = re.search(
        r"collection times(.{0,3000}?)(?:delivery times|call us|email us|phone us|give us feedback|$)",
        t,
        re.I | re.S,
    )
    seg = m.group(1) if m else t
    seg = re.sub(r"closed today|open today until[^.;]+", " ", seg, flags=re.I)
    seg = re.sub(r"opens? today at[^.;]+", " ", seg, flags=re.I)
    return norm_ws(seg)


def normalize_times_blob(s):
    s = norm_ws(s).lower()
    s = re.sub(r"[^\w\s:–\-apm.]", " ", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\b0(\d)(?=\D|$)", r"\1", s)
    s = re.sub(r"(\d)(am|pm)", r"\1 \2", s)
    return s.strip()


def times_bearing_extract(text):
    bits = []
    for m in re.finditer(
        r"[^.\n|]{8,220}(?:\d{1,2}(?::|\.)?\d{0,2}\s*(?:am|pm)|"
        r"Collection times|Opening times|open every|Monday|Tuesday|Wednesday|Thursday|Friday|"
        r"Saturday|Sunday)[^.\n|]{0,140}",
        text or "",
        re.I,
    ):
        bits.append(m.group())
    return norm_ws(" ".join(bits)) if bits else norm_ws(text or "")[:8000]


def times_stable_key(text):
    fp = times_fingerprint(text)
    if re.search(r"collection times|opening times", text or "", re.I):
        return normalize_times_blob(fp)
    return normalize_times_blob(times_bearing_extract(text))


def times_on_page_match(claim, page_text):
    if not (claim or "").strip():
        return True
    full = normalize_times_blob(page_text or "")
    c = normalize_times_blob(claim)
    if not c:
        return True
    if c in full:
        return True
    chunks = [x.strip() for x in re.split(r"[;|]", claim) if x.strip()]
    if chunks and all(normalize_times_blob(ch) in full for ch in chunks):
        return True
    for m in re.finditer(
        r"[^.;|]{12,180}\d[^.;|]{0,90}(?:am|pm)[^.;|]{0,60}",
        claim,
        re.I,
    ):
        if normalize_times_blob(m.group()) in full:
            return True
    dm = re.search(
        r"(mon|tue|wed|thu|fri|sat|sun)\w*\s*(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})",
        claim,
        re.I,
    )
    if dm:
        day = dm.group(1)[:3].lower()
        a, b = dm.group(2), dm.group(3)
        if day in full and a in full and b in full:
            return True
    return False


def times_quote(text, fp):
    raw = text or ""
    m = re.search(r"(Collection times.{0,400})", raw, re.I | re.S)
    if m:
        return norm_ws(m.group(1))[:400]
    return fp[:400]


def has_known_sessions(times_str):
    s = (times_str or "").strip()
    if not s:
        return False
    if re.search(r"\(no opening|no opening_times|timings_text_only\)", s, re.I):
        return False
    if re.search(r"delivery only", s, re.I) and not SESSION_TIME.search(s):
        return False
    return bool(SESSION_TIME.search(s) or re.search(r"\d{1,2}:\d{2}", s))


def is_empty_or_all_closed(times_str):
    s = norm_ws(times_str).lower()
    if not s:
        return True
    if SESSION_TIME.search(s):
        return False
    if re.search(r"\d{1,2}:\d{2}", s) and "closed" not in s:
        return False
    return True


def assess_times(claim, text1, text2, fetch_ok):
    if not (claim or "").strip():
        return "UNSURE", "", ""
    if not fetch_ok:
        return "UNSURE", "", "page could not be read"
    fp1, fp2 = times_stable_key(text1), times_stable_key(text2)
    if not fp1 and not fp2:
        return "REJECTED", "", "no times on page"
    if fp1 != fp2:
        return "UNSURE", times_quote(text1, times_fingerprint(text1)), "reads disagree"
    if not times_on_page_match(claim, text1):
        return "REJECTED", times_quote(text1, times_fingerprint(text1)), "timetable on page differs from claim"
    return "CONFIRMED", times_quote(text1, times_fingerprint(text1)), ""


def overall_verdict(phone_v, times_v, need_phone, need_times):
    vs = []
    if need_phone:
        vs.append(phone_v)
    if need_times:
        vs.append(times_v)
    if not vs:
        return "UNSURE"
    if any(v == "REJECTED" for v in vs):
        return "REJECTED"
    if all(v == "CONFIRMED" for v in vs):
        return "CONFIRMED"
    return "UNSURE"


def would_blank_known_times(our_times, page_times_fp):
    if not has_known_sessions(our_times):
        return False
    return is_empty_or_all_closed(page_times_fp)


def listing_conflicts(processed):
    """Same listing id with different URLs or confirmed own-page phones."""
    by = {}
    for r in processed:
        lid = pick(r, "listing id")
        by.setdefault(lid, []).append(r)
    bad = set()
    for lid, rows in by.items():
        urls = {pick(r, "own-page URL") for r in rows if pick(r, "own-page URL")}
        if len(urls) > 1:
            bad.add(lid)
            continue
        phones = {
            digits_only(pick(r, "own-page phone"))
            for r in rows
            if r.get("phone_verdict") == "CONFIRMED" and digits_only(pick(r, "own-page phone"))
        }
        if len(phones) > 1:
            bad.add(lid)
    return bad


def decide_action(r, conflict):
    need_phone = bool(pick(r, "own-page phone"))
    need_times = bool(pick(r, "own-page times"))
    pv = r.get("phone_verdict", "UNSURE")
    tv = r.get("times_verdict", "UNSURE")
    fetch_ok = r.get("_fetch_ok", True)

    if conflict:
        return "REVIEW", "own pages conflict"
    if not fetch_ok:
        return "REVIEW", "site down"
    if need_phone and pv != "CONFIRMED":
        if pv == "REJECTED" or not phone_in_read(pick(r, "own-page phone"), r.get("_text1", "")):
            return "REVIEW", "no number or times on the page"
        return "REVIEW", "no number or times on the page"
    if need_phone and r.get("_phone_review"):
        return "REVIEW", r["_phone_review"]
    if need_times and tv != "CONFIRMED":
        if tv == "REJECTED":
            return "REVIEW", "no number or times on the page"
        if r.get("_times_note") == "reads disagree":
            return "REVIEW", "site down"
        return "REVIEW", "no number or times on the page"
    if need_times and would_blank_known_times(pick(r, "our times"), r.get("_times_fp", "")):
        return "REVIEW", "would blank data"
    if need_phone and pv == "CONFIRMED" and (not need_times or tv == "CONFIRMED"):
        return "AUTO_APPLY", ""
    if need_times and tv == "CONFIRMED" and not need_phone:
        return "AUTO_APPLY", ""
    return "REVIEW", "uncertain"


def review_summary(rows):
    parts = []
    for r in rows:
        if r.get("action") != "REVIEW":
            continue
        lid = pick(r, "listing id")
        reason = r.get("review_reason") or "uncertain"
        parts.append("%s (%s)" % (lid or "?", reason))
    if not parts:
        return "REVIEW: none"
    return "REVIEW: " + "; ".join(parts)


def process_row(row, text1, text2, fetch_ok=True, own_sites=None):
    r = dict(row)
    need_phone = bool(pick(r, "own-page phone"))
    need_times = bool(pick(r, "own-page times"))
    pv, pq, _ = assess_phone(pick(r, "own-page phone"), text1, text2, fetch_ok)
    tv, tq, tnote = assess_times(pick(r, "own-page times"), text1, text2, fetch_ok)
    r["phone_verdict"] = pv if need_phone else ""
    r["phone_quote"] = pq if need_phone else ""
    r["times_verdict"] = tv if need_times else ""
    r["times_quote"] = tq if need_times else ""
    r["verdict"] = overall_verdict(pv, tv, need_phone, need_times)
    r["quote"] = pq or tq
    r["_fetch_ok"] = fetch_ok
    r["_text1"] = text1
    r["_times_fp"] = times_fingerprint(text1) if fetch_ok else ""
    r["_times_note"] = tnote
    r["_phone_review"] = phone_review_reason(r, text1, text2, own_sites) if need_phone and fetch_ok else ""
    return r


def load_fixture_pair(fixture_dir, listing_id):
    safe = re.sub(r"[^\w\-/]+", "_", listing_id)
    p1 = os.path.join(fixture_dir, safe + "_read1.saved")
    p2 = os.path.join(fixture_dir, safe + "_read2.saved")
    with open(p1, encoding="utf-8") as f:
        h1 = f.read()
    with open(p2, encoding="utf-8") as f:
        h2 = f.read()
    return html_to_text(h1), html_to_text(h2)


def fetch_twice_live(url, gap_sec=2.0):
    from playwright.sync_api import sync_playwright

    texts = []
    err = None
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        try:
            for _ in range(2):
                page = browser.new_page(user_agent=UA)
                try:
                    text, ok = page_text_after_render(page, url)
                    if not ok:
                        err = err or "empty or error response"
                    texts.append(text)
                except Exception as e:
                    err = str(e)
                    texts.append("")
                finally:
                    page.close()
                if gap_sec:
                    time.sleep(gap_sec)
        finally:
            browser.close()
    ok = err is None and all(t.strip() for t in texts)
    return texts[0] if texts else "", texts[1] if len(texts) > 1 else "", ok


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        raw = f.read()
    delim = "\t" if "\t" in raw.splitlines()[0] else ","
    return list(csv.DictReader(io.StringIO(raw), delimiter=delim))


def write_csv(rows, out):
    if not rows:
        return
    fields = list(rows[0].keys())
    for c in OUT_EXTRA:
        if c not in fields:
            fields.append(c)
    clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    w = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(clean)


def run(rows, loader, own_sites=None):
    own_sites = load_own_sites() if own_sites is None else own_sites
    processed = []
    for row in rows:
        rk = row_key(row)
        lid = pick(rk, "listing id")
        url = pick(rk, "own-page URL")
        try:
            t1, t2, ok = loader(lid, url)
        except Exception:
            t1, t2, ok = "", "", False
        processed.append(process_row(rk, t1, t2, ok, own_sites))
    conflicts = listing_conflicts(processed)
    for r in processed:
        act, reason = decide_action(r, pick(r, "listing id") in conflicts)
        r["action"] = act
        r["review_reason"] = reason
    return processed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", help="claims CSV path")
    ap.add_argument(
        "--fixture-dir",
        help="read <id>_read1.html / _read2.html instead of live Playwright fetches",
    )
    ap.add_argument("--gap", type=float, default=2.0, help="seconds between live reads")
    args = ap.parse_args(argv)
    rows = read_csv(args.csv)

    if args.fixture_dir:

        def loader(lid, url):
            a, b = load_fixture_pair(args.fixture_dir, lid)
            return a, b, True

    else:

        def loader(lid, url):
            return fetch_twice_live(url, gap_sec=args.gap)

    out_rows = run(rows, loader)
    print(review_summary(out_rows), file=sys.stderr)
    write_csv(out_rows, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
