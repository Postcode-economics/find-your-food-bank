"""Read the live build (version.json) the way a visitor's browser does, for the deploy check's wait steps.

Cloudflare Bot Fight Mode (Free plan, on since 27 Oct 2026) answers curl from a CI runner with a 403 "Just a moment..."
challenge (cf-mitigated: challenge) and ignores the helpmap-check WAF skip rule. The deploy wait polled with curl, so it
read '' for 10 min and failed every deploy as "not live", with nothing tested and no word of Cloudflare. Real Chrome with
the check_browser identity is the path the live checks already use, and it is answered with the site.

A 403, a cf-mitigated header, or a "Just a moment" / security verification page is "Cloudflare blocked the live check",
never "deploy not live".

Usage:
  python scripts/live_build.py BASE_URL WANT [TRIES] [PAUSE_S]
    Polls BASE_URL/version.json until its build is WANT (TRIES polls, PAUSE_S apart; default 40 x 15 s = 10 min).
    Prints each poll on stderr and the last build read ('' if none) on stdout.
    Exit 0: live is WANT. Exit 3: the last poll was blocked by Cloudflare. Exit 1: anything else.
  python scripts/live_build.py --scan NAME=LOG ...
    Prints the NAMEs whose check output shows a Cloudflare block (a retry that then passed is not one)."""
import json, os, re, shutil, sys, time
import check_browser as B

BLOCKED = 3
BLOCKED_MSG = 'Cloudflare blocked the live check'
_BLOCK_LINE = re.compile(r'bot page instead of|blocked or challenged|cloudflare (?:blocked|challenge)|cf-mitigated'
                         r'|just a moment|performing security verification|challenge page in place of', re.I)


def chrome_path():
    for path in ('/usr/bin/google-chrome', shutil.which('google-chrome')):
        if path and os.path.exists(path):
            return path
    return None


def classify(status, cf_mitigated, text):
    """(build, blocked, why) for one poll of version.json."""
    if cf_mitigated or status == 403 or B.bot_page('', text or ''):
        return '', True, '%s (HTTP %s, cf-mitigated: %s)' % (BLOCKED_MSG, status or '?', cf_mitigated or 'none')
    if status and status >= 400:
        return '', False, 'HTTP %s' % status
    try:
        build = json.loads(text or '').get('build', '')
    except (ValueError, AttributeError):
        return '', False, 'not JSON: %r' % (text or '')[:80]
    return (build or ''), False, 'build %r' % build


def blocked_in_log(text):
    """True when check output shows a Cloudflare block that was not cleared by the one retry."""
    return any(_BLOCK_LINE.search(line) for line in (text or '').splitlines() if not line.strip().startswith('retry:'))


def scan(pairs):
    hits = []
    for pair in pairs:
        name, _, path = pair.partition('=')
        try:
            text = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        if blocked_in_log(text):
            hits.append(name)
    return hits


def read_once(page, url, log):
    seen = {}

    def on_response(resp):
        try:
            if resp.request.resource_type == 'document' and resp.url.split('?', 1)[0].endswith('/version.json'):
                seen['status'] = resp.status
                seen['cf'] = resp.headers.get('cf-mitigated', '')
        except Exception:
            pass

    page.on('response', on_response)
    error = ''
    try:
        B.goto(page, url, ready=False, log=log)
    except (B.BotPage, B.BlockedPage) as e:
        error = str(e).splitlines()[0][:160]
    except Exception as e:
        error = '%s: %s' % (type(e).__name__, str(e).splitlines()[0][:160])
    finally:
        page.remove_listener('response', on_response)
    try:
        text = page.evaluate("()=>document.body?document.body.innerText:''") or ''
    except Exception:
        text = ''
    build, blocked, why = classify(seen.get('status'), seen.get('cf', ''), text)
    if error and not build:
        why = '%s; %s' % (why, error)
    return build, blocked, why


def main(argv):
    if len(argv) > 1 and argv[1] == '--scan':
        print(' '.join(scan(argv[2:])))
        return 0
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 1
    base, want = argv[1].rstrip('/'), argv[2]
    tries = int(argv[3]) if len(argv) > 3 else 40
    pause = float(argv[4]) if len(argv) > 4 else 15
    log = lambda m: print(m, file=sys.stderr, flush=True)
    chrome = chrome_path()
    if not chrome:
        log('::error::real Chrome (google-chrome) not found; the live build is only read in real Chrome')
        print('')
        return 1
    from playwright.sync_api import sync_playwright
    got, blocked, blocked_polls, polls = '', False, 0, 0
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome)
        context = B.new_context(browser, viewport={'width': 390, 'height': 844})
        page = context.new_page()
        for i in range(1, tries + 1):
            got, blocked, why = read_once(page, '%s/version.json?t=%d' % (base, time.time() * 1000), log)
            polls, blocked_polls = i, blocked_polls + blocked
            log('poll %d/%d: %s' % (i, tries, why))
            if got == want:
                break
            if i < tries:
                time.sleep(pause)
        browser.close()
    if blocked_polls:
        log('::warning::%s on %d of %d polls of version.json' % (BLOCKED_MSG, blocked_polls, polls))
    print(got)
    if got == want:
        return 0
    return BLOCKED if blocked else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
