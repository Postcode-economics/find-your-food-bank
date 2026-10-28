# Phones for Dean: branch fix/phone-qa-28oct

No phone change on this branch goes live without Dean's yes. Each number was checked digit for digit on the helpline's **own** website, read twice more than 60 seconds apart (28 Oct 2026, 07:00–07:10 UTC).

Scope: this branch is the 28 Oct phone (mobile) QA fixes. Its only phone-related change is B7, which adds a spoken name (`aria-label`) to the four helpline links in "More free helplines". **No number and no `tel:` link changed.** The links below have been live on main since before this branch.

| Helpline | Link (unchanged) | Shown (unchanged) | Own site, read 1 | Own site, read 2 | Branch change | Dean |
|---|---|---|---|---|---|---|
| Shelter housing advice | `tel:08088004444` | 0808 800 4444 | 0808 800 4444 (england.shelter.org.uk/get_help/helpline) | 0808 800 4444 | label "Call 0808 800 4444" / "Ffoniwch 0808 800 4444" | awaiting yes |
| National Domestic Abuse Helpline | `tel:08082000247` | 0808 2000 247 | 0808 2000 247 (nationaldahelpline.org.uk) | 0808 2000 247 | label "Call 0808 2000 247" / "Ffoniwch 0808 2000 247" | awaiting yes |
| Samaritans | `tel:116123` | 116 123 | 116 123 (samaritans.org) | 116 123 | label "Call 116 123" / "Ffoniwch 116 123" | awaiting yes |
| Live Fear Free (Wales) | `tel:08088010100` | 0808 80 10 100 | **0808 80 10 800** (gov.wales/live-fear-free/contact-live-fear-free) | **0808 80 10 800** | **NOT CONFIRMED. The digit label was reverted.** The label is now the name only: "Call Live Fear Free" / "Ffoniwch Byw Heb Ofn" | awaiting decision |
| 999 | `tel:999` | Call 999 | n/a | n/a | none | n/a |

B6 also adds invisible 44px tap padding to `tel:` links in the footer and legal text. This is CSS only, so no number or link changes.

## Needs Dean: Live Fear Free number

The Welsh Government's own Live Fear Free contact page says "Call: 0808 80 10 800" on both reads. The site shows and dials **0808 80 10 100**, and that is already live on main. This branch does not change it. If Dean says yes, the change is `tel:08088010100` → `tel:08088010800` and "0808 80 10 100" → "0808 80 10 800" in the English and Welsh strip in `v3.js`. It needs a fresh pair of reads on the day it is made.

## Undo

- Live Fear Free label: in `v3.js`, set `aria-label="Call Live Fear Free"` back to `aria-label="Call 0808 80 10 100"` and `aria-label="Ffoniwch Byw Heb Ofn"` back to `aria-label="Ffoniwch 0808 80 10 100"`. Then put `index.html`'s `v3.js?v=` back to `h0096a29daeab` and run `python scripts/sw_version.py`, or revert the commit that added this file.
- All B7 labels: revert the B7 hunk of commit d86b6666a in `v3.js`.
