"""Live Fear Free (Wales) helpline is 0808 80 10 800 (Dean, 28 Oct 2026).

Own site, re-read 1 Nov 2026 00:06 GMT (and 28 Oct 07:02:58 / 07:04:06 UTC): https://www.gov.wales/live-fear-free/contact-live-fear-free
("Call: 0808 80 10 800"); every Live Fear Free page on gov.wales / llyw.cymru that gives a number agrees.
The old number (ending 10 100) was shown and dialled in both languages of the helpline strip and must not come back anywhere.
"""
import os, re, subprocess, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
rd = lambda f: open(os.path.join(R, f), encoding='utf-8').read()
SEP = r'[\s\u00a0\-.()]*'
OLD = re.compile(SEP.join('0808' + '8010' + '100'))  # split so this file never spells the old number itself


class LiveFearFree(unittest.TestCase):
    def test_strip_dials_and_shows_the_own_site_number_in_both_languages(self):
        v3 = rd('v3.js')
        self.assertIn('<li><b>Live Fear Free</b> (Wales): <a href="tel:08088010800" aria-label="Call 0808 80 10 800">0808 80 10 800</a>', v3)
        self.assertIn('<li><b>Byw Heb Ofn</b> (Cymru): <a href="tel:08088010800" aria-label="Ffoniwch 0808 80 10 800">0808 80 10 800</a>', v3)

    def test_old_number_appears_nowhere(self):
        files = subprocess.run(['git', 'ls-files'], cwd=R, capture_output=True, text=True, check=True).stdout.split('\n')
        bad = []
        for f in files:
            if not f: continue
            try: s = open(os.path.join(R, f), encoding='utf-8').read()
            except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError): continue
            if OLD.search(s): bad.append(f)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
