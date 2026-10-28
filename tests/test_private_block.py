"""Rule 9. Dummy address and phone only. The real values stay in the PRIVATE_BLOCKLIST secret."""
import io, json, os, re, shutil, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import private_block, publish_gate as pg, validate

ADDR = '99 Dummy Lane, Exampletown EX1 1EX'
PHONE = '01000 000000'
PHONE_DIGITS = '01000000000'
ROOT = os.path.join(os.path.dirname(__file__), '..')


def _item():
    return dict(id='dummy-home', name='Private', address=ADDR, phone=PHONE, tel=PHONE_DIGITS,
                postcode='EX1 1EX', website='https://example.test/private')


class Entries(unittest.TestCase):
    def tearDown(self):
        os.environ.pop('PRIVATE_BLOCKLIST', None)

    def test_unset_matches_nothing(self):
        os.environ.pop('PRIVATE_BLOCKLIST', None)
        self.assertEqual(private_block.entries(), [])
        self.assertFalse(private_block.matches(_item()))
        self.assertEqual(private_block.match_count([_item()]), 0)

    def test_address_and_phone_match_and_short_entries_do_not(self):
        secrets = [ADDR, PHONE, 'EX1', '01234']
        self.assertTrue(private_block.matches({'address': '99 dummy lane, exampletown ex1 1ex'}, secrets))
        self.assertTrue(private_block.matches({'tel': PHONE_DIGITS}, secrets))
        self.assertFalse(private_block.matches({'address': '1 Other Road', 'phone': '020 7946 0000'}, secrets))
        self.assertFalse(private_block.matches({'name': 'EX1', 'postcode': 'EX1 2AB'}, ['EX1', '01234']))
        self.assertEqual(private_block.match_count([{'tel': PHONE_DIGITS}, {'id': 'ok', 'phone': '02079460000'}], secrets), 1)
        # Same needles as scripts/privacy_check.py: postcode spacing and +44 / 0044.
        self.assertTrue(private_block.matches({'address': '99 Dummy Lane Exampletown EX11EX'}, secrets))
        self.assertTrue(private_block.matches({'phone': '+44 1000 000 000'}, secrets))
        self.assertTrue(private_block.matches({'phone': '0044 1000 000000'}, secrets))

    def test_how_to_set_the_secret_is_documented_and_not_a_value_in_the_repo(self):
        doc = open(private_block.__file__, encoding='utf-8').read()
        self.assertIn('PRIVATE_BLOCKLIST', doc)
        self.assertIn('Settings → Secrets and variables → Actions', doc)
        self.assertIn('one address or phone per line', doc)
        self.assertIn('01000 000000', doc)  # documented shape is a dummy, not a real number
        for name in ('refresh.yml', 'refresh-shelters.yml', 'refresh-warmspaces.yml'):
            text = open(os.path.join(ROOT, '.github', 'workflows', name), encoding='utf-8').read()
            self.assertIn('PRIVATE_BLOCKLIST: ${{ secrets.PRIVATE_BLOCKLIST }}', text, name)
            self.assertIn('scripts/private_block.py', text, name)
            self.assertGreaterEqual(text.count('PRIVATE_BLOCKLIST: ${{ secrets.PRIVATE_BLOCKLIST }}'), 3, name)
            # The publish step and the severe-failure gate both stop the job. Neither is continue-on-error.
            blocking = [s for s in re.split(r'\n(?=      - name:)', text)
                        if 'python scripts/publish_gate.py' in s or 'python scripts/validate.py gate' in s]
            self.assertGreaterEqual(len(blocking), 3, name)
            for step in blocking:
                self.assertNotIn('continue-on-error', step, name)
                self.assertIn('PRIVATE_BLOCKLIST: ${{ secrets.PRIVATE_BLOCKLIST }}', step, name)


class Gate(unittest.TestCase):
    def tearDown(self):
        os.environ.pop('PRIVATE_BLOCKLIST', None)

    def _repo(self, items, git=True):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for sub in ('logs', 'reports', 'overrides'):
            os.makedirs(os.path.join(d, sub))
        open(os.path.join(d, 'data.full.js'), 'w').write('window.FB_DATA=' + json.dumps({'items': items}) + ';')
        if git:
            run = lambda *a: subprocess.run(a, cwd=d, check=True, capture_output=True)
            run('git', 'init', '-q')
            run('git', 'add', '-A')
            run('git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base')
        return d

    def test_a_match_is_held_back_and_the_secret_is_not_copied(self):
        d = self._repo([_item(), dict(id='other', name='Other', tel='02079460000')])
        os.environ['PRIVATE_BLOCKLIST'] = ADDR + '\n' + PHONE
        old = pg.ROOT
        pg.ROOT = d
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                held = pg.gate('foodbanks')
        finally:
            pg.ROOT = old
        self.assertTrue(pg.gate.last_privacy)
        self.assertEqual([i['id'] for i, _ in held], ['dummy-home'])
        ids = [i['id'] for i in pg.split(open(os.path.join(d, 'data.full.js')).read())[1]['items']]
        self.assertEqual(ids, ['other'])
        blob = open(os.path.join(d, 'reports', 'pending_dean.md'), encoding='utf-8').read()
        blob += json.dumps(json.load(open(os.path.join(d, 'logs', 'pending_dean.json'))))
        out = buf.getvalue()
        blob += out
        self.assertNotIn('99 Dummy', blob)
        self.assertNotIn('01000', blob)
        self.assertNotIn(PHONE_DIGITS, blob)
        self.assertIn('private details', blob)
        self.assertIn('dummy-home', blob)
        self.assertRegex(out, r'PRIVATE_BLOCKLIST matched 1 listing\(s\)')
        self.assertNotIn(ADDR, out)
        self.assertNotIn(PHONE, out)
        self.assertNotIn('dummy-home', out)
        src = open(pg.__file__, encoding='utf-8').read()
        self.assertIn('sys.exit(1 if gate.last_privacy else 0)', src)

    def test_no_baseline_still_holds_a_match_when_the_secret_is_set(self):
        d = self._repo([_item()], git=False)
        os.environ['PRIVATE_BLOCKLIST'] = ADDR
        old = pg.ROOT
        pg.ROOT = d
        try:
            held = pg.gate('foodbanks')
        finally:
            pg.ROOT = old
        self.assertTrue(pg.gate.last_privacy)
        self.assertEqual(pg.split(open(os.path.join(d, 'data.full.js')).read())[1]['items'], [])
        self.assertEqual([i['id'] for i, _ in held], ['dummy-home'])

    def test_check_fails_closed_for_a_food_bank_without_printing_the_secret(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        body = lambda items: 'window.X=' + json.dumps({'items': items}) + ';'
        open(os.path.join(d, 'data.full.js'), 'w').write(body([_item()]))
        open(os.path.join(d, 'shelters.js'), 'w').write(body([dict(id='s', tel='01', groups=['Men'])]))
        open(os.path.join(d, 'warmspaces.js'), 'w').write(body([dict(id='w', tel='01')]))
        os.environ['PRIVATE_BLOCKLIST'] = PHONE
        old = pg.ROOT
        pg.ROOT = d
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pg.check()
        finally:
            pg.ROOT = old
        out = buf.getvalue()
        self.assertEqual(code, 1)
        self.assertIn('private blocklist', out)
        self.assertRegex(out, r'foodbanks: 1 private blocklist')
        self.assertNotIn(PHONE, out)
        self.assertNotIn(PHONE_DIGITS, out)
        self.assertNotIn(ADDR, out)
        self.assertNotIn('dummy-home', out)

    def test_validate_gate_fails_closed_and_the_message_has_no_secret(self):
        text = 'window.X=' + json.dumps({'items': [_item()]}) + ';'
        os.environ['PRIVATE_BLOCKLIST'] = ADDR + '|' + PHONE
        bad = validate.gate({'foodbanks': text}, {'foodbanks': text})
        self.assertIn('PRIVATE_BLOCKLIST', bad['foodbanks'])
        self.assertRegex(bad['foodbanks'], r'\(1 listing\(s\) not published\)')
        self.assertNotIn('99 Dummy', bad['foodbanks'])
        self.assertNotIn('01000', bad['foodbanks'])
        os.environ.pop('PRIVATE_BLOCKLIST')
        self.assertEqual(validate.gate({'foodbanks': text}, {'foodbanks': text}), {})

    def test_validate_report_writes_a_count_and_not_the_secret(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        os.makedirs(os.path.join(d, 'reports'))
        open(os.path.join(d, 'data.full.js'), 'w').write('window.X=' + json.dumps({'items': [_item()]}) + ';')
        os.environ['PRIVATE_BLOCKLIST'] = ADDR + '\n' + PHONE
        old = validate.ROOT
        validate.ROOT = d
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                validate.main()
        finally:
            validate.ROOT = old
        report = open(os.path.join(d, 'reports', 'validation.md'), encoding='utf-8').read()
        report += open(os.path.join(d, 'reports', 'validation.json'), encoding='utf-8').read()
        out = buf.getvalue() + report
        self.assertRegex(out, r'PRIVATE_BLOCKLIST matched 1 listing')
        self.assertIn('1 listing(s) matched (values not shown)', report)
        self.assertNotIn('99 Dummy', out)
        self.assertNotIn('01000', out)
        self.assertNotIn(PHONE_DIGITS, out)
        self.assertNotIn('dummy-home', out)


if __name__ == '__main__':
    unittest.main()
