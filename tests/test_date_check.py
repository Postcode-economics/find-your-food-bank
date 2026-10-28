"""Date check is alert-only for one week: it must report mismatches but exit 0."""
import importlib.util, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("date_check", ROOT / "scripts" / "date_check.py")
dc = importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)

STAMP = {"run": "2026-10-27T05:53:01+00:00", "label": "27 Oct 2026, 05:53",
         "layers": {"fb": {"label": "27 Oct 2026, 05:53"}, "sh": {"label": "27 Oct 2026, 05:39"},
                    "ws": {"label": "27 Oct 2026, 05:38"}}}


def site(tmp, fb="27 Oct 2026, 05:53", mapchk="27 Oct 2026, 05:53", phones=("26 Oct 2026", "26 Oct 2026")):
    (tmp / "stamp.js").write_text("window.FB_STAMP=" + json.dumps(STAMP) + ";")
    (tmp / "food-banks" / "a").mkdir(parents=True)
    (tmp / "food-banks" / "a" / "index.html").write_text(
        f'<p>Information last updated {fb}.</p><p class="mapchk" data-run="{STAMP["run"]}">Map data last checked {mapchk}</p>'
        f"<p>Phone numbers and opening times checked {phones[0]}</p>")
    (tmp / "faq.html").write_text(f"<p>Phone numbers and opening times checked {phones[1]}</p><p>x</p>")
    return tmp


def test_live_repo_runs():
    assert isinstance(dc.check(ROOT), list)


def test_clean_site_has_no_problems(tmp_path):
    assert dc.check(site(tmp_path)) == []


def test_reports_layer_mismatch(tmp_path):
    p = dc.check(site(tmp_path, fb="26 Oct 2026, 21:29"))
    assert len(p) == 1 and "Information last updated" in p[0]


def test_reports_map_and_phone_mismatch(tmp_path):
    p = dc.check(site(tmp_path, mapchk="26 Oct 2026, 00:13", phones=("26 Oct 2026", "25 Oct 2026")))
    assert any("Map data last checked" in x for x in p)
    assert any("Phone numbers and opening times checked" in x for x in p)


def test_alert_only_exit_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dc, "ROOT", site(tmp_path, fb="1 Jan 2020"))
    assert dc.main([]) == 0
    assert "::warning" in capsys.readouterr().out
    assert dc.main(["--strict"]) == 1
