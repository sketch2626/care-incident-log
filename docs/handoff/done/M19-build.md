# Handoff: M19 build, a secure address book (second account, branch `other/M19-build`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read:
- the **M19** section of `docs/mary-roadmap.md`: Andy's words, his board changes and his five answers;
- `docs/handoff/done/M19-design.md`, the design you build from;
- `mockups/mary/round10/README.md`, and the boards as needed;
- the M18 merge's report (`git log --grep "DONE: M18" -1 --format=%B`): how screens open inside Mary's page, the `use_screen` tool, the save gate and `memory_core.scrub_addresses`.

Then read only what you need of:
- `skills/messages/skill.py` (the contacts);
- `skills_core.py`, `send_gate.py`, `secret_store.py` and `memory_dates.py`;
- `server.py`, `mary.py` and `web/mary/screens.js`.

**Why:** Andy: "She obviously needs a secure address book… for everybody that she can think of… That's probably one of the more important things to this." And: "She should just be able to say email my daughter." It's built into the app; plug-ins ask permission to use it.

**Andy's answers override the design note where they differ:**
1. **After a first send** to someone new, she keeps the address and says so: "It's in your book now." She doesn't ask. (The note picked "ask once"; Andy took the other.) A resident who says "don't keep it" or "forget her" gets that, as always.
2. **"Forget Sarah"** clears her card, her reminders, and what Mary remembers about her.
3. **A Windows PIN at setup.** Add it to the helper's setup steps wherever they live. If there are none, say so.
4. **"Forget everything"** leaves the address book alone. The book can be cleared on its own.
5. **A helper's copy for a new laptop,** unlocked with six words kept on paper.

**Andy's board changes. The rule: if you can just ask Mary, it needs no button.**
- **The list:**
  - keep Up and Down;
  - under "Who are you after?" add a line like "If you need to scroll down, let me know.";
  - no "Add someone" button.
- **A person's card:** no All people, Change, Email Sarah or Make a card buttons.
- **The look before sending:** Send only, no "Not yet".
- **Changing someone:** no Forget or Put it back buttons.
- **Forgetting:** she asks once and "yes" does it. Keep "No, keep her" as the stop.
- **My doctors** stays a note and a board in M19, not built, as the design note says.

**Build in the design note's pieces, one checkpoint commit each.**
- **Pieces 1 to 4 have no screen**, so the contact fix lands early. Today saved addresses sit in incidents.db, so forget can't reach its 30 dated backups.
- **The `cryptography` package:** pin it in `packaging/requirements.txt` and install that version for the system Python, so the tests run. Don't run the build. Say if the installer needs anything else.
- **`mail.log`** already keeps a salted hash since M18. Don't redo it.
- **M18b is not this job.** That's voice filling in Normal and Offline. Mary's address-book tools follow M18's Live pattern.

**Tests prove:**
- the book file holds no readable name or address;
- a locked or missing key fails safely, with no plain fallback;
- the old contacts move in once and leave incidents.db and its backups;
- a plug-in without permission gets nothing;
- forget reaches the card, the reminders, the memories and the logs;
- "forget everything" leaves the book;
- the helper's copy round-trips only with the six words;
- nothing saves without a tap or a plain "save it";
- Gemini sees names and relationships, and a detail only when the resident's words ask for it.

**Rules:**
- Scratch data only. Never launch the app; no browser.
- Secrets use the test backend from `tests/helpers.py`.
- The safety sections of `mary/instructions.md` stay word for word. Quote any new lines in your report.
- Stay out of `bench/results/`.
- Memory is tight: if a test run is stopped, wait and retry once.
- If your context passes about 200K, commit `WAITING: context full`, listing the pieces done and the pieces left.

**Models:**
- Opus `coder`, `effort: "xhigh"`: pieces 1, 3 and 6 (the seal, the move and her tools).
- Opus `coder`: pieces 2, 4, 5 and 7.
- Sonnet `coder`: the tests and bench cases.

**Finish:** commit `DONE: M19 address book`. The message carries:
- three plain lines for Andy;
- what to try (these go on his test list);
- what isn't verified.

Then stop.
