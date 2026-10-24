import subprocess, os, json, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
def js(expr):
    return json.loads(subprocess.check_output(["node", "-e", f"const N=require('./newlook.js');console.log(JSON.stringify({expr}))"], cwd=ROOT))

class NewLookButtons(unittest.TestCase):
    def test_phone_wins_over_facebook(self):  # Dean 24 Oct: phone button wherever there's a venue number
        self.assertEqual(js("N.contact('07803259452','https://facebook.com/x')"), "call")
    def test_facebook_only_without_phone(self):
        self.assertEqual(js("N.contact('','https://facebook.com/x')"), "fb")
    def test_no_contact_button(self):
        self.assertIsNone(js("N.contact('','')"))
    def test_phone_format(self):
        self.assertEqual(js("['07803259452','02392825673','01132522927','01353860850','03001231966'].map(N.fmt)"),
                         ["07803 259452", "023 9282 5673", "0113 252 2927", "01353 860850", "0300 123 1966"])
    def test_domain(self):
        self.assertEqual(js("N.domain('https://www.cambsacre.org.uk/projects/x')"), "cambsacre.org.uk")
    def test_loaded_after_v3(self):
        s = open(os.path.join(ROOT, "index.html")).read()
        self.assertLess(s.index('src="v3.js'), s.index('src="newlook.js'))
