"""Dean-approved phones from the 26 Oct 2026 missing-number list.

Clean numbers, shared venue lines and library service lines are in the override
files, so a refresh keeps them. A named or personal number that the venue's own
page gives as its contact is shown with that role (Team Rector, Pastor).
Numbers the own page does not confirm stay out. The 40 places with no number
stay on their website or email.
"""
import json, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load(name):
    return json.load(open(os.path.join(ROOT, "overrides", name), encoding="utf-8"))
def digits(s):
    return re.sub(r"\D", "", s or "")

# id -> (display, source url). Display is UK spacing; digits are the source digits.
CLEAN = {
    'windsor-food-share': ('07972 646613', 'https://www.givefood.org.uk/needs/at/windsor-food-share/'),
    'brigg': ('07946 109069', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5130830/contact-information'),
    'leyland': ('07435 330900', 'https://servicefinder.lancashire.gov.uk/lancashire-service-finder-directory/directory-details-page/?id=f012af0f-fa60-43e2-8304-b4670116e647'),
    'eastwood': ('01773 535255', 'https://www.eastwoodvb.org.uk/contact/'),
    'hornsey': ('07833 930183', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5221780/contact-information'),
    'bounds-green': ('07933 680869', 'https://www.boundsgreenfoodbank.org/copy-of-contact-us'),
    'still-good': ('07859 110205', 'https://register-of-charities.charitycommission.gov.uk/en/about-the-register-of-charities/-/charity-details/5164660/contact-information'),
    'petersfield': ('07878 693142', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5169643/contact-information'),
    'southend': ('07926 530327', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5065040/contact-information'),
    'islay': ('07563 968518', 'https://www.islayfoodbank.com/contact-us'),
    'banbury': ('01865 670569', 'https://banbury.foodbank.org.uk/contact-us/'),
    'kirkcaldy': ('01592 655422', 'https://www.lintonlanecentre.com/blank-2'),
    'granville-community-kitchen': ('07543 824439', 'https://www.brent.gov.uk/neighbourhoods-and-communities/community-directory/granville-community-kitchen'),
    'ignite-life': ('0117 235 3192', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5119141/contact-information'),
    'melksham': ('07493 738894', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5235288/contact-information'),
    'windsor-food-share/alma-beacon': ('07972 646613', 'https://www.givefood.org.uk/needs/at/windsor-food-share/'),
    'thurrock/st-john-the-baptist-church-tilbury': ('01375 416200', 'https://thurrock.foodbank.org.uk/contact-us/'),
    'thurrock/st-marys-church-hall-little-thurrock': ('01375 416200', 'https://thurrock.foodbank.org.uk/contact-us/'),
    'thurrock/gates-of-praise-international-christian-centre': ('01375 416200', 'https://thurrock.foodbank.org.uk/contact-us/'),
    'thurrock/st-stephens-church-hall-purfleet': ('01375 416200', 'https://thurrock.foodbank.org.uk/contact-us/'),
    'thurrock/grays-methodist-church': ('01375 416200', 'https://thurrock.foodbank.org.uk/contact-us/'),
    'thurrock/st-francis-centre-linford': ('01375 416200', 'https://thurrock.foodbank.org.uk/contact-us/'),
    'thurrock/emmanuel-church-chadwell-st-mary': ('01375 416200', 'https://thurrock.foodbank.org.uk/contact-us/'),
    'thurrock/all-saints-church-south-ockendon': ('01375 416200', 'https://thurrock.foodbank.org.uk/contact-us/'),
    'thurrock/gateway-peoples-centre': ('01375 416200', 'https://thurrock.foodbank.org.uk/contact-us/'),
    'southend/shoeburyness': ('07926 530327', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5065040/contact-information'),
    'southend/westcliff': ('07926 530327', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5065040/contact-information'),
    'southend/leigh': ('07926 530327', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5065040/contact-information'),
    'southend/earls-hall': ('07926 530327', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5065040/contact-information'),
    'southend/eastwood': ('07926 530327', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5065040/contact-information'),
    'southend/hawkwell-hockley': ('07926 530327', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5065040/contact-information'),
    'banbury/st-josephs-church': ('01865 670569', 'https://banbury.foodbank.org.uk/contact-us/'),
    'banbury/hardwick-centre': ('01865 670569', 'https://banbury.foodbank.org.uk/contact-us/'),
    'still-good/freedom-church': ('07859 110205', 'https://register-of-charities.charitycommission.gov.uk/en/about-the-register-of-charities/-/charity-details/5164660/contact-information'),
    'kirkcaldy/link-living': ('01592 655422', 'https://www.lintonlanecentre.com/blank-2'),
    'kirkcaldy/new-volunteer-house': ('01592 655422', 'https://www.lintonlanecentre.com/blank-2'),
    'kirkcaldy/linton-lane-centre': ('01592 655422', 'https://www.lintonlanecentre.com/blank-2'),
    'ifan-01c4e7b3eb5fb6efb0189d-1': ('07946 288144', 'https://www.thebrightmorningministries.com'),
    'ifan-0ea12dd414fcb6a358d3f0-0': ('01983 248170', 'https://pantogether.org.uk/about-us/contact-us/'),
    'ifan-3287e57944ff0bdd42b2a6-0': ('01992 538801', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5161532/contact-information'),
    'ifan-3287e57944ff0bdd42b2a6-1': ('01992 538801', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5161532/contact-information'),
    'ifan-34121866eb63e9e50d317f-0': ('07852 945928', 'https://shopanddonate.org/contact/'),
    'ifan-3598d68070dfe141274bc6-0': ('07736 308883', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/4021121/contact-information'),
    'ifan-3de702dac280937b2490eb-0': ('01924 211130', 'https://www.stcatherines-wakefield.org.uk'),
    'ifan-3e1f90aa3ff4d2ebf4b6d0-0': ('0161 222 3633', 'https://www.hmhc.co.uk'),
    'ifan-4794bf126a61365207fff5-0': ('020 7625 6260', 'https://www.westhampsteadcommunityfoodhub.org'),
    'ifan-4a6217d6ae69c4977d7d70-0': ('01268 743232', 'https://hopeworx.org.uk/Contact'),
    'ifan-bcc7d26b922ed1d9edf4f5-0': ('01704 601090', 'https://www.shorelinechurch.org.uk'),
    'ifan-eddf2af4d3d092a3382b3c-0': ('01902 601600', 'https://cacmor.org.uk/contact/'),
    # Rechecked 26 Oct 08:29: the venue's own page publishes this number as its contact.
    'nomad': ('01491 635737', 'https://www.nomadhenley.co.uk'),
    'ifan-79789d4df6b2024369673c-0': ('07723 447200', 'https://www.Highwayhope.co.uk'),
    'ifan-84cd0bf40986bfc9a427c6-0': ('07498 775019', 'https://www.laurenceslarder.org.uk/contact'),
    'ifan-9fef48d4f0fd3a3f6896d2-0': ('07828 138118', 'https://www.gcjc.co.uk'),
}
# Named or personal contact the venue's own page gives. Label is the role on that page.
NAMED = {
    'kings-langley': ('01923 903531', 'https://beneficeoflangelei.org.uk/allsaints/contact/', 'Team Rector'),
    'kings-langley/bennetts-end': ('01923 903531', 'https://beneficeoflangelei.org.uk/allsaints/contact/', 'Team Rector'),
    'leytonstone-seventh-day-adventist-church': ('07985 566592', 'https://leytonstone.adventistchurch.org.uk/contact-us', 'Pastor'),
}
SHARED = {
    'whitland-town-hall-community': ('01994 241231', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/504650/contact-information'),
    'storehouse-melton': ('07438 458514', 'https://meltonteamparish.org.uk/storehouse/'),
    'life-line': ('07305 869103', 'https://birmingham.connecttosupport.org/search/directory-search/?id=09469875-25f9-46de-a339-abe301381ff5'),
    'sacred-heart': ('020 7607 3594', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5241909/contact-information'),
    'allenby-primary-school': ('020 8578 6636', 'https://www.allenbyprimaryschool.com/ealing/primary/allenby/site/pages/contactus'),
}
LIBRARY = {
    'ww-68618605': ('0300 123 2224', 'https://www.librarieswest.org.uk/-/bruton-community-library'),
    'ww-69062943': ('0300 041 3131', 'https://local.kent.gov.uk/kb5/kent/directory/service.page?id=YRWoQMs70mE'),
    'ww-69100298': ('01484 414868', 'https://www.kirklees.gov.uk/beta/libraries/contact-us.aspx'),
    'ww-69100241': ('01484 414868', 'https://www.kirklees.gov.uk/beta/libraries/contact-us.aspx'),
    'ww-55475504': ('01484 414868', 'https://www.kirklees.gov.uk/beta/libraries/contact-us.aspx'),
    'ww-65438881': ('01623 677200', 'https://www.nottshelpyourself.org.uk/kb5/nottinghamshire/directory/service.page?id=c9-ql22cYZM'),
}
WARM_CLEAN = {
    'ww-65070433': ('07523 424686', 'https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/5197459/contact-information'),
}
# Still held. The venue's own page does not confirm a current contact number.
HELD = {
    'beechdale-community-centre': 'charity register phone, reporting overdue by 1640 days',
    'ifan-4843e1fec06a8fc46989df-0': 'own site says the phone is temporarily inactive',
    'ifan-4843e1fec06a8fc46989df-1': 'own site says the phone is temporarily inactive',
    'ifan-9d9a5ae13b3923c3fd7d0b-0': 'displayed number conflicts with the tel link',
}
NOT_FOUND = [
    'the-food-pantry-feltwell',
    'silverton-community-larder',
    'heston-farm',
    'thorne-and-moorends-community',
    'sandbach',
    'north-lochs',
    'noor',
    'henley-bridge-free-pantry',
    'dunbar-foodshare',
    'helensburgh-lomond',
    'galashiels-and-area',
    'bjo-amara-association',
    'bettws',
    'caithness',
    'llandysul',
    'drighlington',
    'newlands',
    'cgcc',
    'codsall-bilbrook-community',
    'dn7',
    'larkfield-community-church',
    'clifton-road',
    'burntisland-kinghorn',
    'galashiels-and-area/langlee-primary-school-car-park',
    'galashiels-and-area/focus-centre',
    'salvation-army/saltcoats',
    'helensburgh-lomond/st-modans-church-community-centre',
    'ifan-0696416ec3aadb29cb398b-0',
    'ifan-47a9d1714fe97a62d62178-0',
    'ifan-a2fb0701e0208ee9e642a3-0',
    'ifan-e0054aa041ea174c4f6921-0',
    'ww-68911571',
    'ww-63057583',
    'cmn-llanelli-queer-collective',
    'ww-63058939',
    'ww-63065216',
    'ww-69253373',
    'ww-68923940',
    'cmn-trallwm-hall',
    'cambs-whittlesey-community-hub',
]

def test_exactly_the_approved_rows_and_no_held_rows():
    phones, sources, labels = load("phones.json"), load("phone_sources.json"), load("phone_labels.json")
    ws = load("warmspaces_contacts.json")
    for i, (num, url) in CLEAN.items():
        assert phones[i] == num, i
        assert sources[i]["phone"] == num and sources[i]["source"] == url, i
        assert url.startswith("https://"), i
        assert digits(num) == digits(sources[i]["phone"])
        assert i not in labels, i
    for i, (num, url, lab) in NAMED.items():
        assert phones[i] == num and sources[i]["phone"] == num and sources[i]["source"] == url, i
        assert labels[i] == lab, i
        assert url.startswith("https://"), i
    for i, (num, url) in SHARED.items():
        assert phones[i] == num and sources[i]["phone"] == num and sources[i]["source"] == url, i
        assert labels[i] == "Shared venue line", i
    for i, (num, url) in LIBRARY.items():
        e = ws[i]
        assert e["phone"] == num and e["phone_source"] == url, i
        assert e["phone_label"] == "Library service line", i
        assert url.startswith("https://"), i
    for i, (num, url) in WARM_CLEAN.items():
        e = ws[i]
        assert e["phone"] == num and e["phone_source"] == url, i
        assert "phone_label" not in e, i
    blocked = list(HELD) + NOT_FOUND
    assert len(NOT_FOUND) == 40
    assert len(HELD) == 4
    assert len(CLEAN) == 53 and len(NAMED) == 3 and len(SHARED) == 5 and len(LIBRARY) == 6 and len(WARM_CLEAN) == 1
    for i in blocked:
        assert i not in phones and i not in sources and i not in labels, i
        if i in ws:
            assert not ws[i].get("phone") and not ws[i].get("phone_label"), i
    # Kent libraries publishes 03000 41 31 31; stored with UK spacing, same digits.
    assert digits(LIBRARY["ww-69062943"][0]) == "03000413131"
