# Handoff: M18 build, Mary comes along into the menus (second account, branch `other/M18-build`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read:
- the **M18** section of `docs/mary-roadmap.md` (Andy's words);
- `docs/handoff/done/M18-design.md` (the design you build from);
- `mockups/mary/round9/README.md`, and the boards in `mockups/mary/round9/` as needed;
- the merge commit message of the boards (`git log -1 --format=%B 001b026`).

Then read only what you need of `web/mary/`, `web/` (the deeper screens), `server.py`, `mary.py`, `skills_core.py`, `send_gate.py` and `secret_store.py`.

**Why:** Andy, on the boards: approved. Going deeper from Mary must never end a talk. She comes along, small in the top-left corner, and helps on every screen. "That should have been a no-brainer for us."

**Andy's decisions (2026-11-01), all settled:**
1. **Size:** 132 by 132 in the corner, as on the boards.
2. **Save:** always in view at the bottom of forms.
3. **Saved incidents:** she reads the resident's saved incidents when they ask.
4. **The record:** an incident saved with her help says so, for example "Filled in with Mary's help". The resident's own words stay their own, never rewritten.
5. **Opening screens:** she opens any screen by voice. Andy: "She should definitely be able to open anything by voice, period, anything."
6. **Email addresses:** she can read and fill them, both the resident's own (Connect email) and a person's address they tell her. She spells a spoken address back for a yes. Andy: "emails are one of the harder things for an older person to type… she definitely needs to be able to add that." But addresses are never kept anywhere they could get out: not in her memories, not in talk history beyond the turn, not in any log or report. Where this loosens M15c's "Gemini gets names only" rule, Andy's word wins; say what you changed.
7. **Secrets stay out:** the email app password and the Gemini key. She can't see those boxes, never fills them, and says a helper can type them in (board D1).

**The rules from the boards:**
- She fills where the resident can see it, and asks "Is that right?" She never saves or sends by herself. Only a tap on Save, or the resident's own plain "save it", saves. Model this on `send_gate.py`'s plain-phrase check, so a chatty "okay" or a Gemini tool call alone can't save.
- Tapping small Mary, or "Back to Mary", brings her back full size with the talk still going.
- Her words sit beside her in the top band, never over the page. Nothing important is covered.
- Same for Sam.
- Every M17 rule stands:
  - Her name always wakes her.
  - "Back to Mary" stays in view at the top.
  - Nothing flashes the incident tracker.
  - Ending a talk leaves the wake word working.

**Build in pieces, one checkpoint commit each:**
1. **The talk survives.** Deeper screens open inside Mary's page, as the design note says, with the server's framing headers narrowed to same-site only.
2. **Small Mary and the band.**
3. **What Gemini sees of a screen,** plus the tools to open, explain and fill, with secrets cut out in core code.
4. **The save gate.**
5. **Incidents:** reading saved ones when asked, and the "Mary helped" note.

Tests prove:
- a talk survives opening and closing every deeper screen;
- secret fields never reach Gemini or a log;
- an address never lands in memories or logs;
- nothing saves without the tap or a plain "save it";
- the wake word still works on every screen.

**Rules:**
- Scratch data only. Never launch the app; no browser.
- Stay out of `bench/` results and `packaging/`.
- The safety sections of `mary/instructions.md` stay word for word. If she needs new lines, put them where the design note says and quote them in your report.
- Memory is tight: if a test run is stopped, wait and retry once.
- If your context passes about 200K, commit `WAITING: context full`, listing the pieces done and the pieces left.

**Models:**
- Opus coder, `effort: "xhigh"`: pieces 1, 3 and 4.
- Opus coder: pieces 2 and 5.
- Sonnet coder: the tests.

**Finish:** commit `DONE: M18 Mary comes along`. The message carries:
- three plain lines for Andy;
- what to try (these go on his test list);
- what isn't verified, including Paste inside the frame on the real desktop app.

Then stop.
