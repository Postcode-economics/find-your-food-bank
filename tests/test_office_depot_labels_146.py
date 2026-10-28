"""Lock (fix/office-depot-labels, 27 Oct 2026): 146 food bank listings whose shown times were office, phone-line,
helpline, referral, donation, depot or church-activity hours, or another place's times. Every fix quotes the organisation's
own page (overrides/opening_times.json raw). Exact food times only where the page gives them; otherwise the times are
labelled (text) or removed with a 'call ahead' notice. Nothing is ever switched to Closed. Protected from the refresh by
reader 'hand-reviewed' (discover.py never overwrites those)."""
import json, os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from times import normalise
def J(p): return json.load(open(os.path.join(ROOT, "overrides", p), encoding="utf-8"))
def items():
    t = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
    return {i["id"]: i for i in json.loads(t[t.index("=") + 1:].strip().rstrip(";"))["items"]}
FOOD = {
 "billingham-stockton-borough/stockton": {
  "mon": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "tue": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "wed": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "thu": [
   [
    "10:00",
    "12:00"
   ]
  ]
 },
 "chat": {
  "mon": [
   [
    "09:30",
    "12:00"
   ]
  ],
  "tue": [
   [
    "09:30",
    "12:00"
   ]
  ],
  "wed": [
   [
    "09:30",
    "12:00"
   ]
  ],
  "thu": [
   [
    "09:30",
    "12:00"
   ]
  ],
  "fri": [
   [
    "09:30",
    "12:00"
   ]
  ],
  "sat": [
   [
    "09:30",
    "12:00"
   ]
  ]
 },
 "chiltern/prestwood": {
  "tue": [
   [
    "09:00",
    "12:00"
   ]
  ],
  "wed": [
   [
    "09:00",
    "12:00"
   ]
  ],
  "thu": [
   [
    "09:00",
    "12:00"
   ]
  ],
  "fri": [
   [
    "09:00",
    "12:00"
   ]
  ]
 },
 "crossroads-community-hub": {
  "mon": [
   [
    "13:00",
    "15:00"
   ]
  ],
  "thu": [
   [
    "13:00",
    "15:00"
   ]
  ]
 },
 "dens": {
  "mon": [
   [
    "10:00",
    "13:00"
   ]
  ],
  "tue": [
   [
    "10:00",
    "13:00"
   ]
  ],
  "wed": [
   [
    "10:00",
    "13:00"
   ],
   [
    "15:00",
    "18:00"
   ]
  ],
  "thu": [
   [
    "10:00",
    "13:00"
   ]
  ],
  "fri": [
   [
    "10:00",
    "13:00"
   ]
  ]
 },
 "derby-city-mission": {
  "tue": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "wed": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "thu": [
   [
    "10:00",
    "12:00"
   ]
  ]
 },
 "edinburgh-food-project/clermiston": {
  "mon": [
   [
    "17:00",
    "18:45"
   ]
  ]
 },
 "hayle": {
  "sat": [
   [
    "10:30",
    "12:00"
   ]
  ]
 },
 "hereford": {
  "mon": [
   [
    "10:00",
    "12:00"
   ],
   [
    "13:00",
    "15:00"
   ]
  ],
  "tue": [
   [
    "10:00",
    "12:00"
   ],
   [
    "13:00",
    "15:00"
   ]
  ],
  "wed": [
   [
    "10:00",
    "12:00"
   ],
   [
    "13:00",
    "15:00"
   ]
  ],
  "thu": [
   [
    "10:00",
    "12:00"
   ],
   [
    "13:00",
    "15:00"
   ]
  ],
  "fri": [
   [
    "10:00",
    "12:00"
   ],
   [
    "13:00",
    "15:00"
   ]
  ]
 },
 "highams-park-hub": {
  "tue": [
   [
    "11:00",
    "13:00"
   ]
  ],
  "thu": [
   [
    "11:00",
    "13:00"
   ]
  ]
 },
 "hope-for-belper": {
  "tue": [
   [
    "12:00",
    "14:00"
   ]
  ],
  "fri": [
   [
    "12:00",
    "14:00"
   ]
  ]
 },
 "hornsey": {
  "thu": [
   [
    "10:15",
    "13:00"
   ]
  ]
 },
 "ifan-25c84c4582b7e7c60aeeac-0": {
  "mon": [
   [
    "09:30",
    "14:00"
   ]
  ],
  "wed": [
   [
    "12:30",
    "16:30"
   ]
  ],
  "fri": [
   [
    "09:30",
    "16:30"
   ]
  ]
 },
 "ifan-3c7cb974c7ac6c1966b83c-0": {
  "mon": [
   [
    "12:00",
    "14:00"
   ]
  ],
  "tue": [
   [
    "12:00",
    "14:00"
   ]
  ],
  "wed": [
   [
    "12:00",
    "14:00"
   ]
  ],
  "fri": [
   [
    "12:00",
    "14:00"
   ]
  ],
  "sat": [
   [
    "11:00",
    "13:00"
   ]
  ]
 },
 "ifan-84cd0bf40986bfc9a427c6-0": {
  "wed": [
   [
    "10:00",
    "14:00"
   ]
  ]
 },
 "ifan-9fef48d4f0fd3a3f6896d2-0": {
  "fri": [
   [
    "17:00",
    "18:00"
   ]
  ]
 },
 "liphook": {
  "tue": [
   [
    "09:30",
    "11:30"
   ]
  ],
  "fri": [
   [
    "09:30",
    "11:30"
   ]
  ]
 },
 "living-hope": {
  "wed": [
   [
    "12:00",
    "13:30"
   ]
  ]
 },
 "long-eaton-sawley": {
  "tue": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "fri": [
   [
    "10:00",
    "12:00"
   ]
  ]
 },
 "lyme-regis": {
  "wed": [
   [
    "10:00",
    "12:00"
   ]
  ]
 },
 "machars-churches": {
  "tue": [
   [
    "09:00",
    "12:00"
   ]
  ],
  "wed": [
   [
    "09:00",
    "12:00"
   ]
  ],
  "thu": [
   [
    "09:00",
    "12:00"
   ]
  ]
 },
 "maidenhead": {
  "wed": [
   [
    "16:45",
    "17:45"
   ]
  ],
  "sat": [
   [
    "09:30",
    "10:45"
   ]
  ]
 },
 "muswell-hill": {
  "mon": [
   [
    "11:30",
    "13:30"
   ]
  ],
  "wed": [
   [
    "11:30",
    "13:30"
   ]
  ],
  "fri": [
   [
    "11:30",
    "13:30"
   ]
  ]
 },
 "newlands": {
  "thu": [
   [
    "09:00",
    "11:00"
   ]
  ]
 },
 "north-belfast": {
  "mon": [
   [
    "14:00",
    "15:30"
   ]
  ]
 },
 "nourish": {
  "tue": [
   [
    "10:00",
    "14:00"
   ]
  ],
  "thu": [
   [
    "10:00",
    "14:00"
   ]
  ]
 },
 "poole": {
  "tue": [
   [
    "09:30",
    "12:30"
   ]
  ],
  "wed": [
   [
    "09:30",
    "12:30"
   ]
  ],
  "thu": [
   [
    "09:30",
    "12:30"
   ]
  ],
  "fri": [
   [
    "09:30",
    "12:00"
   ]
  ]
 },
 "poole/st-clements-church-hall": {
  "mon": [
   [
    "11:00",
    "12:30"
   ]
  ],
  "tue": [
   [
    "11:00",
    "12:30"
   ]
  ],
  "wed": [
   [
    "11:00",
    "12:30"
   ]
  ],
  "thu": [
   [
    "11:00",
    "12:30"
   ]
  ],
  "fri": [
   [
    "11:00",
    "12:30"
   ]
  ]
 },
 "poole/st-gabriels-church-hall": {
  "tue": [
   [
    "13:30",
    "15:00"
   ]
  ]
 },
 "purley/old-lodge-lane-baptist-church": {
  "fri": [
   [
    "09:00",
    "12:00"
   ]
  ]
 },
 "riverside-vineyard-storehouse": {
  "thu": [
   [
    "13:00",
    "15:00"
   ]
  ],
  "sat": [
   [
    "10:00",
    "12:00"
   ]
  ]
 },
 "ross-community-larder": {
  "tue": [
   [
    "09:00",
    "11:00"
   ]
  ]
 },
 "sadaka": {
  "sat": [
   [
    "11:30",
    "13:00"
   ]
  ]
 },
 "salma": {
  "mon": [
   [
    "10:00",
    "13:00"
   ]
  ],
  "thu": [
   [
    "10:00",
    "13:00"
   ]
  ]
 },
 "salvation-army/inverness": {
  "wed": [
   [
    "09:00",
    "13:00"
   ]
  ]
 },
 "shepshed": {
  "tue": [
   [
    "11:00",
    "12:30"
   ]
  ]
 },
 "shrewsbury": {
  "tue": [
   [
    "09:30",
    "12:00"
   ]
  ],
  "wed": [
   [
    "17:00",
    "18:45"
   ]
  ],
  "fri": [
   [
    "09:30",
    "12:00"
   ]
  ]
 },
 "skegness": {
  "mon": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "tue": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "wed": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "thu": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "fri": [
   [
    "10:00",
    "12:00"
   ]
  ]
 },
 "sketty": {
  "wed": [
   [
    "11:00",
    "14:00"
   ]
  ]
 },
 "soar-valley-community-food-project": {
  "mon": [
   [
    "11:00",
    "13:00"
   ]
  ]
 },
 "south-tyneside": {
  "mon": [
   [
    "11:00",
    "13:00"
   ]
  ],
  "tue": [
   [
    "11:00",
    "13:00"
   ]
  ],
  "thu": [
   [
    "11:00",
    "13:00"
   ]
  ],
  "fri": [
   [
    "11:00",
    "13:00"
   ]
  ]
 },
 "southend/hawkwell-hockley": {
  "mon": [
   [
    "17:00",
    "18:30"
   ]
  ]
 },
 "southgate-mosque": {
  "mon": [
   [
    "10:30",
    "12:00"
   ]
  ]
 },
 "st-andrews": {
  "tue": [
   [
    "11:00",
    "13:00"
   ]
  ],
  "wed": [
   [
    "13:00",
    "14:30"
   ]
  ],
  "thu": [
   [
    "11:00",
    "13:00"
   ]
  ]
 },
 "st-monicas": {
  "mon": [
   [
    "12:00",
    "14:30"
   ]
  ]
 },
 "sunderland/downhill-centre-community-hub": {
  "thu": [
   [
    "11:00",
    "13:30"
   ]
  ]
 },
 "transformation/centenary-methodist-centre-camborne": {
  "tue": [
   [
    "13:30",
    "15:30"
   ]
  ],
  "wed": [
   [
    "17:30",
    "18:30"
   ]
  ],
  "thu": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "fri": [
   [
    "10:30",
    "12:00"
   ]
  ]
 },
 "wansbeck-valley/ymca": {
  "tue": [
   [
    "12:00",
    "13:00"
   ]
  ],
  "thu": [
   [
    "12:00",
    "13:00"
   ]
  ]
 },
 "wells": {
  "wed": [
   [
    "10:30",
    "12:30"
   ]
  ],
  "sat": [
   [
    "10:30",
    "12:30"
   ]
  ]
 },
 "welwyn-garden-city": {
  "wed": [
   [
    "09:00",
    "11:00"
   ]
  ]
 },
 "west-end-impact": {
  "tue": [
   [
    "10:00",
    "13:00"
   ]
  ]
 },
 "west-hallam-methodist": {
  "fri": [
   [
    "10:00",
    "11:00"
   ]
  ]
 },
 "westminster": {
  "mon": [
   [
    "13:00",
    "15:00"
   ]
  ],
  "thu": [
   [
    "11:00",
    "13:00"
   ]
  ]
 },
 "whitefoot-and-downham": {
  "thu": [
   [
    "19:00",
    "20:30"
   ]
  ]
 },
 "wimborne": {
  "wed": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "fri": [
   [
    "14:00",
    "16:00"
   ]
  ]
 },
 "windsor-food-share": {
  "wed": [
   [
    "09:00",
    "12:30"
   ]
  ],
  "thu": [
   [
    "09:00",
    "14:30"
   ]
  ]
 },
 "woodhouse-close-church": {
  "mon": [
   [
    "09:00",
    "16:30"
   ]
  ],
  "tue": [
   [
    "09:00",
    "16:30"
   ]
  ],
  "wed": [
   [
    "09:00",
    "16:30"
   ]
  ],
  "thu": [
   [
    "09:00",
    "16:30"
   ]
  ],
  "fri": [
   [
    "09:00",
    "12:30"
   ]
  ]
 },
 "woodley": {
  "mon": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "tue": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "wed": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "thu": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "fri": [
   [
    "10:00",
    "12:00"
   ]
  ]
 },
 "worth-valley": {
  "tue": [
   [
    "13:00",
    "14:45"
   ]
  ]
 },
 "worthing-food-foundation": {
  "wed": [
   [
    "10:00",
    "11:30"
   ]
  ],
  "fri": [
   [
    "10:00",
    "11:30"
   ]
  ]
 },
 "yeovil": {
  "mon": [
   [
    "10:00",
    "14:00"
   ]
  ],
  "tue": [
   [
    "10:00",
    "14:00"
   ]
  ],
  "wed": [
   [
    "10:00",
    "14:00"
   ]
  ],
  "thu": [
   [
    "10:00",
    "14:00"
   ]
  ],
  "fri": [
   [
    "10:00",
    "14:00"
   ]
  ]
 },
 "ystradgynlais": {
  "tue": [
   [
    "10:00",
    "12:00"
   ]
  ],
  "thu": [
   [
    "10:00",
    "12:00"
   ]
  ]
 }
}
TEXT = {
 "aylesbury": "Postal/warehouse address (deliveries and donations only). Office hours: Mon - Thurs 10.30am - 3:00pm",
 "bradford-north": "Phone line hours, not collection: Our phone line is open Monday, Tuesday, Thursday and Friday: 9:00am - 2:00pm",
 "broxbourne": "Warehouse: food donations Tuesday to Thursday 10am - 2pm, not a collection point. Collect parcels from the distribution centres",
 "chiltern/wendover": "Delivery only (no collection here). Phoneline open Tuesday to Friday, 10am to 12:30pm, not collection times",
 "ek-community": "Church office hours, not food bank times: Office Opening Hours: Monday-Friday: 9am-5pm",
 "fusion": "Office hours, not food collection: Pearl House office Mon-Fri 9am - 4pm (Wednesdays emergency appointments only)",
 "fusion/calderdale": "Office hours, not food collection: Halifax Mon-Fri: 10am - 3pm",
 "glasgow-sw": "Office and warehouse only, no food parcels collected here. Office hours: Monday to Friday 9am to 5pm",
 "glastonbury-street": "Citizens Advice Somerset hours, not food bank sessions: by phone Monday to Friday 10am to 4pm; in person Glastonbury Library Thursdays 10am to 1pm, Crispin Community Centre Wednesdays 10am to 1pm",
 "godmanchester-huntingdon": "Helpline hours, not food bank sessions: Rural Citizens Advice Huntingdonshire 0808 2787 807 (lines open Monday to Friday 9.30am to 3.30pm); Help through Hardship 0808 2082138 (open Monday to Friday, 9am-5pm)",
 "hangleton-west-blatchington": "The food bank is open every Wednesday from 12:00-14:00 for clients by appointment only",
 "haverhill": "Contact hours (phone and office), not food collection: Monday to Friday, 9am - 4.30pm",
 "hucknall": "Engage Food Bank, referral necessary: available on Mondays and Tuesdays between 9:30am and 1.30pm",
 "ifan-9cf9dd4ce1df051c2c0a59-0": "Pantries: Myatts Field Pantry Tuesdays 10am-1pm; the Village Pantry (Oasis at St Martins) Tuesdays 12-2pm; Moorlands Pantry Thursdays 11am-3pm",
 "ifan-d59b2e089746f7a97c1e15-0": "Community Pantry (members only): Monday, Wednesday and Friday, 9am to 2pm",
 "lalley-centre": "Lalley Centre: food pantry session from 10.30am to 12.30pm (last entry at 12.15pm) on Wednesdays and Fridays",
 "luton": "Phone line hours, not food collection: 01582 725838 Mon-Fri, 8.30am - 4pm",
 "newark/tuxford": "Delivery only: this centre is managed from Newark - obtain a voucher and we will deliver",
 "north-bristol-south-gloucestershire": "Phone line hours, not collection times: 0117 472 5172 Mon-Fri 9.30am-4.30pm. Emergency parcels can only be collected at specific times: see their website for centre times",
 "open-hands-reigate": "Phone line hours, not collection times: Tuesday & Thursday 9 am to 12 pm - 07849-634309; Tuesday & Thursday 1 pm to 4 pm - 07849-633736. Closed every Wednesday",
 "patch": "Milford Haven, Robert Street, SA73 2HA: Monday – Friday 10am-2pm",
 "pbp": "CETMA office opening hours, not food collection: Kidwelly Office Monday-Friday 10AM - 4PM",
 "redcar-area": "Please note this is not a foodbank. We can now accept donations at our office again Monday to Friday 9am to 12noon",
 "ringwood": "Warehouse (postal address), open Monday, Wednesday and Friday 9:30 to 12:30: we do not distribute food from here, please go to your nearest Distribution Centre",
 "ripon-community-house": "Referral hours, not collection times: Referrals are accepted Monday to Friday between 12.30 - 3.30pm. Parcels can be collected Monday to Friday",
 "salford": "THIS IS THE OFFICES AND WAREHOUSE OF SALFORD FOODBANK. NO FOOD PARCELS WILL BE AVAILABLE AT THIS SITE, ONLY AT OUR DISTRIBUTION CENTRES",
 "salvation-army/bradford-holmewood": "Requests for a crisis food parcel (Monday to Thursday 10am to 12noon), via their Facebook page: request hours, not a collection session",
 "salvation-army/hastings-temple": "Tuesday: Food Bank - appointment required 10:30am - 11:30am",
 "salvation-army/scunthorpe": "Food Bank 09.30-12.00 every other Wednesday",
 "salvation-army/sheringham": "Food Bank (by appointment 9am-4pm / Monday - Friday / 01263 826059)",
 "somebody-cares": "Foodbank order line (not a walk-in time): Monday - Friday 10:00am - 3:30pm, order by 11.30 am for same day collection",
 "southend": "Warehouse, DONATIONS ONLY, Monday, Tuesday and Thursday between 9am - 2pm. You are unable get a voucher or collect food from this location",
 "stowmarket-area": "The centre is open during the following hours: Mondays to Fridays: 9 am - 1 pm",
 "tameside-south-longdendale": "Hollingworth Hub (PERMANENTLY CLOSED AFTER MONDAY 29 JULY 2024): its times removed. See the centres for their own times",
 "thame": "Food bank phone line answered between 9.00am and 1.00pm each weekday (not collection times)",
 "the-community-cupboard": "West Kingsdown: Mon, Wed & Fri: 10am - 12 noon; Tues & Thur 12 - 2pm",
 "the-forest": "Warehouse, not a distribution centre. Distribution Centres: LYDNEY Tuesday 1 pm - 3 pm; COLEFORD Wednesday 10 am - 12 noon; CINDERFORD Thursday 1 pm - 3 pm",
 "the-storehouse-congleton": "Not food bank hours: EVERY TUESDAY (Term-time) 10am to 12.30 is the Jubilee Club (social group). See their website for Storehouse food bank times",
 "wokingham": "Warehouse donation hours, not a collection point: Monday 9:30-14:30, Wednesday 9:30-14:30 (Book a Food Donation Drop)",
 "york": "Donation drop-off depot only, not a food collection point: Tuesday/Thursday 9am-1pm or by arrangement"
}
CALL_AHEAD = [
 "aylesbury/tabitha-foodbank",
 "corfe-mullen",
 "green-lane-masjid-and-community-centre",
 "hays-community-pantry",
 "liberty-church-mid-ulster",
 "maidstone-homeless-care",
 "manna",
 "north-ayrshire/st-johns-church",
 "north-lakes",
 "queens-park-govanhill-parish-church",
 "rickmansworth/maple-cross",
 "salvation-army",
 "salvation-army/bourne",
 "salvation-army/bury",
 "salvation-army/chester",
 "salvation-army/dorchester",
 "salvation-army/guernsey",
 "salvation-army/hayle",
 "salvation-army/hedge-end",
 "salvation-army/ivybridge",
 "salvation-army/newton-abbot-church-community-centre",
 "salvation-army/paignton",
 "salvation-army/penzance",
 "salvation-army/pill",
 "salvation-army/poole",
 "salvation-army/sale",
 "salvation-army/salisbury",
 "salvation-army/southsea",
 "salvation-army/street",
 "salvation-army/sundays",
 "salvation-army/tiverton",
 "salvation-army/ware",
 "salvation-army/weymouth",
 "salvation-army/wimborne",
 "salvation-army/winton",
 "seaton",
 "st-annes-advice-nottingham",
 "st-augustines",
 "st-pauls-crewe",
 "stretton",
 "stroud-district",
 "the-bus-shelter-shop",
 "ty-hapus",
 "walk-inn"
]
WRONG_CORPS_PAGE = ["salvation-army", "salvation-army/bourne", "salvation-army/bury", "salvation-army/chester", "salvation-army/pill", "salvation-army/sale", "salvation-army/salisbury", "salvation-army/street", "salvation-army/sundays", "salvation-army/ware", "salvation-army/wimborne"]  # times came from another Salvation Army corps' page: link removed too
NOTICE = {
 "aylesbury": "Warehouse: deliveries and donations only. Times shown are office hours. See where to get food below.",
 "aylesbury/tabitha-foodbank": "Call ahead: no food bank session times are confirmed on their own page.",
 "bradford-north": "Times shown are phone line hours, not food collection. See where to get food below.",
 "broxbourne": "Warehouse for donations: not a place to collect food. See where to get food below.",
 "chiltern/prestwood": "Delivery only: food is delivered, not collected here. Times shown are delivery times.",
 "chiltern/wendover": "Delivery only: food is delivered, not collected here. Call ahead to arrange a delivery.",
 "corfe-mullen": "Call ahead: no food bank session times are confirmed on their own page.",
 "ek-community": "Times shown are church office hours, not food bank times. Call or see their website for food bank times.",
 "fusion": "Times shown are office hours, not food collection.",
 "fusion/calderdale": "Times shown are office hours, not food collection.",
 "glasgow-sw": "Office and warehouse only: no food parcels can be collected here. See where to get food below.",
 "glastonbury-street": "Times shown are Citizens Advice Somerset's hours, not food bank sessions. See their website for session times.",
 "godmanchester-huntingdon": "Times shown are helpline hours (Citizens Advice / Help through Hardship) for getting a voucher, not food bank sessions. See their website for session times.",
 "green-lane-masjid-and-community-centre": "Call ahead: no food bank session times are confirmed on their own page.",
 "hangleton-west-blatchington": "Food bank by appointment only. Call ahead to book.",
 "haverhill": "Times shown are contact hours, not food collection. See where to get food below.",
 "hays-community-pantry": "Call ahead: no food bank session times are confirmed on their own page.",
 "hucknall": "Referral needed. Call ahead.",
 "ifan-25c84c4582b7e7c60aeeac-0": "Low-cost community shop (you pay). Free food bank is delivery-only, Wed–Fri, by professional referral.",
 "ifan-9cf9dd4ce1df051c2c0a59-0": "Three pantries at different addresses. See their website for each one.",
 "ifan-d59b2e089746f7a97c1e15-0": "Community pantry for members only. Call ahead to join.",
 "lalley-centre": "Pantry sessions are at the Lalley Centre. Call ahead.",
 "liberty-church-mid-ulster": "Call ahead: no food bank session times are confirmed on their own page.",
 "luton": "Times shown are phone line hours, not food collection. See where to get food below.",
 "maidstone-homeless-care": "Call ahead: no food bank session times are confirmed on their own page.",
 "manna": "Call ahead: no food bank session times are confirmed on their own page.",
 "newark/tuxford": "Delivery only: food is delivered, not collected here.",
 "north-ayrshire/st-johns-church": "Opens on phone request: \"This centre is only open upon a telephone request.\" Call ahead on 07437 521930 to arrange a collection.",
 "north-bristol-south-gloucestershire": "Times shown are phone line hours, not collection times. Parcels are collected at set times at each centre: see their website for centre times.",
 "north-lakes": "Call ahead: no food bank session times are confirmed on their own page.",
 "open-hands-reigate": "Times on their page are phone line hours, not collection times. Closed every Wednesday.",
 "pbp": "Times shown are CETMA office hours, not food collection. See where to get food below.",
 "purley/old-lodge-lane-baptist-church": "Food stop: £3.50 payment, no referral needed.",
 "queens-park-govanhill-parish-church": "Call ahead: no food bank session times are confirmed on their own page.",
 "redcar-area": "Not a food bank, donations only.",
 "rickmansworth/maple-cross": "Call ahead, no current sessions listed.",
 "ringwood": "Does not hand out food here. See where to get food below.",
 "ripon-community-house": "Times on their page are referral hours (Mon to Fri 12.30 to 3.30pm), not collection times. Parcels can be collected Monday to Friday.",
 "salford": "No parcels at this site. See where to get food below.",
 "salvation-army": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/bourne": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/bradford-holmewood": "Times shown are when to request a crisis food parcel, not a collection session. Call ahead.",
 "salvation-army/bury": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/chester": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/dorchester": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/guernsey": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/hastings-temple": "Food bank by appointment only. Call ahead to book.",
 "salvation-army/hayle": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/hedge-end": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/ivybridge": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/newton-abbot-church-community-centre": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/paignton": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/penzance": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/pill": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/poole": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/sale": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/salisbury": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/scunthorpe": "Food bank every other Wednesday, 9.30am to 12 noon. Call ahead to check which weeks.",
 "salvation-army/sheringham": "Food bank by appointment only. Call ahead to book.",
 "salvation-army/southsea": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/street": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/sundays": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/tiverton": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/ware": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/weymouth": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/wimborne": "Call ahead: no food bank session times are confirmed on their own page.",
 "salvation-army/winton": "Call ahead: no food bank session times are confirmed on their own page.",
 "seaton": "Call ahead: no food bank session times are confirmed on their own page.",
 "somebody-cares": "Times shown are the foodbank order line. Order by 11.30am for same-day collection.",
 "southend": "Warehouse for donations only: you cannot collect food here. See where to get food below.",
 "st-annes-advice-nottingham": "Call ahead: no food bank session times are confirmed on their own page.",
 "st-augustines": "Call ahead: no food bank session times are confirmed on their own page.",
 "st-pauls-crewe": "Call ahead: no food bank session times are confirmed on their own page.",
 "stowmarket-area": "Times shown are the food bank centre's hours (the Tue/Wed pop-up shop at the Catholic Centre is separate).",
 "stretton": "Call ahead: no food bank session times are confirmed on their own page.",
 "stroud-district": "Office and warehouse: not a place to collect food. Call ahead or see where to get food below.",
 "tameside-south-longdendale": "The Hollingworth Hub has been permanently closed since July 2024. See where to get food below.",
 "thame": "Their phone line is answered 9am to 1pm on weekdays. These are not collection times.",
 "the-bus-shelter-shop": "Call ahead: no food bank session times are confirmed on their own page.",
 "the-community-cupboard": "Times shown are West Kingsdown's.",
 "the-forest": "Warehouse: not a place to collect food. See where to get food below.",
 "the-storehouse-congleton": "Tuesday 10am to 12.30 is a social club, not the food bank. See their website for food bank times.",
 "ty-hapus": "Call ahead: no food bank session times are confirmed on their own page.",
 "walk-inn": "Call ahead: no food bank session times are confirmed on their own page.",
 "welwyn-garden-city": "Food bank open Wednesday mornings 9am to 11am only. Other hours on their page are helpline hours.",
 "wokingham": "Warehouse for donations: not a place to collect food. See where to get food below.",
 "york": "Donation drop-off depot only: not a place to collect food. See where to get food below."
}
WAREHOUSE = [  # never Closed; point to centres
"york", "glasgow-sw", "haverhill", "luton", "fusion", "aylesbury", "stroud-district", "wokingham", "the-forest", "pbp", "southend", "bradford-north", "manna", "ringwood", "salford", "redcar-area", "broxbourne"]
# Merge with main (28 Oct): these 3 ids are locked by main's Dean-approved tests to main's state
# (test_listing_fixes Southend, test_rule27_second_pass ty-hapus / soar-valley), so this branch's expectations for them are dropped here.
for _k in ("southend", "ty-hapus", "soar-valley-community-food-project"):
    FOOD.pop(_k, None); TEXT.pop(_k, None); NOTICE.pop(_k, None)
    if _k in CALL_AHEAD: CALL_AHEAD.remove(_k)
class T(unittest.TestCase):
    @classmethod
    def setUpClass(c): c.t, c.n, c.d = J("opening_times.json"), J("foodbank_notices.json"), items()
    def ot(self, k):
        o = self.t[k]; self.assertTrue(o["reader"].startswith("hand-reviewed"), k); return o
    def test_exact_food_times(self):
        for k, s in FOOD.items():
            o = self.ot(k); self.assertEqual((o["status"], o["structured"]), ("TIMES_FOUND", s), k)
            self.assertEqual(self.d[k]["opening_times"]["structured"], normalise(o)["structured"], k)
            self.assertNotIn(self.d[k].get("kind"), ("warehouse", "dropoff"), k)
    def test_labelled_text_never_closed(self):
        for k, raw in TEXT.items():
            o = self.ot(k); self.assertEqual((o["status"], o["structured"], o["raw"]), ("TIMES_TEXT_ONLY", None, raw), k)
            if k == "tameside-south-longdendale": self.assertIn("hollingworth hub (permanently closed", o["raw"].lower()); continue  # names the closed hub only; the food bank is not closed
            self.assertNotRegex(o["raw"].lower().replace("closed every", ""), r"\bclosed\b", k)
            self.assertEqual(self.d[k]["opening_times"]["raw"], raw, k)
    def test_call_ahead_not_closed(self):
        for k in CALL_AHEAD:
            o = self.ot(k); self.assertEqual((o["status"], o["structured"], o["raw"]), ("NO_TIMES", None, ""), k)
            self.assertIn("call ahead", self.n[k]["notice"].lower(), k)
            d = self.d[k]["opening_times"]; self.assertNotEqual(d.get("status"), "TIMES_FOUND", k); self.assertFalse(d.get("all_closed"), k)
        for k in WRONG_CORPS_PAGE: self.assertIsNone(self.t[k]["source_url"], k)
    def test_notices_on_cards(self):
        for k, v in NOTICE.items(): self.assertEqual(self.n[k]["notice"], v, k); self.assertEqual(self.d[k].get("notice"), v, k)
    def test_warehouse_pins_point_to_centres(self):
        m = J("foodbank_manual.json")
        self.assertEqual(m["york"]["kind"], "dropoff"); self.assertEqual(m["glasgow-sw"]["kind"], "warehouse"); self.assertEqual(m["stroud-district"]["kind"], "warehouse")
        self.assertEqual(m["poole"]["kind"], "client")  # the Poole Lifecentre food bank is at this pin
        for k in WAREHOUSE: self.assertIn(self.d[k].get("kind"), ("warehouse", "dropoff"), k)
    def test_specific_cases(self):
        self.assertEqual(FOOD["salvation-army/inverness"], {"wed": [["09:00", "13:00"]]})  # day from the same line, not the next one
        self.assertEqual(FOOD["whitefoot-and-downham"], {"thu": [["19:00", "20:30"]]})
        self.assertEqual(FOOD["wansbeck-valley/ymca"], {"tue": [["12:00", "13:00"]], "thu": [["12:00", "13:00"]]})
        self.assertNotIn("website for delivery", self.n["chiltern/wendover"]["notice"].lower())  # their site lists no delivery times
        self.assertEqual(FOOD["poole/st-gabriels-church-hall"], {"tue": [["13:30", "15:00"]]})  # swapped with St Clement's
        self.assertEqual(FOOD["poole/st-clements-church-hall"], {d: [["11:00", "12:30"]] for d in ("mon", "tue", "wed", "thu", "fri")})
        self.assertEqual(FOOD["woodhouse-close-church"]["fri"], [["09:00", "12:30"]])
        self.assertEqual(FOOD["muswell-hill"], {d: [["11:30", "13:30"]] for d in ("mon", "wed", "fri")})
        self.assertFalse(str((self.t.get("cardiff") or {}).get("reader", "")).startswith("hand-reviewed 2026-10-27 (own page re-fetched live"))
if __name__ == "__main__": unittest.main()
class Round16(unittest.TestCase):
    """27 Oct 23:31 review: Cornerstone reverted to main; nbil labelled low-cost shop; Bot 4 browser findings (each quoted on 2 fetches)."""
    def test_round16(self):
        t, n = J("opening_times.json"), J("foodbank_notices.json")
        self.assertNotIn("ifan-5b3e01fe979d373d9ba679-0", t)
        self.assertEqual(n["ifan-25c84c4582b7e7c60aeeac-0"]["notice"], "Low-cost community shop (you pay). Free food bank is delivery-only, Wed–Fri, by professional referral.")  # 28 Oct: Bot 3 FAIL fixed, quoted on 2 fetches
        self.assertEqual(t["hereford"]["structured"]["wed"], [["10:00", "12:00"], ["13:00", "15:00"]])
        self.assertEqual(t["purley/old-lodge-lane-baptist-church"]["structured"], {"fri": [["09:00", "12:00"]]})
        self.assertNotIn("Parish Office", t["corfe-mullen"]["raw"])
        self.assertIn("telephone request", n["north-ayrshire/st-johns-church"]["notice"])
        self.assertEqual(t["aylesbury/tabitha-foodbank"]["status"], "NO_TIMES")
        self.assertNotIn(" | ", t["patch"]["raw"])
        self.assertIn("pantry session from 10.30am to 12.30pm", t["lalley-centre"]["raw"])
