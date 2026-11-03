"""New places on the map email one summary to help@helpmap.uk. Dry run only: no network."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from urllib.error import HTTPError

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import new_live_email as mail

HELP = "help@helpmap.uk"


def _js(items):
    return "window.FB_DATA=" + json.dumps({"items": items}) + ";"


def _live(cards, public=True):
    return json.dumps({"public": public, "cards": cards})


class Places(unittest.TestCase):
    def test_new_food_bank_lists_name_type_town_and_map_link(self):
        districts = {"NR1 1AA": "Norwich"}
        prev = [{"id": "old", "name": "Old Bank", "postcode": "NR1 1AA"}]
        cur = prev + [{"id": "new", "name": "Riverside Food Bank", "postcode": "NR1 1AA", "address": "1 High Street, Norwich"}]
        got = mail.newly_live(cur, prev, "foodbanks", districts)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["name"], "Riverside Food Bank")
        self.assertEqual(got[0]["type"], "Food bank")
        self.assertEqual(got[0]["town"], "Norwich")
        self.assertEqual(got[0]["link"], "https://helpmap.uk/?q=NR1%201AA")

    def test_already_live_place_is_not_listed(self):
        item = {"id": "same", "name": "Same", "postcode": "AB1 2CD"}
        self.assertEqual(mail.newly_live([item], [item], "warmspaces", {}), [])

    def test_warm_space_and_shelter_links_open_that_layer(self):
        ws = mail.newly_live([{"id": "w", "name": "Hub", "postcode": "PE15 8SQ"}], [], "warmspaces", {"PE15 8SQ": "Fenland"})
        sh = mail.newly_live([{"id": "s", "name": "Hostel", "town": "Southampton", "postcode": "SO15 2ED"}], [], "shelters", {})
        self.assertEqual(ws[0]["type"], "Warm space")
        self.assertEqual(ws[0]["town"], "Fenland")
        self.assertIn("ws=1", ws[0]["link"])
        self.assertEqual(sh[0]["type"], "Shelter")
        self.assertEqual(sh[0]["town"], "Southampton")
        self.assertIn("sh=1", sh[0]["link"])
        self.assertIn("q=SO15%202ED", sh[0]["link"])

    def test_town_falls_back_to_the_address_when_the_cache_has_no_postcode(self):
        got = mail.newly_live(
            [{"id": "a", "name": "Hall", "address": "Church Lane, March, PE15 8SQ"}],
            [], "warmspaces", {},
        )
        self.assertEqual(got[0]["town"], "March")
        self.assertIn("q=PE15%208SQ", got[0]["link"])

    def test_closed_and_example_rows_are_not_new_places(self):
        rows = [
            {"id": "c", "name": "Closed", "flag_closed": True, "postcode": "NR1 1AA"},
            {"id": "e", "name": "Example", "example": True, "postcode": "NR1 1AA"},
        ]
        self.assertEqual(mail.newly_live(rows, [], "shelters", {}), [])

    def test_emergency_card_goes_live_only_when_the_file_is_public(self):
        card = {"id": "rc1", "name": "Riverside Hall", "address": "BN17 5AA", "opened_by": "Arun District Council", "category": "incident_rest_centre"}
        hidden = mail.parse_layer(_live([card], public=False), "emergency")
        shown = mail.parse_layer(_live([card], public=True), "emergency")
        self.assertEqual(mail.newly_live(hidden, [], "emergency", {}), [])
        got = mail.newly_live(shown, [], "emergency", {})
        self.assertEqual(got[0]["type"], "Emergency provision")
        self.assertEqual(got[0]["town"], "Arun District Council")
        self.assertIn("q=BN17%205AA", got[0]["link"])
        self.assertNotIn("ws=1", got[0]["link"])
        again = mail.newly_live(shown, shown, "emergency", {})
        self.assertEqual(again, [])

    def test_swep_badge_is_its_own_type(self):
        card = {"name": "Night shelter", "swep_badge": "Severe weather shelter", "postcode": "LS1 1AA", "council": "Leeds"}
        got = mail.newly_live([card], [], "emergency", {})
        self.assertEqual(got[0]["type"], "SWEP")
        self.assertEqual(got[0]["town"], "Leeds")

    def test_an_address_inside_a_name_is_removed(self):
        got = mail.newly_live([{"id": "x", "name": "Hub other@example.com", "postcode": "NR1 1AA"}], [], "foodbanks", {})
        self.assertNotIn("@", got[0]["name"])
        self.assertNotIn("example.com", json.dumps(got))


class DryRun(unittest.TestCase):
    def setUp(self):
        self.env = {k: os.environ.get(k) for k in ("GITHUB_WORKFLOW", "BREVO_API_KEY", "HELPMAP_EMAIL_TO")}
        os.environ.pop("GITHUB_WORKFLOW", None)
        os.environ.pop("BREVO_API_KEY", None)
        os.environ["HELPMAP_EMAIL_TO"] = "other@example.com"

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _places(self):
        return mail.newly_live(
            [{"id": "n", "name": "Riverside Food Bank", "postcode": "NR1 1AA"}],
            [], "foodbanks", {"NR1 1AA": "Norwich"},
        )

    def test_nothing_new_does_not_send(self):
        def boom(*a, **k):
            raise AssertionError("opener called")
        out = mail.deliver([], send=True, api_key="secret-key", opener=boom)
        self.assertEqual(out["reason"], "nothing-new")
        self.assertFalse(out["sent"])

    def test_dry_run_prints_the_summary_and_does_not_call_brevo(self):
        def boom(*a, **k):
            raise AssertionError("opener called")
        out = mail.deliver(self._places(), send=False, api_key="secret-key", opener=boom)
        self.assertEqual(out["reason"], "dry-run")
        self.assertFalse(out["sent"])
        text = out["message"]["text"]
        self.assertIn("Riverside Food Bank", text)
        self.assertIn("Food bank", text)
        self.assertIn("Norwich", text)
        self.assertIn("https://helpmap.uk/?q=NR1%201AA", text)
        self.assertNotIn("@", text)
        self.assertEqual(mail.RECIPIENT, HELP)

    def test_send_posts_one_message_only_to_the_help_address(self):
        seen = []

        class Resp:
            status = 201
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def opener(req, timeout=None):
            seen.append(req)
            return Resp()

        out = mail.deliver(self._places(), send=True, api_key="secret-key", opener=opener)
        self.assertTrue(out["sent"])
        self.assertEqual(len(seen), 1)
        req = seen[0]
        self.assertEqual(req.full_url, mail.BREVO_URL)
        self.assertEqual(req.get_header("Api-key"), "secret-key")
        body = json.loads(req.data.decode())
        self.assertEqual(body["to"], [{"email": HELP, "name": "helpmap.uk"}])
        self.assertEqual(body["sender"]["email"], HELP)
        self.assertNotIn("bcc", body)
        self.assertNotIn("cc", body)
        self.assertNotIn("other@example.com", json.dumps(body))
        emails = set(mail._EMAIL.findall(json.dumps(body)))
        self.assertEqual(emails, {HELP})
        self.assertIn("Riverside Food Bank", body["textContent"])
        self.assertIn("Norwich", body["textContent"])

    def test_missing_key_does_not_call_brevo(self):
        def boom(*a, **k):
            raise AssertionError("opener called")
        out = mail.deliver(self._places(), send=True, api_key="", opener=boom)
        self.assertEqual(out["reason"], "no-key")
        self.assertFalse(out["sent"])

    def test_brevo_http_error_is_a_mail_error_and_names_no_body(self):
        def opener(req, timeout=None):
            raise HTTPError(req.full_url, 401, "no", hdrs=None, fp=None)
        with self.assertRaises(mail.MailError) as cm:
            mail.deliver(self._places(), send=True, api_key="secret-key", opener=opener)
        self.assertIn("401", str(cm.exception))
        self.assertNotIn("secret-key", str(cm.exception))

    def test_script_names_only_the_help_address(self):
        src = open(os.path.join(ROOT, "scripts", "new_live_email.py"), encoding="utf-8").read()
        emails = set(mail._EMAIL.findall(src))
        self.assertEqual(emails, {HELP})
        self.assertIn("BREVO_API_KEY", src)
        self.assertNotIn("def deliver(places, send=False, api_key=None, opener=None, to=", src)


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        self._git("init", "-q")
        self._git("config", "user.email", "dev@example.com")
        self._git("config", "user.name", "test")
        os.makedirs(os.path.join(self.d, "overrides"))
        json.dump({"NR1 1AA": "Norwich"}, open(os.path.join(self.d, "overrides", "district_cache.json"), "w"))
        open(os.path.join(self.d, "data.full.js"), "w").write(_js([
            {"id": "old", "name": "Old Bank", "postcode": "NR1 1AA"},
        ]))
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "base")
        self.base = subprocess.check_output(["git", "-C", self.d, "rev-parse", "HEAD"], text=True).strip()

    def _git(self, *args):
        subprocess.check_call(["git", "-C", self.d, *args], stdout=subprocess.DEVNULL)

    def _run(self, *extra):
        env = os.environ.copy()
        env.pop("BREVO_API_KEY", None)
        env.pop("GITHUB_WORKFLOW", None)
        env["HELPMAP_EMAIL_TO"] = "other@example.com"
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "new_live_email.py"), "--root", self.d, *extra],
            capture_output=True, text=True, env=env,
        )

    def test_dry_run_on_a_new_place(self):
        open(os.path.join(self.d, "data.full.js"), "w").write(_js([
            {"id": "old", "name": "Old Bank", "postcode": "NR1 1AA"},
            {"id": "new", "name": "Riverside Food Bank", "postcode": "NR1 1AA"},
        ]))
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "add")
        r = self._run("--layers", "foodbanks", "--baseline", self.base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("DRY RUN", r.stdout)
        self.assertIn("No email sent", r.stdout)
        self.assertIn("To: %s" % HELP, r.stdout)
        self.assertIn("Riverside Food Bank", r.stdout)
        self.assertIn("Type: Food bank", r.stdout)
        self.assertIn("Town: Norwich", r.stdout)
        self.assertIn("https://helpmap.uk/?q=NR1%201AA", r.stdout)
        self.assertNotIn("Old Bank", r.stdout)
        self.assertNotIn("other@example.com", r.stdout)

    def test_no_diff_sends_nothing(self):
        r = self._run("--layers", "foodbanks", "--baseline", self.base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("No new place went live. No email sent.", r.stdout)
        self.assertNotIn("DRY RUN", r.stdout)
        self.assertNotIn(HELP, r.stdout)

    def test_send_without_the_secret_does_not_claim_a_send(self):
        open(os.path.join(self.d, "data.full.js"), "w").write(_js([
            {"id": "new", "name": "Riverside Food Bank", "postcode": "NR1 1AA"},
        ]))
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "add")
        r = self._run("--layers", "foodbanks", "--baseline", self.base, "--send")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("BREVO_API_KEY", r.stdout + r.stderr)
        self.assertNotIn("Sent one summary", r.stdout)

    def test_a_missing_previous_file_does_not_mail_the_whole_map(self):
        with self.assertRaises(mail.MailError):
            mail.collect(self.d, self.base, ["emergency"])

    def test_missing_baseline_sends_nothing(self):
        r = self._run("--layers", "foodbanks", "--baseline", "")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("No baseline commit. No email sent.", r.stdout)


class Workflows(unittest.TestCase):
    def test_each_publisher_sends_after_a_successful_publish(self):
        cases = {
            "refresh.yml": "foodbanks",
            "refresh-warmspaces.yml": "warmspaces",
            "refresh-shelters.yml": "shelters,emergency",
            "swep-daily.yml": "emergency",
        }
        call = 'python scripts/new_live_email.py --layers %s --baseline "$LIVE_BASELINE" --send'
        for name, layers in cases.items():
            text = open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8").read()
            self.assertIn("LIVE_BASELINE=$(git rev-parse HEAD)", text, name)
            self.assertIn(call % layers, text, name)
            self.assertIn("BREVO_API_KEY: ${{ secrets.BREVO_API_KEY }}", text, name)
            self.assertIn("steps.commit.outcome == 'success'", text, name)
            self.assertNotIn("other@", text, name)

    def test_incident_loop_sends_after_each_publish(self):
        # The 10-minute loop publishes inside one long job, so it emails after each push.
        wf = open(os.path.join(ROOT, ".github", "workflows", "incident-rest-centre-watch.yml"), encoding="utf-8").read()
        loop = open(os.path.join(ROOT, "scripts", "incident_rest_centre_watch_loop.sh"), encoding="utf-8").read()
        self.assertIn("BREVO_API_KEY: ${{ secrets.BREVO_API_KEY }}", wf)
        self.assertIn('python scripts/new_live_email.py --layers emergency --baseline "$1" --send', loop)
        self.assertIn('push_with_retry || return 1\n  send_new_place_email "$baseline"', loop)
        self.assertNotIn("other@", wf + loop)


if __name__ == "__main__":
    unittest.main()
