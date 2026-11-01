"""Shelter type chips must match published shelters.js (Dean hotfix).

Each filter chip alone shows only matching places in the nearest list and on the map
(markers only for matches with pins; no-pin town cards stay in the list).
"""
import json, os, re, sys, unittest

ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))


def _items():
    text = open(os.path.join(ROOT, 'shelters.js'), encoding='utf-8').read()
    return json.loads(text[text.index('=') + 1:].rstrip().rstrip(';'))['items']


def _youth_blob(i):
    wf = i.get('who_for')
    wf_s = ' '.join(wf) if isinstance(wf, list) else str(wf or '')
    return re.sub(r'\s+', ' ', ' '.join([str(i.get('name') or ''), ' '.join(i.get('groups') or []), wf_s]))


def is_youth(i):
    if i.get('kind') == 'young_people':
        return True
    name = str(i.get('name') or '')
    blob = _youth_blob(i)
    if re.search(r'\bfoyers?\b', blob, re.I):
        return True
    if re.search(r'\byoung people\b', blob, re.I):
        return True
    if re.search(r'\byouth\b', blob, re.I):
        return True
    if re.search(r'Age\s*16\s*[-–]\s*25', blob, re.I):
        return True
    if re.search(r'16\s*[-–to]{1,3}\s*25', blob, re.I):
        return True
    if re.search(r'1[678]\s*[-–to]{1,3}\s*2[0-9]', blob, re.I):
        return True
    if re.search(r'\bhousing\b', name, re.I) and re.search(r'16\s*[-–to]{1,3}\s*25', blob, re.I):
        return True
    if re.search(r"young people'?s housing", blob, re.I):
        return True
    return False


def is_day_centre(i):
    if is_youth(i):
        return False
    kind = str(i.get('kind') or i.get('service') or '').lower().replace('-', ' ').replace('_', ' ')
    return i.get('label') == 'Day centre' or kind == 'day centre'


def is_hostel(i):
    return not is_day_centre(i) and not is_youth(i)


def shelter_type_ok(i, day, youth, hostel):
    if not day and not youth and not hostel:
        return True
    if day and is_day_centre(i):
        return True
    if youth and is_youth(i):
        return True
    return bool(hostel and is_hostel(i))


def list_eligible(i):
    if i.get('card_type') == 'referral_hostel':
        return False
    if not isinstance(i.get('lat'), (int, float)) or not isinstance(i.get('lng'), (int, float)):
        return False
    return True


def map_pin_eligible(i):
    return list_eligible(i) and not i.get('no_pin')


class LiveShelterChips(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = _items()
        cls.listable = [i for i in cls.items if list_eligible(i)]
        cls.pinned = [i for i in cls.items if map_pin_eligible(i)]

    def test_partition_every_listable_place_one_type(self):
        for i in self.listable:
            n = sum((is_youth(i), is_day_centre(i), is_hostel(i)))
            self.assertEqual(n, 1, (i['id'], i.get('name')))

    def test_chip_counts_match_data(self):
        cases = (
            ('hostel', False, False, True, is_hostel),
            ('youth', False, True, False, is_youth),
            ('day', True, False, False, is_day_centre),
        )
        for name, day, youth, hostel, fn in cases:
            data_n = sum(1 for i in self.listable if fn(i))
            chip_n = sum(1 for i in self.listable if shelter_type_ok(i, day, youth, hostel))
            self.assertEqual(chip_n, data_n, '%s chip list count' % name)
            pin_n = sum(1 for i in self.pinned if fn(i))
            shown_pins = sum(1 for i in self.pinned if shelter_type_ok(i, day, youth, hostel))
            self.assertEqual(shown_pins, pin_n, '%s chip pin count' % name)

    def test_youth_includes_groups_and_foyer(self):
        ids = {i['id'] for i in self.items if is_youth(i)}
        for need in (
            'man-nightsafe-blackburn',
            'man-new-horizon-youth-centre',
            'man-brighton-hove-foyer',
            'scni-glen-road-belfast',
        ):
            self.assertIn(need, ids, need)

    def test_each_chip_keeps_pins(self):
        cases = (
            ('hostel', False, False, True),
            ('youth', False, True, False),
            ('day', True, False, False),
        )
        for name, day, youth, hostel in cases:
            n = sum(1 for i in self.pinned if shelter_type_ok(i, day, youth, hostel))
            self.assertGreater(n, 0, '%s chip would hide every pin (%d mappable)' % (name, len(self.pinned)))

    def test_union_when_two_chips(self):
        day_n = sum(1 for i in self.pinned if is_day_centre(i))
        youth_n = sum(1 for i in self.pinned if is_youth(i))
        n = sum(1 for i in self.pinned if shelter_type_ok(i, True, True, False))
        self.assertEqual(n, day_n + youth_n)

    def test_none_pressed_shows_all_pins(self):
        n = sum(1 for i in self.pinned if shelter_type_ok(i, False, False, False))
        self.assertEqual(n, len(self.pinned))

    def test_footer_key_row_order_in_layers_js(self):
        js = open(os.path.join(ROOT, 'layers.js'), encoding='utf-8').read()
        fb = js.index("keyRow(symSvg('food',20)")
        ws = js.index("keyRow(symSvg('flame',20)")
        sh = js.index("keyRow(symSvg('house',20),'sh'")
        day = js.index("keyRow(symSvg('sun',20),'dayCentre'")
        youth = js.index("keyRow(symSvg('youth',20),'youth'")
        self.assertLess(fb, ws, 'food banks before warm spaces')
        self.assertLess(ws, sh, 'warm spaces before shelters')
        self.assertLess(sh, day, 'shelters before day centre')
        self.assertLess(day, youth, 'day centre before youth')

    def test_layers_symkey_youth_before_day(self):
        js = open(os.path.join(ROOT, 'layers.js'), encoding='utf-8').read()
        self.assertIn("shYouth(i)?'youth':shDay(i)?'sun'", js)


if __name__ == '__main__':
    unittest.main()
