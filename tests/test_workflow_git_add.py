"""Sweep failed 25 Oct 11:41: an escaped space ('\\ reports/...') in a workflow `git add` line made git look for ' reports/...'.
Every `git add` path in every workflow must be a plain path (no backslash-space)."""
import glob, os, unittest
R = os.path.join(os.path.dirname(__file__), '..')
class T(unittest.TestCase):
    def test_no_escaped_space(self):
        bad = []
        for f in glob.glob(os.path.join(R, '.github', 'workflows', '*.yml')):
            for n, l in enumerate(open(f, encoding='utf-8'), 1):
                if 'git add' in l and '\\ ' in l: bad.append('%s:%d' % (os.path.basename(f), n))
        self.assertEqual(bad, [])

    def test_continuations(self):
        """Sweep failed again 12:16: the 'git add' line lost its trailing '\\', so the next line of paths ran as a command."""
        bad = []
        for f in glob.glob(os.path.join(R, '.github', 'workflows', '*.yml')):
            L = open(f, encoding='utf-8').read().split('\n')
            for n, l in enumerate(L[:-1]):
                if 'git add' in l and not l.rstrip().endswith('\\'):
                    nxt = L[n + 1]
                    if len(nxt) - len(nxt.lstrip()) > len(l) - len(l.lstrip()) and nxt.strip().split(' ')[0].endswith(('.json', '.js', '.html', '.md')):
                        bad.append('%s:%d' % (os.path.basename(f), n + 1))
        self.assertEqual(bad, [])
