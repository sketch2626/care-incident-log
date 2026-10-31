# Mary round 8, redrawn: this is M15b's redraw of the M15 boards

Cards and messages to family, by voice. Static boards at 1280x800 with no app code. Open them with `canvas.json`.
Every board comes from `round8-src/build.py`. `r6.css` is an unchanged copy of round 6; `r8.css` holds the `.m8-` classes still in use and the new `.c8-` ones.
All names and addresses are made up: Mom, her son Mark Hollis (mark.hollis@example.com), her grandson Tyler Hollis.

The rule, from Andy: "We're literally doing this by voice, so there's no need in any of that." No question-and-answer buttons, no who-gets-it list, no way back and no onward button. A button stays only for a real reason, listed below.

## Boards

| Board | What it shows | Her full line, aloud | Caption on screen |
|---|---|---|---|
| `A-Reminder-Mary` | The keepsake leaf: Saturday 7 November, a gilt frame waiting for his photo, Mark in foil | Mark's birthday is next Saturday. He'll be fifty-two. Want to make him a card? | Want to make / him a card? |
| `A-Reminder-Sam` | The same in Sam's look | Mark's birthday is next Saturday. He'll be fifty-two. Want to send him a card? | Want to send / him a card? |
| `B-Design-Mary` | Four painted fronts, numbered: Lake, Buck, Lighthouse, Magnolia | Four that suit him. Or I can make one to order. Tell me what you'd like on it. | Tell me what / you'd like. |
| `C-Card-Mary` | The Lake front, large, thick stock at the edge | What do you want to say? | What do you / want to say? |
| `C3-Opens-Mary` | The card opens by itself to show the inside, moving | Here's how it reads. (Then she reads it aloud.) | Here's how / it reads. |
| `C2-Inside-Mary` | Open flat: the verse, then their words in cursive | I can write it plainer if cursive's hard to read. Anything to change? | Anything to / change? |
| `C4-Plain-Mary` | The same in plain handwriting | Easier to read? | Easier to / read? |
| `D2-LastLook-Mary` | The Lake front over a cream envelope, addressed by hand. No buttons | When you say send, it goes to Mark's email. You'll have five seconds to stop it. | Five seconds / to stop it. |
| `D2b-Tap-Mary` | The same picture and one quiet outlined Send it. Shows only after she has failed twice to make them out | I didn't catch that. Say it again, or tap here. | Say it again, / or tap here. |
| `D3-Sending-Mary` | On "send it": the card and envelope smaller, the big Undo counting 5 4 3 2 1, then "Sent to Mark." for 3 seconds, looping | Going to Mark's email. (Before the count, then she stays quiet.) | Going to / Mark's email. |
| `F-Sent-Mary` | The card, a plain check, "Sent to Mark" and the time. No buttons | Sent to Mark. Would you like it to go through Messenger too, or printed so it can be mailed? | Messenger / or printed? |
| `E1-Open-Mary` | When they answer "Messenger": the card small and three plain steps. No buttons | Facebook keeps the Send button for you. I'll get it all ready. | Your hand on / this one. |
| `E2-Paste` | Facebook's chat in the panel beside her; Paste is in her own bar | Tap Paste to put the card in. | Tap Paste. |
| `E3-Send` | One picture in the message box, front beside inside; her bar asks if it went | Now tap Send in the chat. Then tell me if it went. | Now tap Send. |
| `G-Message-Mary` | A plain message to Tyler on cream paper, not a card. No buttons | Here's what I've got. When you say send, it goes to Tyler's email. You'll have five seconds to stop it. | Five seconds / to stop it. |
| `G2-Undo-Mary` | The same message with the same Undo count, ending "Sent to Tyler." | Going to Tyler's email. (Before the count, then she stays quiet.) | To Tyler's / email. |

The D3 and G2 lines are a proposal: the brief gave the caption and the rule that she's quiet during the count. "Tyler's email." is 14 characters, one over the caption limit, so G2 breaks the line differently from D3.

## Buttons kept, and why

| Button | Board | Reason |
|---|---|---|
| Undo | D3, G2 | Five seconds is too short to depend on being heard. Stopping must be sure. |
| Paste | E2 | Only the resident's tap is allowed in Facebook, and the tap is outside their page. |
| It went, It didn't go | E3 | Mary can't see Facebook's page, so this is how she finds out. |
| Send it | D2b | The one fallback for speech she can't make out, shown only then. |
| Tapping a card | B | Not a button: one big tap, for the same reason as Send it. |

Menu stays where it is on every board. `check.py` fails a board with any other button.

## Voice rules

- The person is whoever they named. If it's unclear she asks aloud, for example "Tyler or Caleb?", with no list on screen.
- Changes are by voice: they say what to change and she does it, on the card or the message.
- Sending needs a plain "send it" or the Send it tap. "Okay" in the middle of a chat doesn't count.
- She stays quiet during the count so she can hear "stop" or "undo". Nothing leaves the laptop until the count ends.
- After a send she offers only routes that are set up. With only print she asks only about print.
- The first send to an address, she asks aloud once: "Keep his address for next time?"
- If email isn't set up she goes straight to the routes that are.
- "Never mind" closes Facebook's panel. She closes it herself.
- The card words are the resident's. Mary only helps if asked, and she reads them back.

## Fonts, to bundle later

Boards load these from Google Fonts for now. All are SIL Open Font License.

| Font | Use |
|---|---|
| Pinyon Script | Foil names and card titles |
| Cinzel | Card lines and the month on the keepsake |
| EB Garamond | Verse, keepsake, picker labels |
| Cedarville Cursive | The cursive: their words, and the envelope address |
| Kalam | Plain handwriting, C4 |
| Fredoka | Her caption, from the round 6 shell |
| Baloo 2, Nunito | In the same font link from the round 6 shell; the other caption styles in `r6.css` |

Segoe UI, for panels, buttons and the plain message, comes with Windows and isn't bundled.

## Sizes

| Part | Where | Size |
|---|---|---|
| Mary | Left 40% (512px), the real aside move: translate -29%, scale .7, rotateY 16deg, perspective 1408px | |
| Caption | Style A, left 24, right 792 | 44px, 2 lines at most, 13 characters at most per line |
| Menu button | As in round 6, 28 from top and right; its shadow ends at y 130 | 223 wide, 96 tall |
| Title | x 512, y 28 to 124, width 450 | 36px bold |
| Content area | x 512 to 1252, y 140 to 768 | |
| Bottom row | x 512 to 1252, y 680 to 768 | 88 tall, 28px bold; Send it 300 wide, 32px bold |
| Card on D2, D2b, F | y 200 to 620, turned 1.5 degrees | 300 by 420 |
| Envelope on D2, D2b | Under the card by 100px, ends x 1252 | 532 by 372; name 38px, email 26px |
| Card and envelope on D3 | y 150 to 430 | 200 by 280 and 380 by 266; name 26px, email 20px |
| Going line on D3, G2 | y 466 to 510, centered | 32px semi-bold |
| Undo on D3, G2 | x 512 to 1252, y 530 to 714 | 740 by 184, word 56px bold, count 96px bold |
| Sent line on D3, G2 | Where Undo was, centered | 56px bold |
| Count | 8 seconds around: 1 second per digit, 3 seconds sent. Stacked digits, opacity only, no movement. Reduced motion: a plain 5 | |
| Sent on F | Beside the card | Check 110, name 44px bold, time 30px |
| Panel on E1 | x 512 to 1252, y 140 to 768, 3px border | Card 200 by 280, steps 32px, line 28px |
| Drawn page on E2, E3 | x 512 to 1252, y 134 to 664. 3px dark frame, page grey | One chat, no chat list. Text 22px and up, header 26px bold |
| Picture in the box, E3 | Left end of the box, which grows to 198 tall | 248 by 174 |
| Gold ring, E3 | Around Send, a board note | 100 across |
| Board notes | Dashed `.m8-note` | 20px semi-bold |
| Plain message | G: 640 by 440, G2: 640 by 280 | 32px Segoe UI |

Nothing on screen is under 20px, with one exception that `check.py` names: the words inside the E3 picture show at about 12px on the front and 10px inside. It's the card as a picture in their chat, and they've read those words at full size already.

Widest fits, counted at safe widths: the email on D3 needs 258 of its 278px, and the email on D2 needs 335 of 384px.

## Colors and contrast

| Use | Colors | Ratio |
|---|---|---|
| Titles, Going line, Sent line, sent note, Send it outline on her glow, darkest spot | #1f1b16 on #f6af74 | 9.2:1 |
| Card picker title on her glow, darkest spot | #2c1c18 on #f6af74 | 8.8:1 |
| Card picker numbers on her glow, darkest spot | #5e1a2e on #f6af74 | 6.8:1 |
| Undo and Paste, main style | #ffffff on #0f5560 | 8.4:1 |
| Envelope address, light and deep paper | #1c2a4a on #fbf3e2, #efe2c9 | 12.9:1, 11.1:1 |
| Envelope address, deepest grain, an estimate | #1c2a4a on #d2c6b0 | 8.4:1 |
| Plain message, light and deep paper | #1f1b16 on #fbf6ea, #f3e9d6 | 15.9:1, 14.2:1 |
| Plain message, deepest grain, an estimate | #1f1b16 on #dad1c0 | 11.3:1 |
| Verse inside the card | #2b2320 on #f0e4cc | 12.2:1 |
| Their handwriting inside the card | #1c2a4a on #f0e4cc | 11.3:1 |
| Date and age on the keepsake, Mary | #5e1a2e on #efe2c6 | 9.8:1 |
| Date and age on the keepsake, Sam | #1f3d2b on #e6dcbf | 8.7:1 |
| Memory lines on the keepsake | #2c1c18 on #efe2c6 | 12.7:1 |
| Reading text on a panel, the drawn page | #1f1b16 on #ffffff | 17.1:1 |
| Other buttons, board notes | #1f1b16 on #fffdf8 | 16.8:1 |
| Step numbers | #ffffff on #9b2c58 | 7.3:1 |
| Drawn page: blue bubble | #ffffff on #1f5fbf | 6.1:1 |
| Drawn page: "Type a message" | #544739 on #ffffff | 9.0:1 |
| Gold ring edge, on gold | #2b1f17 on #f2b632 | 8.8:1 |

Foil is the exception: the gilt names and titles are gradients, so no single ratio applies. They're large, held by a dark edge, and she always says the words aloud.
The glow colors are worked out from the CSS in `r6.css`, with the glow at full strength.

## Notes

- **The reminder comes once.** She says it in the first talk 8 to 5 days ahead, then it's done for the year, whatever they answer.
- **The Messenger page is our drawing.** It's one neutral grey chat, with no chat list, no Meta logo and no Facebook wordmark. The dark frame and the dashed note say so. The real page will look different.
- **Mary's controls live in her own bar,** under the panel, so the Paste tap never touches Facebook's page. The gold ring on `E3-Send` is a board note that shows where the Send button is.
- **Her Paste button is a proposal,** pending tests 5 and 9 in `docs/messaging-plan.md`. If they fail, this step changes.
- **Facebook shows in the panel beside Mary,** inside her own window, with no browser bar. That depends on test 9. If sign-in there is refused, Facebook opens in their normal browser, so `E2-Paste` and `E3-Send` need redrawing.
- **New unknown, untested:** whether Facebook's real chat lays out properly at about 740px wide. The boards show one chat with no list, as we expect at that width, but nobody has tried it.
- **Opening the chat on E1 is a proposal.** With no button, she opens it when she finishes her line, unless they say "not yet".
- **The card goes out as one picture,** front and inside together. That's a proposal, shown on `E3-Send`.
- No exclamation marks, emoji, stars, confetti or praise. Grown adults. The card art is drawn inline, with no outside pictures and no cute faces.

## How to rebuild

From `round8-src`: run `paint.py` only if a scene changed, then `build.py`, then `check.py`. `build.py` writes every board and `canvas.json`, and `check.py` exits 1 on any failure.
`check.py` covers tags, ids, references, captions, text sizes, banned words, the buttons on each board, animated properties, fit and heights.

## What can't be confirmed without a browser

These boards have never been opened; everything above is by calculation.

- The fonts: widths are estimated, and Cedarville's look on the envelope, including its @ sign, is unseen.
- The motion on `C3-Opens-Mary`, `D3-Sending-Mary` and `G2-Undo-Mary`.
- The envelope drawing, and how the card's shadow falls on it.
