# Handoff: M4g, brain fixes from bench run 5 and the first real-Live pass (second account, branch `other/M4g`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read:
- the **M4g** and **M20** sections of `docs/mary-roadmap.md` (the findings, with the replies quoted);
- the failing entries only in `bench/results/2026-11-01_0240.txt` (run 5, Normal and the Live stand-in) and `bench/results/2026-11-01_0424.json` (the real Live model, gemini-3.8-live);
- `CHARACTER_NOTE` in `mary.py`, its threat line (M4f), and wherever `mary.py` builds Live's system text;
- in `mary/instructions.md`, the safety sections (the medical one and "When they talk of hurting someone"), and the new "Working on their screens" section (M18);
- `tests/test_m4e.py`, and the tests that check `CHARACTER_NOTE`;
- `bench/variants/lean-mary.md` and `lean-sam.md`;
- `skills/messages/skill.py` near line 799 ("Let's pick a front first.") and `REMINDER_CARDS_LINE`.

Read only what you need.

**Why:** Andy is testing Mary now, and he still hears "a little bit of that patronization". The bench agrees, and the real Live model, tested for the first time, behaves worse than the stand-in in medical moments. Residents will meet both.

**Fix, Mary and Sam, Normal and Live:**
1. **Name someone when there's talk of hurting a person.** That covers a plan, their own threat ("I'll fight back") and plain venting. The same reply names at least one person to turn to: staff or a nurse, family, the chaplain, or the ombudsman. For danger right now, the call light and 911. Do it the way a friend would: no orders, no "you can't" or "you need to".
   - M4f's warmer line took the people out along with the orders. Run 5's reply: "I won't help with that. But I'm listening. What's brought you to this?"
   - When the resident is the one being hurt and also threatens back, take up both: what was done to them, and their own words.
2. **No talking down.** No praising the ordinary ("That's a good way to start the day", a voting record "to be proud of"). No scolding ("please don't talk like that"). A grown adult talking to a grown adult.
3. **Sam isn't curt.** "Harold. Evening." is too little. A short hello is fine; a bare one isn't.
4. **Real Live in medical moments:**
   - no boilerplate disclaimers ("not medical advice or diagnosis", "see a healthcare professional");
   - no clinical words ("edema"), just plain ones;
   - after the emergency line, one kind sentence ("Then stay calm and kind" isn't happening);
   - a health worry with no emergency (swollen legs, a missed pill) gets a plain "ask your nurse" or "ask your doctor".
   The real Live model is a different model from the text one, so check what Live's system text actually carries.
5. **M20, the newest feature isn't her whole act.**
   - Reword "Let's pick a front first." and any line like it that pushes cards.
   - `REMINDER_CARDS_LINE` goes only with a birthday reminder.
   - Make sure nothing in her prompt invites card offers in an ordinary chat.
6. **The lean variants** get the same changes, plus M18's "Working on their screens" section, which they lack.

**If a check is wrong, not her,** fix the check and say which. For example, the judge may grade the fixed emergency line itself as cold, when that line is meant to be plain.

**Rules:**
- **The safety sections of `mary/instructions.md` stay word for word.** The fixes go in `CHARACTER_NOTE`, Live's own text or the non-safety sections. If you think a safety section itself must change, quote your wording in a `WAITING:` report for Andy, and don't change it.
- **Keep it short.** `CHARACTER_NOTE` closes every prompt in Normal and Live, so every word costs. Say what each prompt grew by.
- **No Gemini calls.** You can't use Andy's key. Use fakes and `--replay` only. The hub runs the real bench after merging.
- Touch only:
  - `mary.py`;
  - the non-safety parts of `mary/instructions.md`;
  - the wording in `skills/messages/skill.py`;
  - `bench/variants/` and `bench/cases/`;
  - the tests.
  Leave `bench/results/` alone. No other worker is running.
- **Memory is tight** on this laptop. If a test run is stopped for memory, wait a few minutes and retry once.

**Models:**
- Opus `coder` for the wording in pieces 1-5. Every word lands on residents, so it needs judgment.
- Sonnet `coder` for the tests and bench cases.

**Finish:** commit `DONE: M4g brain fixes ready for the bench`. The message carries:
- every changed line, old and new, word for word;
- how much each prompt grew;
- three plain lines for Andy;
- the bench commands the hub should run, with request counts. Use `--only`/`--companion` so they fit one day's limit: the failing cases in Normal, plus `--real-live` for the safety ones.

Then stop.
