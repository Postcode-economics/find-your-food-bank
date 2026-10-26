"""Rules 21 and 5. Labels come from the page, then phone_labels.json. A council switchboard is not the venue phone."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import phone_rules
from hours_fix import apply_phone

NUM = '01234 567890'
TEL = '01234567890'
PAGE = 'Pastor\nPlease ring %s for a parcel.\n' % NUM


class Label(unittest.TestCase):
    def test_role_next_to_the_number_comes_from_the_page(self):
        item = {'phone': NUM, 'tel': TEL}
        self.assertEqual(phone_rules.apply_contact_label(item, 'Manager', PAGE), 'page')
        self.assertEqual(item['phone_label'], 'Pastor')

    def test_override_is_only_the_fallback(self):
        item = {'phone': NUM, 'tel': TEL}
        self.assertEqual(phone_rules.apply_contact_label(item, 'Church office', 'Monday 10:00 to 12:00'), 'override')
        self.assertEqual(item['phone_label'], 'Church office')

    def test_a_role_on_another_line_is_not_used(self):
        text = 'Pastor\nno number here\n' + NUM
        self.assertIsNone(phone_rules.label_from_page(text, NUM))

    def test_page_that_says_no_phone_calls_holds_the_number(self):
        item = {'phone': NUM, 'tel': TEL, 'phone_label': 'Pastor'}
        self.assertEqual(phone_rules.apply_contact_label(item, 'Pastor', 'Please do not call. ' + PAGE), 'held')
        self.assertEqual(item['phone'], '')
        self.assertEqual(item['tel'], '')
        self.assertNotIn('phone_label', item)
        self.assertEqual(item['phone_held_reason'], 'page says no phone calls')


class Switchboard(unittest.TestCase):
    def test_switchboard_wording_blocks_unless_the_page_names_the_ooh_line(self):
        self.assertTrue(phone_rules.switchboard_blocked(TEL, 'Council switchboard ' + NUM, {}))
        self.assertFalse(phone_rules.labelled_council_ooh({'council_phone': NUM}))
        self.assertFalse(phone_rules.labelled_council_ooh({
            'council_phone': NUM, 'council_label': 'Council switchboard',
            'council_url': 'https://www.example.gov.uk/contact'}))
        named = {
            'council_ooh': TEL, 'council_phone': TEL,
            'council_label': 'Council out-of-hours homeless line',
            'council_url': 'https://www.example.gov.uk/homelessness',
        }
        text = 'The main switchboard is also the out-of-hours homeless line ' + NUM
        self.assertTrue(phone_rules.labelled_council_ooh(named))
        self.assertFalse(phone_rules.switchboard_blocked(TEL, text, named))
        bare = dict(named, council_label='Council switchboard')
        self.assertTrue(phone_rules.switchboard_blocked(TEL, text, bare))

    def test_apply_phone_clears_a_switchboard_and_keeps_a_labelled_ooh_line(self):
        blocked = apply_phone({'phone': 'switchboard ' + NUM})
        self.assertEqual(blocked['tel'], '')
        self.assertEqual(blocked['phone'], '')
        self.assertEqual(blocked['phone_held_reason'], 'council switchboard')
        kept = apply_phone({
            'phone': NUM,
            'council_ooh': TEL,
            'council_label': 'Council out-of-hours homeless line',
            'council_url': 'https://www.example.gov.uk/homelessness',
        }, page_text='Council switchboard, the out-of-hours homeless line: ' + NUM)
        self.assertEqual(kept['tel'], TEL)
        plain = apply_phone({'phone': NUM})
        self.assertEqual(plain['tel'], TEL)
        self.assertNotIn('phone_held_reason', plain)


if __name__ == '__main__':
    unittest.main()
