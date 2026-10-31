# Handoff: M15d core, a safe place for secrets, and email sending (second account, branch `other/M15d-core`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read:
- `docs/messaging-plan.md`: "Email" and "Keeping the secret safe" (section 1), "Privacy" (section 6), the start of section 8 and the M15c and M15d rows, and decisions 2 and 4 in section 9;
- in `server.py`: `SETTING_KEYS` (about line 70), and every place that reads or writes `gemini_key` (about lines 394, 454, 771 and 1675);
- `assist.py` and `voices.py`, where the key is used and scrubbed;
- `skills_core.py`, around `ctx.fetch` (about line 662), and how a skill's card lists what it may use.

**Why:** cards and messages (M15) need to send email, and the plan says the mail secret lives only in Windows Credential Manager. Separately, before the pilot, the resident's Gemini key must stop sitting in the settings table as plain text. That table is copied into every daily backup. This piece builds the groundwork for both. The cards worker (`other/M15b-cards`) is running at the same time, so this stays in core files.

**Build:**
1. **`secret_store.py` (new).** Don't name it `secrets.py`, which is a standard Python module.
   - Windows Credential Manager through `ctypes` (CredWriteW, CredReadW, CredDeleteW, generic credentials). No new package.
   - **The entry name includes a hash of the data folder** (`TRACKER_DATA`/`APPDATA`). A scratch or test install must never see the real resident's secrets. This matters: installer checks run the frozen app with a scratch `APPDATA`.
   - It handles the 2,560-byte limit (split into parts or refuse plainly) and works away from Windows with a clear "not available" answer.
   - Tests use an in-memory backend. Only one opt-in round-trip test may touch the real Credential Manager, with a random `CareIncidentLog-test-…` name that it deletes afterwards. Never read or write any other entry.
2. **Move the Gemini key.**
   - On startup, if `settings` holds `gemini_key`, move it into the secret store and remove it from `settings`.
   - Saving a key in My info goes straight to the store. Everything that used `s["gemini_key"]` reads from the store.
   - The page still sees only `gemini_key_set`.
   - **Old backups still hold the key.** Don't change backups. Report how many hold it, and propose what to do, for Andy.
3. **`mail_core.py` (new) and `ctx.send_mail`.**
   - SMTP for Gmail (`smtp.gmail.com`) and Yahoo (`smtp.mail.yahoo.com`), with TLS and certificate checks (`ssl.create_default_context()`). Use the address and app password from the secret store.
   - Send plain text plus pictures, for the card's front, inside, and both side by side.
   - **The skill never sees the secret.**
   - **No send without a ticket:** `ctx.send_mail` refuses unless it's handed a one-time send ticket that only the core can mint. M15c will mint it from the resident's "send it" and the five-second Undo. For now, the core mints tickets only in tests. A test proves a skill can't make, reuse or forge one.
   - Each send is logged (when, to which address, success or the error code), never with the message or secret. List `send_mail` on a skill's card, the way `fetch` is listed.
   - Friendly error codes: no email set up, wrong password, offline, refused.
4. **Helper setup in My info: "Connect email".**
   - Their address, Gmail or Yahoo, and one paste box for the app password, with short plain steps for making one.
   - "Send a test to myself" checks it.
   - Text ≥20px, targets ≥64px.
   - The password never comes back to the page, and "Disconnect" removes it.

**Tests** with a fake SMTP server (a small socket server in the test, since Python 3.12 has no `smtpd`) cover:
- a send with pictures;
- a wrong password;
- offline;
- no ticket;
- the key moved out of `settings` and never in backups made after the move, logs, the page or a Gemini request;
- a scratch data folder never reading another folder's secrets.

Make no real email sends, and use no real accounts or keys.

**At the same time:** M15b cards (`other/M15b-cards`) is changing `skills/messages/`, `web/mary/fonts/` and maybe parts of `server.py` and `mary.py`. Stay out of `skills/messages/`. Before your last commit, run `git merge main` (the hub may have merged cards by then) and resolve anything small.

**Usage:** her account is being used up to its weekly limit before it resets at 4:59pm. If you're stopped by a limit, the hub tells you to continue after the reset. Commit after each piece so a stop loses little.

**Memory is tight** on this 5.7 GB laptop. If a test run is stopped for memory, wait a few minutes and retry once.

**Stay out of:** `bench/`, `tools/brain_bench.py`, `packaging/`, `mockups/` and `skills/messages/`. The safety sections of `mary/instructions.md` stay word for word.

**Models:**
- Opus coder, `effort: "xhigh"`: the secret store, the key move and the send ticket.
- Opus coder: SMTP and My info.
- Sonnet coder: the tests.

**Finish:** commit `DONE: M15d core: secrets in Credential Manager, ctx.send_mail ready`. Include:
- three plain lines for Andy;
- what isn't verified (a real Gmail or Yahoo send needs a helper and a real account);
- the backups question for Andy;
- anything the hub needs to merge.

Use `WAITING:` if something needs Andy first. Then stop.
