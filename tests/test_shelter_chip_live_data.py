"""Shelter type chips must match published shelters.js (Dean hotfix).

Each filter chip alone must leave at least one mappable place when none of the
chips are pressed, every pin shows; union when several are on.
"""
import json, os, re, sys, unittest

ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))


def _items():
    text = open(os.path.join(ROOT, 'shelters.js'), encoding='utf-8').read()
    return json.loads(text[text.index('=') + 1:].rstrip().rstrip(';'))['items']


def is_day_centre(i):
    kind = str(i.get('kind') or i.get('service') or '').lower().replace('-', ' ').replace('_', ' ')
    return i.get('label') == 'Day centre' or kind == 'day centre'


def is_youth(i):
    if i.get('kind') == 'young_people':
        return True
    name = str(i.get('name') or '')
    groups = ' '.join(i.get('groups') or [])
    blob = name + ' ' + groups
    if re.search(r'\bfoyers?\b', name, re.I):
        return True
    if re.search(r'\bhousing\b', name, re.I) and re.search(r'16\s*[-–to]{1,3}\s*25', blob, re.I):
        return True
    if re.search(r'\byoung people\b', name, re.I):
        return True
    if re.search(r'16\s*[-–to]{1,3}\s*2[0-9]', name, re.I):
        return True
    if re.search(r'16\s*[-–to]{1,3}\s*2[0-9]', groups, re.I):
        return True
    return False


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


def pin_items(items):
    return [
        i for i in items
        if i.get('card_type') != 'referral_hostel'
        and isinstance(i.get('lat'), (int, float))
        and isinstance(i.get('lng'), (int, float))
        and not i.get('no_pin')
    ]


class LiveShelterChips(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = pin_items(_items())

    def test_each_chip_keeps_pins(self):
        cases = (
            ('hostel', False, False, True),
            ('youth', False, True, False),
            ('day', True, False, False),
        )
        for name, day, youth, hostel in cases:
            n = sum(1 for i in self.pins if shelter_type_ok(i, day, youth, hostel))
            self.assertGreater(n, 0, '%s chip would hide every pin (%d mappable)' % (name, len(self.pins)))

    def test_union_when_two_chips(self):
        day_n = sum(1 for i in self.pins if is_day_centre(i))
        youth_n = sum(1 for i in self.pins if is_youth(i) and not is_day_centre(i))
        n = sum(1 for i in self.pins if shelter_type_ok(i, True, True, False))
        self.assertEqual(n, day_n + youth_n)

    def test_none_pressed_shows_all_pins(self):
        n = sum(1 for i in self.pins if shelter_type_ok(i, False, False, False))
        self.assertEqual(n, len(self.pins))

    def test_footer_key_row_order_in_layers_js(self):
        js = open(os.path.join(ROOT, 'layers.js'), encoding='utf-8').read()
        fb = js.index("keyRow(`<i class=\"sw tear\"")
        ws = js.index("keyRow(`<i class=\"sw dia\"")
        sh = js.index("keyRow(symSvg('house',20),'sh'")
        day = js.index("keyRow(symSvg('sun',20),'dayCentre'")
        youth = js.index("keyRow(symSvg('youth',20),'youth'")
        self.assertLess(fb, ws, 'food banks before warm spaces')
        self.assertLess(ws, sh, 'warm spaces before shelters')
        self.assertLess(sh, day, 'shelters before day centre')
        self.assertLess(day, youth, 'day centre before youth')


if __name__ == '__main__':
    unittest.main()
