"""Who it's for, how to get in, and wheelchair access (Dean 31 Oct 2026).

The build copies wheelchair only when an override states yes, partial or no.
Cards show the same rows on every layer, and Not stated when a value is missing.
Accessible Toilets stays a facility. It is not turned into wheelchair access.
"""
import json, os, subprocess, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import place_facts
import refresh_guard
import recheck
import compact

NODE = r'''
const fs = require('fs');
const vm = require('vm');
const ctx = {window: {}, document: {documentElement: {lang: 'en'}}, console};
ctx.window = ctx;
ctx.global = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx); } catch (e) {}
ctx.window.timesFmt = ctx.timesFmt;
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), ctx);
const U = ctx.UFacts;
const out = {
  men: U.whoBits({groups: ['Men', 'Age 18+']}).map(x => x[0]).join(' · '),
  ages: U.whoBits({groups: ['Young people 16-25']}).map(x => x[0]).join(' · '),
  dogs: U.whoBits({groups: ['Families'], provided: ['Dog Friendly', 'Accessible Toilets']}).map(x => x[0]).join(' · '),
  couples: U.whoBits({groups: ['Couples without children', 'Age 16+']}).map(x => x[0]).join(' · '),
  emptyWho: U.whoHtml({}),
  types: {
    fb: U.typeOf('fb', {}),
    ws: U.typeOf('ws', {}),
    day: U.typeOf('sh', {kind: 'day_centre'}),
    hostel: U.typeOf('sh', {name: 'Bradford Cyrenians - Hostel for Homeless Men'}),
    ref: U.typeOf('sh', {name: 'Union Terrace Hostel', access_type: 'referral_only'}),
    foyer: U.typeOf('sh', {name: 'Camberwell Foyer'}),
    night: U.typeOf('sh', {name: 'Hastings Night Shelter'})
  },
  winter: U.typeRow('sh', {name: 'Barnet Winter Night Shelter', season: 'Winter-only'}),
  how: {
    v: U.howPair('fb', {id: 'a'}, {access: 'voucher'}),
    w: U.howPair('fb', {id: 'a'}, {access: 'walkin'}),
    u: U.howPair('fb', {id: 'a'}, {access: 'unconfirmed'}),
    ref: U.howPair('sh', {access_type: 'referral_only', referral: 'Referral only: Via HAB'}),
    self: U.howPair('sh', {access_type: 'self_referral'}),
    walk: U.howPair('sh', {access_type: 'open_access'})
  },
  wheel: ['yes', 'partial', 'no', '', undefined].map(w => U.wheelPair({wheelchair: w})),
  toilets: U.wheelPair({provided: ['Accessible Toilets']}),
  card: U.block('sh', {name: 'A Night Shelter', groups: ['Men', 'Age 18+'], access_type: 'referral_only', referral: 'Referral only: Via the council', wheelchair: 'yes', hours: {Mon: '17:00 - 10:00'}, provided: ['Accessible Toilets', 'Showers']}),
  bare: U.block('ws', {name: 'Hub', hours: {}}),
  checked: U.checked({last_verified: '2026-10-31'}),
  times: U.timesLines('fb', {opening_times: {status: 'TIMES_TEXT_ONLY', lines: ['Monday - 12:30 - 2.30pm']}})
};
process.stdout.write(JSON.stringify(out));
'''


def render():
    r = subprocess.run(['node', '-e', NODE, os.path.join(ROOT, 'v3.js'), os.path.join(ROOT, 'facts.js')],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


class Data(unittest.TestCase):
    def test_copy_only_a_stated_value(self):
        dest = {}
        self.assertTrue(place_facts.copy_wheelchair(dest, {
            'wheelchair': 'partial', 'wheelchair_quote': 'One step at the door', 'wheelchair_source': 'https://example.org/a'}))
        self.assertEqual(dest['wheelchair'], 'partial')
        self.assertEqual(dest['wheelchair_quote'], 'One step at the door')
        self.assertEqual(dest['wheelchair_source'], 'https://example.org/a')
        kept = dict(dest)
        self.assertFalse(place_facts.copy_wheelchair(kept, {'provided': ['Accessible Toilets']}))
        self.assertEqual(kept['wheelchair'], 'partial')
        self.assertFalse(place_facts.copy_wheelchair({}, {'wheelchair': 'maybe'}))
        self.assertFalse(place_facts.copy_wheelchair({}, {}))

    def test_stamp_does_not_infer_toilets_or_overwrite_groups(self):
        items = [{'id': 'w', 'provided': ['Accessible Toilets']}, {'id': 's', 'groups': ['Women']}]
        n = place_facts.stamp(items, {
            'w': {'provided': ['Accessible Toilets'], 'groups': ['Families']},
            's': {'groups': ['Men'], 'wheelchair': 'no', 'wheelchair_source': 'https://example.org/s'},
            'missing': {'wheelchair': 'yes'},
        }, fill_missing=True)
        self.assertEqual(n, 1)
        self.assertNotIn('wheelchair', items[0])
        self.assertEqual(items[0]['groups'], ['Families'])
        self.assertEqual(items[1]['groups'], ['Women'])
        self.assertEqual(items[1]['wheelchair'], 'no')
        self.assertEqual(items[1]['wheelchair_source'], 'https://example.org/s')

    def test_refresh_keeps_a_stated_wheelchair(self):
        old = [{'id': 's', 'name': 'S', 'lat': 1, 'lng': 1, 'wheelchair': 'yes', 'wheelchair_quote': 'Level entrance', 'wheelchair_source': 'https://example.org/q'}]
        new = [{'id': 's', 'name': 'S', 'lat': 1, 'lng': 1}]
        out, rep = refresh_guard.guard('shelters', old, new)
        self.assertEqual(out[0]['wheelchair'], 'yes')
        self.assertEqual(out[0]['wheelchair_quote'], 'Level entrance')
        self.assertEqual(out[0]['wheelchair_source'], 'https://example.org/q')
        self.assertEqual(rep['wheelchair'], ['s'])

    def test_schema_accepts_only_the_three_values(self):
        base = {'name': 'N', 'lat': 51.5, 'lng': -0.1, 'postcode': 'N1 1AA', 'address': '1 Road'}
        self.assertEqual(recheck.schema_errors(dict(base), 'sh'), [])
        for w in ('yes', 'partial', 'no'):
            self.assertEqual(recheck.schema_errors(dict(base, wheelchair=w), 'ws'), [])
        self.assertIn('wheelchair invalid', recheck.schema_errors(dict(base, wheelchair='maybe'), 'fb'))

    def test_builds_carry_the_field(self):
        for name in ('build.py', 'build_shelters.py', 'build_warmspaces.py'):
            src = open(os.path.join(ROOT, 'scripts', name), encoding='utf-8').read()
            self.assertIn('place_facts.stamp', src, name)
        ws = open(os.path.join(ROOT, 'scripts', 'build_warmspaces.py'), encoding='utf-8').read()
        self.assertIn('Accessible Toilets', ws)
        self.assertNotIn('wheelchair', ws.split('place_facts')[0])

    def test_compact_round_trip_and_blank_column_omitted(self):
        meta = {'fetched': '2026-10-31', 'source': 's', 'items': [
            {'id': 'a', 'name': 'A', 'wheelchair': 'yes', 'wheelchair_quote': 'step-free', 'wheelchair_source': 'https://a.example'},
            {'id': 'b', 'name': 'B'}]}
        raw = compact.encode(meta)
        data = json.JSONDecoder().raw_decode(raw[raw.rindex('})(') + 3:])[0]
        self.assertEqual(data['c']['wheelchair'], ['yes'])
        self.assertEqual(data['c']['wheelchair_quote'][0], 'step-free')
        self.assertEqual(data['c']['wheelchair_source'], ['https://a.example'])
        bare = compact.encode({'fetched': '2026-10-31', 'source': 's', 'items': [{'id': 'a', 'name': 'A'}]})
        data2 = json.JSONDecoder().raw_decode(bare[bare.rindex('})(') + 3:])[0]
        self.assertNotIn('wheelchair', data2['k'])
        self.assertIn('name', data2['k'])


class Cards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = render()

    def test_who_line(self):
        self.assertEqual(self.r['men'], 'Men only · Age 18+')
        self.assertEqual(self.r['ages'], 'Young people 16-25')
        self.assertEqual(self.r['dogs'], 'Families · Dogs welcome')
        self.assertEqual(self.r['couples'], 'Couples without children · Age 16+')
        self.assertEqual(self.r['emptyWho'], '')

    def test_types_and_winter_badge(self):
        self.assertEqual(self.r['types']['fb'], ['Food bank', 'Banc bwyd'])
        self.assertEqual(self.r['types']['ws'], ['Warm space', 'Man cynnes'])
        self.assertEqual(self.r['types']['day'], ['Day centre', 'Canolfan ddydd'])
        self.assertEqual(self.r['types']['hostel'][0], 'Hostel')
        self.assertEqual(self.r['types']['ref'], ['Referral hostel', 'Hostel drwy atgyfeiriad'])
        self.assertEqual(self.r['types']['foyer'][0], "Young people's housing (16-25)")
        self.assertEqual(self.r['types']['night'], ['Night shelter', 'Lloches nos'])
        self.assertIn('Winter-only', self.r['winter'])
        self.assertIn('Gaeaf yn unig', self.r['winter'])

    def test_how_and_wheelchair_wording(self):
        self.assertEqual(self.r['how']['v'], ['Voucher', 'Taleb'])
        self.assertEqual(self.r['how']['w'], ['Walk-in', 'Galw heibio'])
        self.assertIsNone(self.r['how']['u'])
        self.assertEqual(self.r['how']['ref'][0], 'Referral via HAB')
        self.assertEqual(self.r['how']['self'][0], 'Self-referral')
        self.assertEqual(self.r['how']['walk'][0], 'Walk-in')
        self.assertEqual(self.r['wheel'][0][1], 'Hygyrch i gadeiriau olwyn')
        self.assertEqual(self.r['wheel'][1][1], 'Rhannol hygyrch i gadeiriau olwyn')
        self.assertEqual(self.r['wheel'][2][1], 'Ddim yn hygyrch i gadeiriau olwyn')
        self.assertIsNone(self.r['wheel'][3])
        self.assertIsNone(self.r['wheel'][4])
        self.assertIsNone(self.r['toilets'])

    def test_rows_present_and_bare_card_says_not_stated(self):
        card = self.r['card']
        for label in ('Who it’s for', 'How to get in', 'Opening times', 'Wheelchair access', 'Facilities'):
            self.assertIn(label, card)
        self.assertIn('I bwy mae hwn', card)
        self.assertIn('Sut i fynd i mewn', card)
        self.assertIn('Oriau agor', card)
        self.assertIn('Mynediad i gadeiriau olwyn', card)
        self.assertIn('Cyfleusterau', card)
        self.assertIn('Men only', card)
        self.assertIn('Hygyrch i gadeiriau olwyn', card)
        self.assertIn('Toilets', card)
        self.assertIn('Toiledau', card)
        self.assertIn('class="ot"', card)
        self.assertIn('17:00–10:00', card)
        self.assertNotIn('22:00', card)
        bare = self.r['bare']
        self.assertEqual(bare.count('Not stated'), 5)
        self.assertEqual(bare.count('Heb ei nodi'), 5)
        self.assertNotIn('Wheelchair accessible', bare)
        self.assertIn('31 Oct 2026', self.r['checked'])
        self.assertIn('31 Hydref 2026', self.r['checked'])
        self.assertEqual(self.r['times'], ['Mon 12:30–14:30'])

    def test_script_tag_matches_the_file(self):
        import hashlib
        h = 'h' + hashlib.sha256(open(os.path.join(ROOT, 'facts.js'), 'rb').read()).hexdigest()[:12]
        home = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
        sw = open(os.path.join(ROOT, 'sw.js'), encoding='utf-8').read()
        self.assertIn('facts.js?v=' + h, home)
        self.assertIn('facts.js?v=' + h, sw)
        lh = 'h' + hashlib.sha256(open(os.path.join(ROOT, 'layers.js'), 'rb').read()).hexdigest()[:12]
        self.assertIn('layers.js?v=' + lh, home)
        self.assertIn('layers.js?v=' + lh, sw)
