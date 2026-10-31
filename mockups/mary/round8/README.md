# Mary round 8: cards and messages to family

Static boards for M15, 1280x800, in the round 7 file shape. No app code. Open them with `canvas.json`.
`r6.css` is an unchanged copy of round 6; `r8.css` holds only the new classes (`.m8-*`). Every board links both.
All names and addresses are made up: Mom, her son Mark Hollis, her daughter Ellen Hollis, her grandson Tyler Hollis.

## The boards

| Board | What it shows | Her line, in full | Caption on screen |
|---|---|---|---|
| `A-Reminder-Mary` | The reminder: calendar page, Mark's birthday, three answers | Mark's birthday is next Saturday. Want to make him a card? | Want to make him a card? |
| `A-Reminder-Sam` | The same in Sam's look | Mark's birthday is next Saturday. Want to send him a card? | Want to send a card? |
| `B-Design-Mary` | Five pictures and "Make a new picture"; the bass is picked | Which one suits him? | Which one suits him? |
| `C-Card-Mary` | The card large, with their words printed on it | Here's how it reads. (Then she reads the card aloud.) | Those are your words. |
| `D1-Who-Mary` | Who gets it, and how it goes; Mark and email are picked | Email or Messenger? | Email or Messenger? |
| `D2-LastLook-Mary` | The last look: the card, the person and the way | Send it to Mark? | Send it to Mark? |
| `E1-Open-Mary` | Messenger, still in her app: three plain steps | Facebook keeps the Send button for you. I'll get it all ready. | Your hand on this one. |
| `E2-Paste` | The chat page open, with her slim strip over it and a Paste button | Tap Paste to put the card in. | The strip text: Tap Paste to put the card in. |
| `E3-Send` | The card in the message box, ready; the strip asks if it went | Now tap Send in the chat. | The strip text: Now tap Send in the chat. |
| `F-Sent-Mary` | Sent by email, when, and whether to keep the address | It's on its way. | It's on its way. |
| `G-Message-Mary` | A plain message to Tyler, no picture | Here's what I've got. Is that it? | Is that it? |

The brief gave her full line for A, C, E1 and G. On the other boards her line is proposed, and it's the same as the caption.

## Sizes

| Part | Where | Size |
|---|---|---|
| Mary | Left 40% (512px), same move as the real aside: translate -29%, scale .7, rotateY 16deg, perspective 1408px | |
| Caption | Style A, left 24, right 792 | 44px, 2 lines at most, 12 characters at most per line |
| Menu button | As in round 6, 28 from top and right; its shadow ends at y 130 | 223 wide, 96 tall |
| Title | x 512, y 28 to 124, width 450, so 290px stays clear on the right | 36px bold |
| Panel | x 512 to 1252, y 140 to 664 | 3px border |
| Picture tiles | 3 by 2, x 512 to 1252, y 134 to 664 | 240 by 258, name 24px bold, ring 8px |
| Printed words on the card | Under a 280 tall picture | 32px, "Love, Mom" semi-bold |
| Person and way buttons | Rows at y 140 and y 406 | 236 by 200, 236 by 244, name 32px bold |
| Bottom row | x 512 to 1252, y 680 to 768 | 88 tall, 28px bold, at most 3 buttons |
| Mary strip | x 0 to 1280, y 0 to 104, 6px bottom border | Text 28px bold, face 96 |
| Strip buttons | Inside the strip | Paste and It went 200 wide, 84 tall; It didn't go 84 tall; Back to Mary 72 tall |
| Drawn page | x 0 to 1280, y 104 to 800, dashed outline | Text 22px and up |
| Board notes | Dashed, on the drawn page only | 20px semi-bold |

With Segoe UI Bold counted at 0.56em per character, the longest bottom row, "Change the words", "Other picture", "This is it", needs 716 of the 740px.
"Church at sunrise" needs 228 of the 234px inside a tile. "Make a new picture" and "Tell Mary what to draw" wrap to two lines each in their tile.

## Colors and contrast

| Use | Colors | Ratio |
|---|---|---|
| Reading text on a card, panel or tile | #1f1b16 on #ffffff | 17.1:1 |
| Titles and "How should it go?", Mary, darkest spot of the glow | #1f1b16 on #f6af74 | 9.2:1 |
| The same in Sam's look, darkest spot of the glow | #1f1b16 on #d99642 | 6.8:1 |
| Main button | #ffffff on #0f5560 | 8.4:1 |
| Other buttons | #1f1b16 on #fffdf8 | 16.8:1 |
| NOV, step numbers, checks, picked initial, Mary | #ffffff on #9b2c58 | 7.3:1 |
| NOV on the calendar, Sam | #ffffff on #1b5a8c | 7.3:1 |
| Initials not picked | #ffffff on #544739 | 9.0:1 |
| Picked ring on white, Mary | #9b2c58 on #ffffff | 7.3:1 |
| Strip text | #1f1b16 on #fff0d2 | 15.2:1 |
| Board notes | #1f1b16 on #fffdf8 | 16.8:1 |
| Drawn page: grey bubble | #1f1b16 on #e4e6eb | 13.7:1 |
| Drawn page: blue bubble | #ffffff on #1f5fbf | 6.1:1 |
| Drawn page: address | #1f1b16 on #ffffff | 17.1:1 |
| Drawn page: "Type a message" | #544739 on #ffffff | 9.0:1 |
| Gold ring edge, on gold | #2b1f17 on #f2b632 | 8.8:1 |

The glow colors are worked out from the CSS in `r6.css`, with the glow at full strength.

## Notes

- **The reminder comes once.** She says it in the first talk 8 to 5 days ahead, then it's done for the year, whatever they answer.
- On Sam's boards, every "Back to Mary" reads "Back to Sam", and "Tell Mary what to draw" reads "Tell Sam what to draw".
- **The Messenger page is our drawing.** It's a neutral grey-white chat with no Meta logo and no Facebook wordmark. The dashed outline and the note in its corner say so. The real page will look different.
- The strip belongs to our app, and the page under it is theirs. Mary draws nothing on their page. The gold ring on `E3-Send` is a board note that shows where the Send button is.
- **The strip's Paste button is a proposal,** pending test 5 in `docs/messaging-plan.md`. If that test fails, this step changes.
- **Mary can't see whether it went, so she asks.** The strip's "It went" and "It didn't go" are how she finds out.
- **The five-second Stop after an email yes isn't drawn.** It comes after the last look, in place of the plain "Sent". It needs its own board if Andy wants to see it.
- Sending happens only from the last look, and only after a tap or a plain "send it". "Okay" in the middle of a chat doesn't count.
- The card words are the resident's. Mary only helps if asked, and she reads them back.
- No exclamation marks, emoji, stars, confetti or praise. Grown adults. The card art is drawn inline, with no outside pictures, and no cute faces.
- The main button is teal, at the end or as the natural next step. On `F-Sent-Mary` that's "Keep it", in the middle, with "Back to Mary" at the end. That's a proposal.
