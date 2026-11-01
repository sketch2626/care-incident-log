# Mary round 9: she comes along (M18)

Going from Mary into a deeper screen used to leave her page, and the talk ended. Andy: "there should be a place in the top left that Mary can shrink down... That way you can still talk to her... she can help answer questions about things in the menu... and fill things out for you herself."

Static boards at 1280x800 with no app code. Open them with `canvas.json`.
Every board comes from `round9-src/build.py`. `r6.css` is an unchanged copy of round 6; `r9.css` holds the new `.m9-` classes.
All data is made up: resident Ruth Hollis, room was 108, now 214, Pine Hollow Care Center, 100 Example Road, NC, ruth.hollis@example.com.

## Boards

| Board | What it shows | Her full line, aloud | Caption on screen |
|---|---|---|---|
| `A1-Full-Mary` | Full page, big face, mid-talk, Menu closed | That's in My info. Open the Menu and I'll come along. | That's in / My info. |
| `A2-Menu-Mary` | Full page with the Menu open: Stop talking, Things Mary can do, My info, Choose Mary or Sam, Games, Close Mary | Tap My info. | Tap My info. |
| `A3-MyInfo-Mary` | My info with small Mary in the band: five fields and the Save row | Here it is. Tell me what to change, or ask about anything on here. | Tell me what to change, / or ask about anything here. |
| `B1-Fill-Mary` | They said "Put my room number as 214." The room field is lit and fills in: 2, 21, 214, moving | Room 214. Is that right? | Room 214. / Is that right? |
| `B2-Saved-Mary` | After their plain "save it" or a tap on Save: field no longer lit, a plain check and Saved beside Save | Saved. | Saved. |
| `S1-Fill-Sam` | B1 in Sam's look, his face, Back to Sam | Room 214. Is that right? | Room 214. / Is that right? |
| `C1-Explain-Mary` | Incident form, their words left, the two questions right. How bad was it? is lit, nothing chosen | That one's your call. Serious means it hurt you or really upset you. Dangerous means you could have been badly hurt. | Serious means it hurt you / or really upset you. |
| `C2-FillForm-Mary` | The same form, How long did you wait? lit, 2+ hours chosen from their words | More than two hours. Is that right? | More than two hours. / Is that right? |
| `D1-Secret-Mary` | Connect email: address filled, Gmail chosen, App password box with a lock, Paste, and "Mary can't see this box." | I won't read or fill that one. It's a password, so it stays out of my hands. A helper can type it in. | I won't read or fill that one. / A helper can type it in. |
| `E1-Grow-Mary` | Tapped small Mary or Back to Mary. She grows from the corner to full size, moving; the page fades out | That's done. Now, the coast. Go on. | That's done. in the band, then Now, the / coast. Go on. at the bottom once the page has gone |
| `E2-Back-Mary` | Full page, talk still going, no restart and no new hello | That's done. Now, the coast. Go on. | Now, the / coast. Go on. |
| `N-Notes` | Plain notes: where her words sit, how big she is, nothing is covered | | |

The resident's own words never appear as a caption. What they said sits in a dashed board note.

## The rules these boards show

- She never saves or sends by herself. A tap on Save, or their plain "save it", does that.
- Their words stay their own. She fills answers from what they said and never rewrites them.
- A choice that is a judgment stays theirs: she explains the words and doesn't pick.
- She won't read or fill a secret, such as the App password or the Gemini key. A resident or a helper types those in.

## Buttons kept, and why

| Button | Board | Reason |
|---|---|---|
| Menu (Hide menu when open, the real app's words) | A1, A2, E2 | Her one button on the full page |
| The six menu items | A2 | The real menu |
| Back to Mary, Back to Sam | Every deeper board | A big sure way home, in view always |
| Save | A3, B1, B2, S1, C1, C2, E1 | The resident's own say-so, by tap |
| The form's choices | C1, C2 | The real form. Tapping still works for anyone who would rather not talk |
| Gmail | D1 | The form's choice, shown chosen. Yahoo is left off because these boards name no company but Gmail |
| Paste | D1 | The real app has it, so no key combos are needed |
| Connect email | D1 | The real form's step |
| Tapping small Mary | Every deeper board | Not a `<button>`: a 132px tap target that does what Back to Mary does |

`check.py` fails a board with any other button.

## Sizes

| Part | Where | Size |
|---|---|---|
| Top band | y 0 to 156, her warm background, never scrolls | 1280 by 156 |
| Small Mary | x 16, y 12 | 132 by 132, her real face, viewBox `180 50 280 280`, in a plain circle |
| Mood ring | Around the circle, 5px inside and a soft glow out. It takes her listening and thinking colors from the same classes as her edge glow | |
| Her words | x 164 to 864, centered in the band | Fredoka 600, 32px, 2 lines, 32 characters a line at most |
| Back to Mary | x 884 to 1252, y 28 to 124 | 368 by 96, 34px bold |
| Page | y 156 to 712, scrolls on its own | Segoe UI, cream #fbf7ef |
| Bottom row, a proposal | y 712 to 800, stays in view | 88 tall; Save 300 by 72, 32px bold; Connect email 380 by 72 |
| My info rows | Label x 56 to 412, field x 420 to 1224 | Fields 72 tall, label 26px, value 28px |
| Choices | C1, C2 | 64 and 72 tall, 24 to 26px, hints 22px |
| Lit | Field or question | 5px #f2b632 ring, 3px #2b1f17 outer edge, #fff1c7 fill |
| Full-page caption | Style A | 44px, 2 lines, 13 characters a line at most |
| Board notes | Dashed `.m9-note` | 20px semi-bold |
| N-Notes | | Headings 40px, words 30px |

Motion: B1 and S1 loop 4.8 seconds on stacked opacity, nothing moves, and reduced motion shows 214. E1 loops 3 seconds: transform on her and opacity on the page, and reduced motion shows her at full size with the page gone. Her start in E1 is translate -68.86, -11.57 scale .23571, which puts her head on the small circle.

Fonts: Fredoka for her caption, from the round 6 shell, on Google Fonts for now and to bundle later. Segoe UI comes with Windows.

## Colors and contrast

| Use | Colors | Ratio |
|---|---|---|
| Value on a lit field | #1f1b16 on #fff1c7 | 15.2:1 |
| Value on a plain field | #1f1b16 on #ffffff | 17.1:1 |
| Labels on the page | #1f1b16 on #fbf7ef | 16.0:1 |
| Hints | #544739 on #ffffff | 9.0:1 |
| Save, Paste, a chosen option | #ffffff on #0f5560 | 8.4:1 |
| Her words, Mary | #9b2c58 on the white edge | 7.3:1 |
| Her words, Sam | #1b5a8c on the white edge | 7.3:1 |
| Back to Mary | #2b1f17 on #fffdf8 | 15.8:1 |
| Notes board on her glow, darkest spot | #1f1b16 on #f6af74 | 9.2:1 |

## How to rebuild

From `round9-src`: run `build.py`, then `check.py`. `build.py` writes every board and `canvas.json`, and `check.py` exits 1 on any failure. The rectangles live in `build.py` as data and `check.py` imports them.
`check.py` covers tags, ids, references, captions, text sizes, banned words, the buttons on each board, targets, animated properties, the band and page rectangles, every box's position, text fit, contrast, the face crop, E1's timing, `canvas.json`, and this README's lines.

## What can't be confirmed without a browser

These boards have never been opened; everything above is by calculation.

- The fonts: widths are estimated. Fredoka at 32px with the thinner white edge is unseen.
- The motion on `B1-Fill-Mary`, `S1-Fill-Sam` and `E1-Grow-Mary`, and how her face looks partway through the grow.
- Her face at 132px: whether her moods still read at that size, and how visible the warm ring is on her warm band.
- `A2-Menu-Mary`: the open Menu covers part of her face, as it does in the real app.
