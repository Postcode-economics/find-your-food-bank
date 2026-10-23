import os, subprocess, sys, tempfile, shutil, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import indexnow as IN
class T(unittest.TestCase):
    def test_changed_ignores_stamps(self):
        d = tempfile.mkdtemp(); g = lambda *a: subprocess.run(['git', '-C', d, '-c', 'user.email=a@b', '-c', 'user.name=a'] + list(a), check=True, capture_output=True)
        os.makedirs(os.path.join(d, 'shelters', 'x')); os.makedirs(os.path.join(d, 'logs'))
        w = lambda r, s: open(os.path.join(d, r), 'w').write(s)
        w('faq.html', '<p>a</p><!--mapchk--><p class="mapchk">Map data last checked on 1 at 01:00</p><!--/mapchk-->')
        w('shelters/x/index.html', '<p>one</p><script type="application/ld+json" data-ld="page">{"dateModified":"1"}</script>')
        w('logs/a.json', '1'); w('0123456789abcdef0123456789abcdef.txt', '0123456789abcdef0123456789abcdef')
        g('init', '-q'); g('add', '.'); g('commit', '-qm', 'a')
        w('faq.html', '<p>a</p><!--mapchk--><p class="mapchk">Map data last checked on 2 at 02:00</p><!--/mapchk-->')
        w('shelters/x/index.html', '<p>two</p><script type="application/ld+json" data-ld="page">{"dateModified":"2"}</script>')
        os.makedirs(os.path.join(d, 'warm-spaces', 'y')); w('warm-spaces/y/index.html', 'new'); w('logs/a.json', '2')
        g('add', '.'); g('commit', '-qm', 'b')
        self.assertEqual(IN.changed('HEAD~1', d), ['https://helpmap.uk/shelters/x/', 'https://helpmap.uk/warm-spaces/y/'])
        self.assertEqual(IN.key(d), '0123456789abcdef0123456789abcdef')
        shutil.rmtree(d)
    def test_main_never_raises(self):
        IN.ping = lambda u, k: (_ for _ in ()).throw(OSError('down'))
        IN.changed = lambda b: ['https://helpmap.uk/']
        IN.main()
