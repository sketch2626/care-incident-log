# Mary round 10: a secure address book (M19)

Mary needs to know who a resident means when they say "email my daughter", without anyone reading out an address. These boards show a plain address book: find someone, see their card, add someone by voice, use it, change it, take someone out for good, and let a helper type in several people.

Static boards at 1280x800 with no app code. Open them with `canvas.json`.
Every board comes from `round10-src/build.py`. `r6.css` and `r9.css` are unchanged copies of round 9's; `r10.css` holds the new `.m10-` classes.
No real names or data are used. All of it is made up: resident Ruth Hollis, nine people, 555-01xx numbers, example.com emails, and Anytown addresses.

## Boards

| Board | What it shows | Her full line, aloud | Caption on screen |
|---|---|---|---|
| `A1-List-Mary` | The list: Find box, My doctors, 9 people, the first five rows, Up, Down, the lock line, Add someone | Who are you after? | Who are you after? |
| `A2-Find-Mary` | They said "Show me Sarah." The list narrows to two Sarahs, both rows lit, with Show everyone in the bottom row | Two Sarahs. Your daughter, or Sarah Beck from church? | Your daughter, or / Sarah Beck from church? |
| `B1-Card-Mary` | Sarah Whitfield's card, all seven fields, no scrolling: All people, Change, Email Sarah, Make a card | Here's Sarah. | Here's Sarah. |
| `H1-Doctor-Mary` | A doctor's card: Dr. Helen Lee, Heart doctor, with Practice, Office phone, Fax, Patient portal, Office address, Specialty and Notes; All doctors, Change | Here's Dr. Lee. | Here's Dr. Lee. |
| `C1-AddFill-Mary` | The form. Name and Relationship filled; Email lit and filling in: sarah, sarah.whitfeld, sarah.whitfeld@example.com, moving | Sarah Whitfield, your daughter. | Sarah Whitfield, / your daughter. |
| `C2-AddSpell-Mary` | The same form, email lit, still. The spelling is wrong on purpose: she heard it wrong | S, A, R, A, H, dot, W, H, I, T, F, E, L, D, at example dot com. Is that right? | sarah.whitfeld@example.com / Is that right? |
| `C3-AddFix-Mary` | They catch the mistake, and the email is corrected, still lit | W, H, I, T, F, I, E, L, D. At example dot com. Is that right? | sarah.whitfield@example.com / Is that right? |
| `C4-AddSaved-Mary` | Name, Relationship, Email and Birthday filled, nothing lit, a plain check and Saved beside Save | Saved. I'll mention her birthday when it's close. | Saved. I'll mention her / birthday when it's close. |
| `S1-AddSpell-Sam` | C3 in Sam's look, his face, Back to Sam | W, H, I, T, F, I, E, L, D. At example dot com. Is that right? | sarah.whitfield@example.com / Is that right? |
| `D1-Email-Mary` | Full page. They said "Email my daughter." Nobody said the address | To Sarah. What do you want to say? | What do you / want to say? |
| `D2-Look-Mary` | The look before it goes: To, the address, the message signed Mom, Send, Not yet | When you say send, it goes to Sarah's email. You'll have five seconds to stop it. | When you say send, it goes / to Sarah's email. |
| `D3-Card-Mary` | Full page. They said "Make Sarah a birthday card." She knew who and when | March 14 is Sarah's birthday. Pick a front you like. | Pick a front / you like. |
| `G1-KeepAsk-Mary` | Full page, option A, the pick: she asks once per person | Sent to Tom. Keep Tom's address for next time? | Keep Tom's / address? |
| `G2-KeptSay-Mary` | Full page, option B: no question, but she keeps it without being told to | Sent to Tom. His address is in your book now. Say so if you'd rather I didn't keep it. | It's in your / book now. |
| `E1-Change-Mary` | Sarah's form, Cell phone lit with the new number and the old one beside it: Save, Put it back, Forget Sarah | Her cell, 919-555-0188. Is that right? | Her cell, 919-555-0188. / Is that right? |
| `E2-ForgetAsk-Mary` | Sarah Beck's card, with empty boxes for what isn't filled in: Yes, forget her; No, keep her | Forget Sarah Beck? Her address, her birthday reminders and what I remember about her all go for good. | Forget Sarah Beck? / All of it goes for good. |
| `E3-Forgotten-Mary` | The list scrolled to the end without Sarah Beck, 8 people | Done. Sarah Beck is out of your address book. | Done. Sarah Beck is out / of your address book. |
| `F1-Helper-Mary` | A helper types Mark Hollis's details: 3 added today, Save and add another, Done | That's three in. Ask if you need me. | That's three in. / Ask if you need me. |
| `F2-HelperVoice-Mary` | The same form, Birthday lit: the helper types, and Mary filled the one thing Ruth said | June 3. Is that right? | June 3. / Is that right? |
| `N-Notes` | Plain notes: where it's kept, what Mary sees, what forget does | | |

The resident's own words never appear as a caption. What they said sits in a dashed board note.

## The rules these boards show

- She never saves by herself. A tap on Save, or their plain "save it", does that.
- One match opens the card straight away. Two matches, and she asks which.
- She reads an email back letter by letter before it counts, and they can catch a mistake.
- Nobody has to say an address. The address shows on the look step for their eyes, and she doesn't say it.
- Sending is the same send step as today: their say-so, then five seconds to stop it.
- A patient portal's web address is kept on the doctor's card. Its password never is, and she won't read or fill one.
- Forget asks once, by full name, and then takes the person out for real: address, birthday reminders and what she remembers.
- E3 never says "gone", because a resident could hear that as a death.
- Typed words stay on the laptop. Mary sees them only if someone asks her about them.
- The address book is kept only on this laptop, locked, apart from the care log, and never goes in a report.

Two ways to treat a new address on a first send are shown for Andy to choose: G1, the pick, and G2.

## Buttons kept, and why

| Button | Board | Reason |
|---|---|---|
| Menu | D1, D3, G1, G2 | Her one button on the full page |
| Back to Mary, Back to Sam | Every deeper board | A big sure way home, in view always |
| The list rows | A1, A2, E3 | Each whole row is a button, about 84 tall, so a shaky hand can't miss |
| Up, Down | A1, E3 | Shaky hands can't fine-scroll |
| Add someone | A1, A2, E3 | The way in for a helper who types |
| My doctors | A1, A2, E3 | Doctors have their own part of the book |
| All doctors | H1 | Back to the doctors from one card |
| Show everyone | A2 | The way back from a narrowed list |
| All people | B1, C1 to C4, S1 | Back to the list without going back to her |
| Change | B1, H1 | Opens the form on this card |
| Email Sarah, Make a card | B1 | The two things a card is for, by tap as well as by voice |
| Save | C1 to C4, S1, E1 | The resident's own say-so, by tap |
| Send, Not yet | D2 | The real send step |
| Put it back | E1 | Undoes the change she filled in before anything is saved |
| Forget Sarah | E1 | The tap way to E2, which still asks |
| Yes, forget her; No, keep her | E2 | The one question. No, keep her is the Save-style button, so the safe answer stands out |
| Save and add another, Done | F1, F2 | A helper adding several people in one sitting |
| Tapping small Mary | Every deeper board | Not a `<button>`: a 132px tap target that does what Back to Mary does |

`check.py` fails a board with any other button.

## Sizes

| Part | Where | Size |
|---|---|---|
| Top band | y 0 to 156, as round 9 | 1280 by 156 |
| Small Mary | x 16, y 12 | 132 by 132, viewBox `180 50 280 280` |
| Her words | x 164 to 864 | Fredoka 600, 32px, 2 lines, 32 characters a line at most |
| Back to Mary | x 884 to 1252, y 28 to 124 | 368 by 96, 34px bold |
| Page | y 156 to 712, nothing scrolls on the card or the form | Segoe UI, cream #fbf7ef |
| Bottom row | y 712 to 800, always in view | 88 tall; buttons 72 tall, 32px bold; Add someone 340 wide; Up and Down 180 wide |
| Lock line | Bottom row of A1, A2, E3 | 22px semi-bold, lock icon 30px |
| Heading and count | A1, A2, E3 | Heading 36px bold, count 26px semi-bold |
| Find box | x 640 to 948, y 164 to 232 | 68 tall, 28px |
| My doctors | x 964 to 1224, y 160 to 232 | 260 by 72, 32px bold |
| List rows | x 56 to 1224 | 84 tall, name 32px bold, relationship 28px from x 704 |
| Card | Name 40px bold, relationship 28px beside it; left x 56 w 566, right x 658 w 566 | Labels 24px semi-bold, values 28px; boxes 68 tall, two-line boxes 104; ends y 680 |
| Form | Same columns, nine fields, y 164 to 702 | Labels 24px semi-bold, values 28px; boxes 64 tall, two-line boxes 98 |
| Lit | Field or row | 5px #f2b632 ring, 3px #2b1f17 outer edge, #fff1c7 fill |
| Full-page caption | Style A | 44px, 2 lines, 13 characters a line at most |
| Board notes | Dashed `.m9-note`; on full-page boards at x 36 to 376, y 300 to 422, left of her face | 20px semi-bold. H1, E1, F1 and F2 use a tighter three-line note, `.m10-tight`, to fit the bottom row |
| N-Notes | | Headings 40px, words 30px |

Motion: C1 loops 4.8 seconds on round 9's stacked opacity, nothing moves, and reduced motion shows the whole address. `r10.css` adds no motion of its own.

Fonts: Fredoka for her caption, from the round 6 shell, on Google Fonts for now and to bundle later. Segoe UI comes with Windows.

## Colors and contrast

| Use | Colors | Ratio |
|---|---|---|
| Value on a lit field | #1f1b16 on #fff1c7 | 15.2:1 |
| Value on a plain field, white buttons, lock line | #1f1b16 on #ffffff | 17.1:1 |
| Labels on the page | #1f1b16 on #fbf7ef | 16.0:1 |
| Find someone | #544739 on #ffffff | 9.0:1 |
| Was line on a lit field | #544739 on #fff1c7 | 8.0:1 |
| Save-style buttons | #ffffff on #0f5560 | 8.4:1 |
| Her words, Mary | #9b2c58 on the white edge | 7.3:1 |
| Her words, Sam | #1b5a8c on the white edge | 7.3:1 |
| Back to Mary | #2b1f17 on #fffdf8 | 15.8:1 |
| Notes board on her glow, darkest spot | #1f1b16 on #f6af74 | 9.2:1 |

## How to rebuild

From `round10-src`: run `build.py`, then `check.py`. `build.py` writes every board and `canvas.json`, and `check.py` exits 1 on any failure. The rectangles live in `build.py` as data and `check.py` imports them.
`check.py` covers tags, ids, references, captions, text sizes, banned words, the buttons on each board, list rows as measured buttons, targets, animated properties, the band and page rectangles, every box's position, full-page notes clear of her face and caption, text fit, contrast, the face crop, C1's stacked email, `canvas.json`, and this README's lines. It also holds the data to the made-up list: emails end @example.com, phones are 555-01xx, only the listed names appear, no board says "gone", and Saved as a status shows only on C4.

## What can't be confirmed without a browser

These boards have never been opened; everything above is by calculation.

- The fonts: widths are estimated.
- The motion on `C1-AddFill-Mary`.
- Whether the three-line notes on `H1-Doctor-Mary`, `E1-Change-Mary`, `F1-Helper-Mary` and `F2-HelperVoice-Mary` read comfortably in the bottom row. They are board notes, not part of the app.
- Sam's face and glow on `S1-AddSpell-Sam` are as round 9, unseen at this size.
- How the empty boxes on `E2-ForgetAsk-Mary` read: as room for more, or as something missing.
