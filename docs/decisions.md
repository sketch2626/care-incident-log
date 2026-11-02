# Standing decisions (read before any brief or any change)

Andy made these. A change that would break one stops and asks him (`WAITING:` on her account, or the hub's question here). Each has a **guard**: a test that fails if it's broken. A decision without a guard is marked, and the next job that touches it builds one. Started 2026-11-02 (M21), because rounds kept quietly undoing earlier decisions.

## Mary's voice and brain
- **D1. No built-in speech.** Every word she says is the model answering what the resident said. There's no canned hello, goodnight, "I'm here" or wake greeting. When she wakes, she shows she's listening and waits. Emergency steps (call light, 911, 988 press 1) show in big letters on screen, and she says them in her own words. When no model can be reached, the screen says so and she says nothing. Andy, 2026-11-02: "no canned responses, period. There should be no built-in speech at all. It should always be a response to your input." **Guard:** none yet (M21a builds it).
- **D2. Her instructions are mostly safety, and less is more.** They hold the safety sections, who she is, what the app can really do, privacy, and the few places where Andy's choices go against the model's habits (guns, hunting, faith, prayer and politics are welcome; never moralize). A line comes back only when a whole-talk test shows it's needed. Andy, 2026-11-02: "the model is going to do a better job on its own than… with us cramming a million instructions down its throat." **Guard:** none yet. M21a caps her prompt at today's size, and M21c lowers the cap when the lean brain lands.
- **D3. A fix removes before it adds.** Net growth of her prompt is zero unless Andy approves. Reword or delete first. (2026-11-02, after the lean variant doubled from 5,551 to 11,440 characters.) **Guard:** the D2 cap.
- **D4. Brain changes are judged on whole talks on the real model, less against more, and Andy's read decides.** Not single replies, and not the stand-in alone. (First planned 2026-10-30 in M9d; restated 2026-11-02.) **Guard:** none yet (M21b, the whole-talk bench).
- **D5. The safety sections of `mary/instructions.md` stay word for word** unless Andy approves the new wording. **Guard:** the M4e/M9f tests pin them.
- **D6. Southern words:** everyday ones like "y'all" are fine from the start. Uncommon ones like "howdy" come only after the resident uses them. (2026-11-01.) **Guard:** bench cases.
- **D7. Grown-up talk:** no pet names, no praise for the ordinary, no talking down. "Ma'am" and "sir" are respect. (Standing; M4i.) **Guard:** the bench's grown-adult rubric.

## Saving, sending and secrets
- **D8. Mary never saves or sends by herself.** Only a tap or the resident's own plain "save it" or "send it" does. (M15c, M18.) **Guard:** the send-gate and save-gate tests.
- **D9. Secrets stay out of her hands.** She never reads or fills the Gemini key, the email app password or the six words. None of them ever goes in settings, the database, backups, logs, the page or Gemini. **Guard:** the screens.js secret wall and its tests.
- **D10. The address book is the one place an address is kept.** No addresses in memories, talk history, logs or reports. "Forget everything" leaves the book. (M19.) **Guard:** the M19 proofs.
- **D11. A state report is in the resident's own words and judgment.** "Your words" and "How bad was it?" stay theirs; she explains them and copies in what she heard. (M18 boards; M22 asks whether the switches open to her.) **Guard:** the screens.js field kinds.

## Screens
- **D12. If you can just ask Mary, it needs no button.** Every voice path that replaces a button must work, because nothing is behind it. (Andy, 2026-11-01; M22 is the lesson.) **Guard:** none yet.
- **D13. Every screen reached from Mary has a big "Back to Mary" always in view, and going deeper never ends a talk.** (M17, M18.) **Guard:** M17/M18 tests.

## How work is run
- **D14. Her account: an Opus worker plans and checks; Sonnet `coder` writes the code;** no Opus `coder` unless a brief names one hard piece; never `xhigh`. (Andy, 2026-11-01, after the usage audit.)
- **D15. Scratch data only** for workers. No browser or screenshots. Never the real log, his key or Andy Flow's history.
- **D16. Private facts stay out of the public repo** (`private/` is gitignored).
- **D17. GitHub `main` stays current.** The project is **Mary's Porch** (github.com/sketch2626/marys-porch, renamed 2026-11-02). After each merge that passes the tests, the hub pushes `main` to GitHub and backs up to `dev`. Workers still never push. (Andy, 2026-11-02: "Yes, publish". Before this, `main` sat at Oct 24 while all the work went to `dev`.)
