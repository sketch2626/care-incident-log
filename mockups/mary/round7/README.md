# Mary round 7: word search

Static boards for M7a, 1280x800, in the round 6 file shape. No app code. Open them with `canvas.json`.
`r6.css` is an unchanged copy of round 6; `r7.css` holds only the game classes (`.ws-*`). Every board links both.

## The boards

| Board | What it shows | Her line |
|---|---|---|
| `A-Fresh-Mary`, `A-Fresh-Sam` | A fresh puzzle, in each look | Fishing it is. Take your time. |
| `B-Found-Mary` | TROUT just found, with a soft glow once; BASS and WORM found earlier | There's your trout. Good eye. |
| `C-Hint-Mary` | The hint: the third row in pale gold (step 1) and its C in solid gold (step 2) | Third row. It starts with that C. |
| `D-Done-Mary` | All words marked, a plain line in the title row, four buttons | Good one. Want another? |
| `E-Sizes-Mary` | 8 by 8 with 6 words, to compare sizes | Bigger letters, fewer words. |
| `F-Picked` | Detail: first letter tapped, ring on it. The label is a board note, not part of the app | (none) |

## Sizes

| Part | Where | Size |
|---|---|---|
| Mary | Left 40% (512px), same move as the real aside: translate -29%, scale .7, rotateY 16deg, perspective 1408px | |
| Caption | Style A, left 24, right 792 | 44px, 2 lines at most |
| Menu button | As in round 6, 28 from top and right | 223 wide (measured from Segoe UI Bold), 96 tall |
| Title | x 512, y 24 to 124, 290px kept clear on the right | 34px bold |
| Grid 10x10 | x 512, y 124, 540 square | 54px cells, 34px letters |
| Grid 8x8 | Same corner, 528 square | 66px cells, 42px letters |
| Word list | x 1068 to 1252, one word per grid row | 26px bold |
| Bottom row | x 512 to 1252, y 680 to 768 | 88 tall, 28px bold |

The grid's 4px border is drawn on top of the cells, so they stay exactly 54px.
With the longest word, CATFISH, the list text ends at x 1206.

## Colors and contrast

| Use | Colors | Ratio |
|---|---|---|
| Letters in the grid | #1f1b16 on white | 17.1:1 |
| Letters in a found mark | white on teal #0f5560 | 8.4:1 |
| Letters on the hint row | #1f1b16 on pale gold #ffe7a3 | 14.0:1 |
| Lit first letter | #1f1b16 on gold #f2b632 | 9.4:1 |
| Ring on the lit letter | #2b1f17 on gold #f2b632 | 8.8:1 |
| Picked ring, Mary | #9b2c58 on white | 7.3:1 |
| Picked ring, Sam | #1b5a8c on white | 7.3:1 |
| Words in the list | #1f1b16 on the glow, darkest spot | 9.1:1 on Mary, 9.0:1 on Sam |
| Found words in the list | #544739 on the glow, darkest spot | 4.8:1 on Mary, 4.75:1 on Sam |

Found words use #544739, not #5a4d40. The list sits in the edge glow, and #5a4d40 only reaches 4.4:1 on Mary and 4.3:1
on Sam at the darkest spot behind the words (worked out from the glow's CSS, glow at full strength). The check mark and
the thick line say "found" more clearly than the color does.

## Notes

- The puzzle is real: words run across and down only, with no bad words in the filler and each word in the grid once.
  CREEL is across in the third row, and that row holds no other C.
- No timers, scores, stars, confetti or praise. No exclamation marks in her lines. A grown-up friend, not a children's show.
- The glow on a found word plays once on load, so reload the board to see it again. It's skipped with
  `prefers-reduced-motion`, through the rule in `r6.css`.
- The found mark is a shape, so it reads for weak eyes and colorblind eyes. Its thin white edge keeps neighboring words apart.
- The `Same` button is the teal one at the end, as the likely next step. That's a proposal.
- On Sam's boards, every "Back to Mary" reads "Back to Sam".
