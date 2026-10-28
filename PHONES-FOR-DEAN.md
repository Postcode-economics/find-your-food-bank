# Phones for Dean: branch fix/phone-qa-28oct

Rule (Dean, 28 Oct 07:02): a phone correction is applied without waiting when the service's **own** website confirms it. That means identical on 2 reads, with no conflicting own-site page. Trussell, directories and the Charity Commission are never sources. Ambiguous cases are listed under HELD.

This branch is the 28 Oct phone (mobile) QA fixes. B7 adds spoken names to the four helpline links in "More free helplines" (`v3.js`, English and Welsh strip). B6 adds invisible tap padding to footer/legal `tel:` links, which is CSS only with no number change.

## Applied (4)

| # | Helpline | Change | Own-site source | Read 1 (UTC) | Read 2 (UTC) | Undo |
|---|---|---|---|---|---|---|
| 1 | Shelter housing advice | label "Call 0808 800 4444" / "Ffoniwch 0808 800 4444". Number unchanged: `tel:08088004444` | https://england.shelter.org.uk/get_help/helpline | 07:04:57 0808 800 4444 | 07:06:04 0808 800 4444 | remove the `aria-label` on `tel:08088004444` in `v3.js` (both languages) |
| 2 | National Domestic Abuse Helpline | label "Call 0808 2000 247" / "Ffoniwch 0808 2000 247". Number unchanged: `tel:08082000247` | https://www.nationaldahelpline.org.uk/ | 07:04:58 0808 2000 247 | 07:06:04 0808 2000 247 | remove the `aria-label` on `tel:08082000247` in `v3.js` (both languages) |
| 3 | Samaritans | label "Call 116 123" / "Ffoniwch 116 123". Number unchanged: `tel:116123` | https://www.samaritans.org/ | 07:04:58 116 123 | 07:06:05 116 123 | remove the `aria-label` on `tel:116123` in `v3.js` (both languages) |
| 4 | Live Fear Free (Wales) | **number corrected:** `tel:08088010100` "0808 80 10 100" → `tel:08088010800` "0808 80 10 800", label "Call 0808 80 10 800" / "Ffoniwch 0808 80 10 800" | https://www.gov.wales/live-fear-free/contact-live-fear-free ("Call: 0808 80 10 800") | 07:02:58 0808 80 10 800 | 07:04:06 0808 80 10 800 | in `v3.js` set both `tel:08088010800` back to `tel:08088010100` and "0808 80 10 800" back to "0808 80 10 100" (link text and label, English and Welsh). Then set `index.html`'s `v3.js?v=` to the file's new sha256 (first 12 hex, prefixed `h`) and run `python scripts/sw_version.py`. Or revert the commit that made the change. |

Conflict check for #4: every Live Fear Free page linked from https://www.gov.wales/live-fear-free and https://www.llyw.cymru/byw-heb-ofn was read (13 pages). The 8 pages that give a number all give 0808 80 10 800, and none give 0808 80 10 100. Examples are contact, domestic-abuse-wales, sexual-violence, honour-based-violence-and-forced-marriage, and the Welsh cysylltwch-byw-heb-ofn and cam-drin-domestig-yng-nghymru. The gov.wales site search has no result for 0808 80 10 100.

999 is unchanged.

## HELD (0)

None.
