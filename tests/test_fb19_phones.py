import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
O = lambda f: json.load(open(os.path.join(ROOT, 'overrides', f)))
NEW = {'gcg': '07517 747501', 'amble': '01670 620015', 'ifan-53c68645aa831ab649ac43-0': '020 8788 2024',
       'ifan-5b3e01fe979d373d9ba679-0': '0161 817 2250', 'ifan-5b9fd1318a04132921a389-0': '0131 442 3304',
       'ifan-762040c38571b1178c1e2d-0': '020 8374 7708', 'ifan-9cf9dd4ce1df051c2c0a59-0': '07701 365551',
       'ifan-ca574aed6b4ff8c310060c-0': '0113 262 3233'}

def test_fb_numbers_in_overrides_so_refresh_keeps_them():
    ph, src = O('phones.json'), O('phone_sources.json')
    for k, v in NEW.items():
        assert ph[k] == v and src[k]['source'].startswith('https://www.facebook.com/')

def test_labels():
    pl = O('phone_labels.json')
    assert pl['amble'] == 'Referral line'
    assert pl['ifan-5b3e01fe979d373d9ba679-0'].startswith('Caritas Diocese of Salford')

def test_label_reaches_browser_data():
    assert "'phone_label'" in open(os.path.join(ROOT, 'scripts', 'compact.py')).read()
