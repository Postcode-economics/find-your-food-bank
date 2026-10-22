import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from own_locations import all_closed
class T(unittest.TestCase):
    def test_all_closed(self):
        self.assertTrue(all_closed("Opening times Mon Closed Tue Closed Wed Closed Thu Closed Fri Closed Sat Closed Sun Closed "))
    def test_some_open(self):
        self.assertFalse(all_closed("Opening times Mon Closed Tue Closed Wed Closed Thu Closed Fri Closed Sat 11:00 - 13:00 Sun Closed "))
        self.assertFalse(all_closed(""))
if __name__ == '__main__': unittest.main()
