"""Tell Dean when a REAL incident rest centre goes live on helpmap.uk (12 Nov 2026).

Called by incident_rest_centre_live.write_public after the public live file is written. For each card that is in
the new public file, was not in the file before, and is not a test, it opens one GitHub issue labelled `erc-live`:

    Rest centre live on helpmap.uk: <council> - <place> [erc:<key>]

GitHub emails new issues on this repository to its owner, and the body @mentions the owner, so the issue is also
the direct email. Grok Bot listens for the label and messages Dean in chat. No email secret is used here.

Once per incident: the key is the card's council, council page and place name. No new issue while one with that key
is open, or was opened in the last 72 hours. Never on every refresh: a card already in the live file before the
write is not new. Never for tests: a card marked test/example, or with "TEST" (capitals) or "system test" in its
name or what it was opened for, is skipped.

Only on the real repository's main branch inside GitHub Actions (GITHUB_ACTIONS=true, GITHUB_REF=refs/heads/main,
GH_TOKEN set, not the tests workflow, and only for the repository's own checkout). Practice runs, PR runs, the test
suite and temp folders never reach GitHub. Never raises: a failed alert prints a warning and the publish goes on.
"""
import datetime, hashlib, json, os, re, subprocess
from zoneinfo import ZoneInfo

ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LABEL = "erc-live"
OWNER = "Postcode-economics"
SITE = "https://helpmap.uk"
REPEAT_HOURS = 72
_TEST_CAPS = re.compile(r"\bTEST\b")
_TEST_WORDS = re.compile(r"\bsystem test\b|\bdo not travel\b", re.I)


def is_test(card):
    if not isinstance(card, dict):
        return True
    if card.get("test") or card.get("example"):
        return True
    for k in ("name", "opened_for", "id"):
        v = str(card.get(k) or "")
        if _TEST_CAPS.search(v) or _TEST_WORDS.search(v):
            return True
    if re.search(r"\bsystem test\b", str(card.get("quote") or ""), re.I):
        return True
    return False


def real_cards(payload):
    if not isinstance(payload, dict) or not payload.get("public"):
        return []
    out = []
    for c in payload.get("cards") or []:
        if not isinstance(c, dict) or c.get("live") is False or is_test(c):
            continue
        if (c.get("category") or "incident_rest_centre") != "incident_rest_centre":
            continue
        out.append(c)
    return out


def card_key(card):
    raw = "|".join([
        str(card.get("council") or card.get("opened_by") or "").strip().lower(),
        str(card.get("source_url") or "").strip(),
        str(card.get("name") or "").strip().lower(),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def newly_live(before, after):
    """Real cards in `after` whose key was not among the cards (test or not) already in `before`."""
    prev = set()
    if isinstance(before, dict) and before.get("public"):
        prev = {card_key(c) for c in (before.get("cards") or []) if isinstance(c, dict)}
    seen, out = set(), []
    for c in real_cards(after):
        k = card_key(c)
        if k in prev or k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


def _clip(s, n=80):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


def title(card):
    council = _clip(card.get("council") or card.get("opened_by") or "Council not stated", 60)
    return "Rest centre live on helpmap.uk: %s - %s [erc:%s]" % (council, _clip(card.get("name") or "Rest centre"), card_key(card))


def body(card, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    q = card.get("postcode") or card.get("address") or ""
    link = SITE + "/" + ("?q=" + re.sub(r"\s+", "+", str(q).strip()) if q else "")
    run = ""
    if os.environ.get("GITHUB_RUN_ID") and os.environ.get("GITHUB_REPOSITORY"):
        run = "%s/%s/actions/runs/%s" % (os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
                                         os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_RUN_ID"])
    lines = [
        "A council rest centre has just been put on the live helpmap.uk map (incident_rest_centre_live.json).",
        "",
        "**Council:** %s" % (card.get("council") or card.get("opened_by") or "not stated"),
        "**Place:** %s" % (card.get("name") or "not stated"),
        "**Address:** %s" % (card.get("address") or card.get("postcode") or "not stated"),
        "**Opened for:** %s" % (card.get("opened_for") or "not stated"),
        "**Open until:** %s" % (card.get("open_until_label") or card.get("open_until") or "not stated"),
        "**Area code (shown to visitors in):** %s" % (card.get("lad") or "none - nobody will see it"),
        "**Council page:** %s" % (card.get("source_url") or "not stated"),
        "**Map:** %s" % link,
        "**Published (UK):** %s" % now.astimezone(ZoneInfo("Europe/London")).strftime("%d %b %Y %H:%M"),
    ]
    if run:
        lines.append("**Run:** %s" % run)
    lines += ["", "Check the card on the live site. This issue is opened once per rest centre. cc @%s" % OWNER]
    return "\n".join(lines)


def enabled(root=None, env=None):
    env = os.environ if env is None else env
    if env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REF") != "refs/heads/main":
        return False
    if not str(env.get("GH_TOKEN") or "").strip():
        return False
    if (env.get("GITHUB_WORKFLOW") or "").strip().lower() == "tests" or env.get("PYTEST_CURRENT_TEST"):
        return False
    if env.get("GITHUB_REPOSITORY") and env.get("GITHUB_REPOSITORY") != OWNER + "/find-your-food-bank":
        return False
    try:
        return os.path.realpath(root or ROOT) == ROOT
    except Exception:
        return False


def _gh(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("gh %s failed (exit %s): %s" % (args[0], r.returncode, (r.stderr or "").strip()[:200]))
    return r.stdout


def _recent(key, issues, now):
    tag = "[erc:%s]" % key
    for i in issues or []:
        if tag not in (i.get("title") or ""):
            continue
        if (i.get("state") or "").upper() == "OPEN":
            return True
        try:
            t = datetime.datetime.fromisoformat(str(i.get("createdAt")).replace("Z", "+00:00"))
        except Exception:
            return True
        if (now - t).total_seconds() < REPEAT_HOURS * 3600:
            return True
    return False


def notify(before, after, root=None, env=None, gh=None, now=None):
    """Open one erc-live issue per newly live real rest centre. Returns a short result; never raises."""
    new = newly_live(before, after)
    if not new:
        return {"opened": 0, "reason": "nothing-new"}
    if gh is None:
        if not enabled(root, env):
            print("erc-live alert: %d new rest centre(s); not a main run, no issue opened" % len(new))
            return {"opened": 0, "reason": "not-main", "new": len(new)}
        gh = _gh
    now = now or datetime.datetime.now(datetime.timezone.utc)
    opened = 0
    try:
        gh("label", "create", LABEL, "--color", "B60205", "--description", "A real rest centre went live on helpmap.uk", "--force")
        issues = json.loads(gh("issue", "list", "--label", LABEL, "--state", "all", "--limit", "200",
                               "--json", "number,title,state,createdAt") or "[]")
        for c in new:
            k = card_key(c)
            if _recent(k, issues, now):
                print("erc-live alert: [erc:%s] already raised, no new issue" % k)
                continue
            gh("issue", "create", "--title", title(c), "--label", LABEL, "--body", body(c, now))
            issues.append({"title": "[erc:%s]" % k, "state": "OPEN"})
            opened += 1
            print("erc-live alert: issue opened for [erc:%s]" % k)
    except Exception as e:
        print("::warning::erc-live alert failed: %s: %s" % (type(e).__name__, e))
        return {"opened": opened, "reason": "error", "error": str(e)}
    return {"opened": opened, "reason": "ok"}
