"""owner, 26 Oct 2026: the owner's name stays out of the repo (code, tests, scripts, docs, reports, logs, data notes).
It is kept only on privacy.html and terms.html, where UK data protection law expects the site operator to be named.
Real place names (Forest of Dean, Dean Street, Dean Castle, East Dean, Goffs Oak, Canolfan Goffa) are allowed."""
import os, re, subprocess, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED_FILES = {'privacy.html', 'terms.html'}
PLACES = re.compile(r'Forest of Dean|East Dean|Dean St\b|Dean Street|Dean Castle|Goffs Oak|Canolfan Goffa', re.I)
FIRST, LAST = 'De' + 'an', 'Go' + 'ff'  # split so this file passes its own check
FIRST_RE = re.compile(r'\b%s\b' % FIRST)
LAST_RE = re.compile(r'\b%s\b' % LAST, re.I)


class NoOwnerName(unittest.TestCase):
    def test_name_not_in_tracked_files(self):
        files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
        bad = []
        for f in files:
            if not f or f in ALLOWED_FILES:
                continue
            if re.search(r'(^|/)[^/]*(_dean|dean_)[^/]*$', f, re.I):
                bad.append(f + ' (file name)')
            try:
                text = open(os.path.join(ROOT, f), encoding='utf-8').read()
            except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                rest = PLACES.sub('', line)
                if FIRST_RE.search(rest) or LAST_RE.search(rest):
                    bad.append('%s:%d' % (f, n))
        self.assertEqual(bad, [], "owner's name found (use 'owner'): %s" % bad[:30])

    def test_privacy_and_terms_still_name_operator(self):
        for f in ALLOWED_FILES:
            self.assertIn('run by %s %s, trading as Postcode Economics' % (FIRST, LAST), open(os.path.join(ROOT, f), encoding='utf-8').read())


if __name__ == '__main__':
    unittest.main()
