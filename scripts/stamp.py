"""Write stamp.js: the UK date+time of this refresh/sweep run. The footer's 'last updated' and
'checked' read it, so every 3x-daily refresh and overnight sweep bakes in its own run time.
Usage: stamp.py write <kind> | stamp.py verify  (verify fails loudly if the stamp is not from this run)."""
import datetime, json, os, sys
from zoneinfo import ZoneInfo
P = os.path.join(os.path.dirname(__file__), '..', 'stamp.js')
def main():
    now = datetime.datetime.now(ZoneInfo('Europe/London'))
    if sys.argv[1] == 'write':
        s = dict(run=now.isoformat(timespec='seconds'), kind=sys.argv[2] if len(sys.argv) > 2 else 'refresh',
                 label=f"{now.day} {now:%B %Y}, {now:%H:%M}")
        open(P, 'w').write('window.FB_STAMP=' + json.dumps(s) + ';\n'); print('stamped', s['label'])
    else:
        s = json.loads(open(P).read().split('=', 1)[1].rstrip().rstrip(';'))
        age = (now - datetime.datetime.fromisoformat(s['run'])).total_seconds()
        if not 0 <= age < 900: sys.exit(f"::error::stamp.js not updated by this run (stamp {s['run']}, age {age:.0f}s)")
        print('stamp ok', s['label'])
main()
