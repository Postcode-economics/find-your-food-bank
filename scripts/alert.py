"""Make workflow problems visible (risk pack DA3/TS, 22 Oct 2026).
alert.py open  <key> <title> <body>  -> open a GitHub issue labelled 'refresh-alert' for <key>, or comment on the open one
alert.py resolve <key>               -> close the open issue for <key> with a note (the next good run clears it)
alert.py stale <hours>               -> open an alert if stamp.js (last published refresh/sweep) is older than <hours>
alert.py dates                       -> open an alert if the dates the site shows (stamp.js layers, live stamp.js) don't match the published data files
Uses the gh CLI with GH_TOKEN (the workflow's own token). Also writes a line to the job summary.
Exits non-zero when gh fails or anything else goes wrong: an alert that could not be raised or cleared must show as a failed step."""
import datetime, json, os, subprocess, sys
from zoneinfo import ZoneInfo
LABEL = 'refresh-alert'
RUN = f"{os.environ.get('GITHUB_SERVER_URL','https://github.com')}/{os.environ.get('GITHUB_REPOSITORY','')}/actions/runs/{os.environ.get('GITHUB_RUN_ID','')}"
class AlertError(Exception): pass
def gh(*a):
    r = subprocess.run(['gh', *a], capture_output=True, text=True)
    if r.returncode != 0:
        raise AlertError(f"gh {a[0]} {a[1]} failed (exit {r.returncode}): {r.stderr.strip()[:300]}")
    return r
def summary(line):
    p = os.environ.get('GITHUB_STEP_SUMMARY')
    if p:
        with open(p, 'a') as f: f.write(line + '\n')
    print(line)
def find(key):
    # Unreadable output must not look like 'no open issue': that opened duplicates and never closed the real one.
    r = gh('issue', 'list', '--label', LABEL, '--state', 'open', '--json', 'number,title', '--limit', '1000')
    return next((i['number'] for i in json.loads(r.stdout or '[]') if f'[{key}]' in i['title']), None)
def open_(key, title, body):
    gh('label', 'create', LABEL, '--color', 'B60205', '--description', 'Automatic refresh/sweep problem', '--force')
    body = f"{body}\n\nRun: {RUN}\nTime (UK): {datetime.datetime.now(ZoneInfo('Europe/London')):%d %b %Y %H:%M}"
    n = find(key)
    try:
        gh('issue', 'comment', str(n), '--body', body) if n else gh('issue', 'create', '--title', f'[{key}] {title}', '--label', LABEL, '--body', body)
    except AlertError as e:
        summary(f"ALERT [{key}] {title} -> NOT raised: {e}")
        raise
    summary(f"ALERT [{key}] {title} -> issue {'#'+str(n) if n else 'created'} (ok)")
def resolve(key):
    n = find(key)
    if n: gh('issue', 'close', str(n), '--comment', f'Resolved: the next run succeeded. {RUN}')
    summary(f"OK [{key}]" + (f" (closed #{n})" if n else ''))
def stale(hours):
    s = json.loads(open(os.path.join(os.path.dirname(__file__), '..', 'stamp.js')).read().split('=', 1)[1].rstrip().rstrip(';'))
    age = (datetime.datetime.now(ZoneInfo('Europe/London')) - datetime.datetime.fromisoformat(s['run'])).total_seconds() / 3600
    if age > hours: open_('stale', f'No refresh published for {age:.1f} hours', f"The last published run was {s['label']} ({s['kind']}). Check the Actions tab: a refresh may be failing or disabled.")
    else: resolve('stale')
def date_problems(root=None, live=None):
    """Dean 25 Oct: the shown dates come from stamp.js layers; they must match each layer's data file and the live site."""
    import re
    root = root or os.path.join(os.path.dirname(__file__), '..')
    rd = lambda f: open(os.path.join(root, f), encoding='utf-8').read()
    s = json.loads(rd('stamp.js').split('=', 1)[1].rstrip().rstrip(';')); L = s.get('layers') or {}; out = []
    data = {'fb': re.search(r'\{"f":"(\d{4}-\d\d-\d\d)"', rd('data.js')), 'sh': re.search(r'"updated":"(\d{4}-\d\d-\d\d)"', rd('shelters.js')[:200]), 'ws': re.search(r'"updated":"(\d{4}-\d\d-\d\d)"', rd('warmspaces.js')[:200])}
    for k, m in data.items():
        if k not in L: out.append(f'stamp.js has no {k} date'); continue
        if m and L[k]['run'][:10] < m.group(1): out.append(f"{k}: shown date {L[k]['run'][:10]} is older than its data ({m.group(1)})")
    if live is not None:
        try:
            ls = json.loads(live.split('=', 1)[1].rstrip().rstrip(';'))
            age = (datetime.datetime.fromisoformat(s['run']) - datetime.datetime.fromisoformat(ls['run'])).total_seconds() / 60
            if age > 30: out.append(f"live stamp.js ({ls['label']}) is {age:.0f} min behind main ({s['label']})")
        except Exception as e: out.append(f'live stamp.js unreadable: {e}')
    return out
def dates():
    import urllib.request
    try: live = urllib.request.urlopen(urllib.request.Request(f'https://helpmap.uk/stamp.js?t={int(datetime.datetime.now().timestamp())}', headers={'User-Agent': 'helpmap-watchdog/1.0 (+https://helpmap.uk)'}), timeout=20).read().decode()
    except Exception as e: live = f'x=unreadable {e}'
    p = date_problems(live=live)
    if p: open_('dates', 'Shown dates do not match the published data', '\n'.join('- ' + x for x in p))
    else: resolve('dates')
def main(argv):
    c = argv[1] if len(argv) > 1 else ''
    if c == 'open': open_(argv[2], argv[3], argv[4])
    elif c == 'resolve': resolve(argv[2])
    elif c == 'stale': stale(float(argv[2]))
    elif c == 'dates': dates()
    else: raise AlertError(f'unknown command {c!r} (open, resolve, stale, dates)')
if __name__ == '__main__':
    try: main(sys.argv)
    except Exception as e:
        print(f'::error::alert.py failed: {type(e).__name__}: {e}', file=sys.stderr)
        sys.exit(1)
