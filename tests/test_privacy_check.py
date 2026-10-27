import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import privacy_check as pc

FAKE = '1 Example Close, Exampletown EX1 1EX|01000 000123'


def _site(tmp_path, listing_extra='', page_extra=''):
    (tmp_path / 'export').mkdir()
    items = [{'id': 'a', 'name': 'Food bank', 'address': 'High St ZZ9 9ZZ ' + listing_extra, 'phone': '01999 888777'}]
    (tmp_path / 'export' / 'foodbanks.json').write_text(json.dumps({'items': items}))
    (tmp_path / 'index.html').write_text('<p>Hello ' + page_extra + '</p>')
    (tmp_path / 'faq.html').write_text('<p>FAQ</p>')
    return str(tmp_path)


def run(tmp_path, monkeypatch, secret, **kw):
    monkeypatch.chdir(_site(tmp_path, **kw))
    monkeypatch.setenv('PRIVATE_BLOCKLIST', secret)
    return pc.main([])


def test_passes_when_clean(tmp_path, monkeypatch, capsys):
    assert run(tmp_path, monkeypatch, FAKE) == 0
    out = capsys.readouterr().out
    assert 'listings checked: 1' in out and 'pages checked: 2' in out and 'matches: 0' in out


def test_empty_secret_fails(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, '') == 2
    d = tmp_path / 'x'; d.mkdir()
    assert run(d, monkeypatch, '  \n | ') == 2


def test_address_in_listing_fails(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, FAKE, listing_extra='1  EXAMPLE close,\nexampletown ex1 1ex') == 1


def test_postcode_squashed_address_fails(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, FAKE, page_extra='1 Example Close Exampletown EX11EX') == 1


def test_phone_variants_fail(tmp_path, monkeypatch):
    for i, v in enumerate(['01000000123', '+44 1000 000 123', '0044 (0)1000-000123'.replace('(0)', ''), '+44 (1000) 000.123']):
        d = tmp_path / str(i); d.mkdir()
        assert run(d, monkeypatch, FAKE, page_extra='call ' + v) == 1, v


def test_output_never_contains_values(tmp_path, monkeypatch, capsys):
    run(tmp_path, monkeypatch, FAKE, listing_extra='1 Example Close, Exampletown EX1 1EX 01000 000123')
    out = capsys.readouterr().out.casefold()
    for bit in ['example', 'ex1', '000123', '01000']:
        assert bit not in out
