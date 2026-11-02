# Handoff: M19 boards, a secure address book (second account, branch `other/M19-boards`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read:
- the **M19** section of `docs/mary-roadmap.md` (Andy's words);
- the **M18** section of `docs/mary-roadmap.md`, `mockups/mary/round9/README.md` and `docs/handoff/done/M18-design.md`: Mary comes along, small in the corner, and fills things in;
- `docs/messaging-plan.md` sections 5 (Contacts) and 6 (Privacy);
- the contacts parts of `skills/messages/skill.py` (around lines 820 and 1220-1500);
- `secret_store.py`;
- `memory_dates.py` (birthdays).

Read only what you need. Make the boards the same way as round 9 (`mockups/mary/round9-src/`).

**Why:** Mary can now send emails and cards, but there's no address book. Andy: "She obviously needs a secure address book… for everybody that she can think of… That's probably one of the more important things to this."

**Another worker (M18 build) is changing `web/`, `server.py`, `mary.py`, `skills/` and the tests right now.** You make boards and a design note only. Touch nothing outside `mockups/mary/round10/`, `mockups/mary/round10-src/` and `docs/handoff/done/M19-design.md`.

**Boards** in `mockups/mary/round10/`, with `canvas.json` and a README. Use made-up names only. Mary is small in the top-left corner on these screens, as M18 approved. Show:
1. **The address book:** a big, easy list of people, each with name and relationship. Find someone by voice ("show me Sarah") or by scrolling.
2. **One person's card:** name, relationship, phone numbers, email, mailing address, Facebook, birthday and notes. Big text, and plain labels.
3. **Adding someone by voice:** "My daughter Sarah, her email is…". Mary fills each field where they can see it, spells the email back, and asks "Is that right?" It's saved on a tap or their plain "save it", never by herself.
4. **Using it:** "Email my daughter" or "Make Sarah a birthday card" finds Sarah. Nobody says the address again.
5. **Changing and removing:** "Sarah's new number is…". "Forget Sarah" asks once, then really removes her, her address and her birthday reminders.
6. **A helper adding several people by typing,** with Mary there to help.

**Design note,** `docs/handoff/done/M19-design.md`, under about 120 lines. Cover:
- **Security:** how the address book is stored securely on the laptop.
  - Weigh encrypting it with a key kept in Windows Credential Manager (`secret_store.py`) against plain storage.
  - Say what daily backups would then hold, and what happens on a new laptop or after a restore (a helper's export and import?).
- **What Gemini sees:** names and relationships to find people. Details only when the resident's task needs them, or when they ask her to read something out. Details never go in her memories, talk history, logs or reports.
- **What carries over:**
  - moving M15c's contacts in;
  - birthdays feeding M15a's yearly reminders;
  - what "forget" reaches.
- **Keeping an address after a first send:** ask once ("Keep her address?"), or keep it in the address book by itself and say so. Give both, with your pick.
- **What the build would take,** in pieces.
- **Questions for Andy,** each answerable with one tap.

**Rules:** no browser and no screenshots. Check the boards by code and numbers only, and never launch the app.

**Models:** Opus coder for the boards and their builder. Write the design note yourself.

**Finish:** commit `WAITING: M19 address book boards for Andy`. The message carries:
- three plain lines for Andy;
- the board list;
- the questions for Andy.

Then stop.
