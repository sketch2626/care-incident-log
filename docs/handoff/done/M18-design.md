# M18 design note: Mary comes along into the menus

Proposal for Andy, drawn on the boards in `mockups/mary/round9/`. Nothing here is built. Andy's words are in the M18 section of `docs/mary-roadmap.md`.

## How the talk survives

**What happens today.** Mary's page is `web/mary.html`. Things Mary can do, Games, My info and Choose are panels inside it, so those don't end a talk, but they do cover her. The deeper screens (the incident form, the list, reports, and the My info with name, room and keys) live in `web/index.html`, a separate page. "More settings" and Open My info load it with `/?from=mary`. Loading it fires `pagehide` on her page, which stops her mic, her speech and the Live connection. A Live connection can't be handed from one page to another, so her page has to stay open.

**Decision: the deeper screens open in a frame inside Mary's page.** `index.html` and its `app.js` run almost unchanged, in the area under a top band. Her page never unloads, so Live, the mic, the wake word and her captions all carry on. Going back only hides the frame.

Turned down:
- Moving the deeper screens into `mary.html`: rewrites most of 1,190 lines of `web/app.js` and mixes two style sheets, for no gain to the resident.
- A second window: two windows to manage, and a big step backwards for someone working by voice.

**One Mary, shrunk.** `face.js` keeps drawing into the same `#face` box, and CSS moves it to the corner, the same way her aside move works today. There's no second face, so moods, speech and the one voice stay as they are. Captions get a band position in CSS.

**The band.** y 0 to 156, always in view: Mary 132 by 132 at top left, her words beside her, "Back to Mary" at right. The frame starts at y 156 and scrolls on its own, so the band can't cover anything. The existing panels get the same treatment, so she's small there too instead of hidden behind a sheet.

**Things that must change for the frame to work** (found by reading the code; none of it tested yet):
1. `server.py:1297` sends `X-Frame-Options: DENY` and `frame-ancestors 'none'` on every page, which blocks the frame. Change them to `SAMEORIGIN` and `frame-ancestors 'self'`. Outside websites stay blocked, which is what the rule is for.
2. **Paste.** The Paste buttons use the desktop window's `paste_text`, and that may not reach inside a frame. The frame needs `allow="clipboard-read"` and a fallback through the parent page. The pasted secret must go straight into the box and never near Live. Test this one first, on the real desktop app.
3. **Two mics.** The form's "Tap and talk" buttons use the on-laptop mic (`/api/listen`), which would fight Live for it. While she's in a talk, those buttons are hidden, because she's the mic. When she's asleep they work as they do today.
4. `#backToMary` (`web/app.js:820`) loads `/mary.html`. Inside the frame it must not show at all, because the band has the button. A small `in=mary` flag handles that.
5. **Timeouts.** Panels go back to her face after 2 minutes alone (`PANEL_IDLE_MS`). The deeper view must not do this during a talk or with unsaved changes.
6. **Report printing and the spreadsheet download** from inside a frame: check both still work.

**Safety.** The emergency check runs first, as it does now: `liveToolGate` already refuses every tool on an emergency turn. New: an emergency while she's small brings her straight to the full emergency screen. The frame is hidden, not closed, so a half-filled form isn't lost. The safety wording doesn't change.

**Sam** is the same code with his name and look.

## What Gemini sees of a screen

**It asks; the page doesn't push.** Moving to a screen tells her its name only ("My info"). She gets the fields by calling `look_at_screen`, when the resident asks something that needs them. A resident who never asks sends nothing new to Google. That fits "their words stay on their laptop, except in the packet for one reply".

**A hand-written list decides what exists.** New file `web/mary/screens.js`, one entry per screen: field id, plain label, kind, choices, a one-line explanation, and whether she may fill it. The page never scans the screen, so a field nobody listed is a field she can't see. A new field stays invisible to her until someone decides.

What `look_at_screen` returns:
- Labels, choices and explanations.
- The resident's own values for the listed fields on the screen they're looking at.
- For a secret: its label and "secret". No value, and not even whether it's filled. That's how she knows to say she won't touch it.

**Never sent:**
- The Gemini key, the app password, or anything with `type="password"`. A test walks `index.html` and fails if any password box is in the list, or if the card ever holds one.
- Andy Flow items.
- The list and report screens: labels only for now (question 3). Saved incidents can name staff and neighbors, and those screens are the likeliest place for someone else's details.

**Another resident's data.** The laptop holds one resident's log, so no other resident's record can appear. What can appear is a name inside this resident's own words, for example a roommate in "Did anyone else see it?". It goes only when they've asked about that screen. It's not added to her memory unless they say so.

## The tools she'd use

Page tools, answered by the page, like `story_more` and `end_talk` in `LIVE_PAGE_TOOLS`. They're not skills, because they act on the resident's own screen and need no internet.

| Tool | Does | Limits |
|---|---|---|
| `look_at_screen` | Returns the card above | Listed fields only |
| `explain_field(field)` | Lights the field and scrolls it into view under the band. She explains it in her own words | Only when asked. No narrating what they can see |
| `fill_field(field, value)` | Lights the field, scrolls it into view, types the value so they see it arrive. She asks "Is that right?" | Only fields marked fillable. Never the secrets. Nothing is saved |
| `open_screen(name)` | Opens a deeper screen when they ask | Listed screens only |
| `go_back` | Same as tapping her | |

**"Put it back"** returns the field to what it was. The page keeps the old value for every fill.

**What stays the resident's:**
- **Saving.** A tap on Save, or their plain "save it". There's deliberately no save tool for her to call on her own say-so. The page checks the words the resident actually spoke, with a new `is_plain_save`, built like `is_plain_send` in `send_gate.py` (same stop words). "Save it? I don't know yet" doesn't count, and neither does "yes" after "Is that right?": that confirms the field, not the form.
- **Sending, and every send.** No change. `send_gate.py` still owns it.
- **Secrets.** A helper types them, or the resident pastes.
- **Privacy switches.** Smart helper, Connect Andy Flow, Connect email. She explains them, never flips them.
- **Deleting and removing anything.**
- **How bad it was.** On an incident she explains Minor, Serious and Dangerous, and the resident picks. That's a judgment, and it's their record.
- **Their words.** "Your words" stays what they said. She fills other answers from it and never rewrites it. Evidence-grade means the words are theirs.

**Other talk modes.** Normal needs the same tools through the server's tool path, sent to the page as effects, so it's a later piece. With no working key she has no brain to fill with: she stays in the corner, and the resident fills the form by hand. Check at build time what Offline's brain can really do.

**Instructions.** A short new section in `mary/instructions.md`: what the tools are for, say the value back and ask, never claim something is saved until it is, and say plainly when a field is a secret. Safety sections stay word for word. New bench cases: she refuses the secret, she doesn't say "saved" early, she doesn't narrate the screen.

## What it would take to build

| Piece | What | Stands alone? |
|---|---|---|
| 1 | `is_plain_save` in Python and its page copy, with tests | Yes, new code |
| 2 | `web/mary/screens.js`: the field list, the card, the no-secrets test | Yes, new file. Good for the second account |
| 3 | The frame, band, shrink and grow, captions in the band, the server header, `in=mary`, Paste, the mic rule, timeouts, emergency return | No: it's the heart. Touches `web/mary/app.js`, `mary.html`, `mary.css`, `web/app.js`, `server.py`. Opus coder, one worker |
| 4 | Panels under the band | Small, right after 3 |
| 5 | Tools and field lighting, instructions, bench cases | Needs 1, 2 and 3 |
| 6 | Normal mode | Needs 5 |

Order: 1 and 2, then 3, and Andy tries the talk carrying on before anything else. Then 4 and 5, then Andy tries filling. Then 6. Piece 3 is the risk: it's the only one touching her live page, so it goes behind a test on the real desktop app, with Paste checked first.

## Questions for Andy (one tap each)

1. **How big is she in the corner?** 132 is on the boards, and her moods should still read at that size. [Keep 132] [Bigger, about 180]
2. **Keep Save always in view at the bottom of forms?** Today it's at the end of a long scroll. [Yes] [Leave it at the end]
3. **Can she read your saved incidents when you ask, on the list and report screens?** They can name staff and neighbors, and they'd go to Google for that reply. [Yes, when asked] [Only the one I have open] [No]
4. **Should a saved incident say Mary helped fill it in?** It's honest and an inspector may ask, but it could give a facility something to argue about. [Yes, say so] [No]
5. **Can she open screens when asked ("take me to My info")?** [Yes] [No, tapping only]
