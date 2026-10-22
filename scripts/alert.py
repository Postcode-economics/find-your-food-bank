"""Make workflow problems visible (risk pack DA3/TS, 22 Oct 2026).
alert.py open  <key> <title> <body>  -> open a GitHub issue labelled 'refresh-alert' for <key>, or comment on the open one
alert.py resolve <key>               -> close the open issue for <key> with a note (the next good run clears it)
alert.py stale <hours>               -> open an alert if stamp.js (last published refresh/sweep) is older than <hours>
Uses the gh CLI with GH_TOKEN (the workflow's own token). Also writes a line to the job summary. Never fails the job itself."""
import datetime, json, os, subprocess, sys
from zoneinfo import ZoneInfo
LABEL = 'refresh-alert'
RUN = f"{os.environ.get('GITHUB_SERVER_URL','https://github.com')}/{os.environ.get('GITHUB_REPOSITORY','')}/actions/runs/{os.environ.get('GITHUB_RUN_ID','')}"
def gh(*a):
    return subprocess.run(['gh', *a], capture_output=True, text=True)
def summary(line):
    p = os.environ.get('GITHUB_STEP_SUMMARY')
    if p:
        with open(p, 'a') as f: f.write(line + '\n')
    print(line)
def find(key):
    r = gh('issue', 'list', '--label', LABEL, '--state', 'open', '--json', 'number,title', '--limit', '50')
    try: return next((i['number'] for i in json.loads(r.stdout or '[]') if f'[{key}]' in i['title']), None)
    except Exception: return None
def open_(key, title, body):
    gh('label', 'create', LABEL, '--color', 'B60205', '--description', 'Automatic refresh/sweep problem', '--force')
    body = f"{body}\n\nRun: {RUN}\nTime (UK): {datetime.datetime.now(ZoneInfo('Europe/London')):%d %b %Y %H:%M}"
    n = find(key)
    r = gh('issue', 'comment', str(n), '--body', body) if n else gh('issue', 'create', '--title', f'[{key}] {title}', '--label', LABEL, '--body', body)
    summary(f"ALERT [{key}] {title} -> issue {'#'+str(n) if n else 'created'} ({'ok' if r.returncode == 0 else 'gh failed: ' + r.stderr.strip()[:200]})")
def resolve(key):
    n = find(key)
    if n: gh('issue', 'close', str(n), '--comment', f'Resolved: the next run succeeded. {RUN}')
    summary(f"OK [{key}]" + (f" (closed #{n})" if n else ''))
def stale(hours):
    s = json.loads(open(os.path.join(os.path.dirname(__file__), '..', 'stamp.js')).read().split('=', 1)[1].rstrip().rstrip(';'))
    age = (datetime.datetime.now(ZoneInfo('Europe/London')) - datetime.datetime.fromisoformat(s['run'])).total_seconds() / 3600
    if age > hours: open_('stale', f'No refresh published for {age:.1f} hours', f"The last published run was {s['label']} ({s['kind']}). Check the Actions tab: a refresh may be failing or disabled.")
    else: resolve('stale')
if __name__ == '__main__':
    try:
        c = sys.argv[1]
        if c == 'open': open_(sys.argv[2], sys.argv[3], sys.argv[4])
        elif c == 'resolve': resolve(sys.argv[2])
        elif c == 'stale': stale(float(sys.argv[2]))
    except Exception as e:
        print('alert.py problem (ignored):', e)
