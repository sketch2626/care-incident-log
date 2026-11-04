# Mary's Porch

**An open-source AI companion for nursing-home residents, built by one.**

Mary (and Sam, if you'd rather talk to a man) is a friend who lives on the resident's own Windows laptop. Friendship comes first: talk, stories, games, cards to the family. When something goes wrong with their care, she helps them speak up. The resident talks naturally, and the app turns it into a formal, dated record for the long-term care ombudsman and state inspectors.

**Status: beta, v0.5.0. Not ready for residents yet.** Her conversation is being rebuilt, because testing found her talking down to people. See [Status](#status).

## Who made this, and why

Mary's Porch is built mostly by voice, with AI and no computer-science degree, by a paralyzed nursing-home resident in North Carolina. He lives with poor care every day and watches his neighbors get the same.

A tool like this never existed, because nobody had the will or the money. AI now makes it possible for pennies, built by the person it affects. **This is what AI is for.**

It's a companion first on purpose. A pure reporting tool scares residents and makes facilities fight it. A friend helps from day one, and when the day comes that they need to speak up, she's already there. It's built as if the state will read it, because it will. The spirit of the project is in [docs/mission.md](docs/mission.md).

## What she does today

- **Talking, three ways.** Live is the default: she hears you and answers in a flowing voice, like a phone call. Normal is turn by turn: the laptop turns your voice into words, then she replies. Offline uses a voice made on the laptop, so it sounds plainer. If one way isn't available, the screen falls back to the next. Privacy for each is [below](#privacy-and-safety-in-plain-words).
- **Hands-free.** Say "Hey Mary" or "Hey Sam" and she wakes up. It works by voice or one big tap, with large text. Her face and captions are on screen (`web/mary/`).
- **Mary and Sam.** Two companions, each with a written personality in [docs/characters/](docs/characters/). The resident picks one, and picks a voice from six Gemini voices or six offline Kokoro voices.
- **Memory.** She remembers what the resident tells her, with dates, and keeps it in a file on the laptop. She reminds them about family birthdays. "Forget that" erases it.
- **Speak-up log.** The resident says what happened. The app sorts it into a category, how long they waited, whether anyone came, and how serious it was. It does this offline with a simple guesser, or with Gemini if the resident turned it on.
- **Reports.** `/report` is a printable record with an attestation and signature lines. There is also an Excel export. Entries carry CMS F-tag citations (checked against Appendix PP), for information only.
- **Skills.** Four so far, in `skills/`:
  - `messages`: greeting cards and short notes in the resident's own words, to print if the laptop has a printer, or to send by email.
  - `pictures`: shows a Wikipedia picture of what they ask about, so she can talk about it.
  - `word_search`: a big-print word search, by voice or touch.
  - `voice_comfort`: slower, faster, quieter or louder, Mary or Sam, and wake word on or off.
- **Email.** From the resident's own Gmail or Yahoo account, with an app password. A helper sets it up once. Nothing goes out without their plain "send it" or a tap, then five seconds to undo.
- **Address book.** People are added by voice in a Live talk, and she finds them by name when asked. A helper can make a copy locked with six words, which moves the book to a new laptop.

### Beta, or not built yet

- **Opening and filling screens by voice works only in Live** ([M18b](docs/mary-roadmap.md)). Normal and Offline can't do it yet.
- **Email has only been tested against a fake server.** A real Gmail or Yahoo send with a helper is still to do.
- **Facebook Messenger is planned, not built** ([docs/messaging-plan.md](docs/messaging-plan.md)). There is no Messenger code in `skills/messages`.
- **Speak-up steps are planned, not built** ([docs/speakup-plan.md](docs/speakup-plan.md)). Mary can offer to write a problem down, and the resident can make a report. She doesn't yet walk them through the facility, the ombudsman and the state.
- **The secure backend and anonymous sending are a plan only** ([docs/backend-plan.md](docs/backend-plan.md)).
- **The app sends no complaints by itself.** The resident decides who gets a report.

## Status

- **Beta, v0.5.0.** The builder is user #1 and tries every change himself. No other resident uses it yet; the first pilot is planned for one North Carolina facility.
- **Her conversation is being rebuilt** ([roadmap M26](docs/mary-roadmap.md)). Testing v0.5.0 found her talking down to people, repeating herself and saying canned lines. Scoring well on single scripted replies hid it. Built-in speech is gone and shorter brains are built; the rebuild finishes on a paid model (Gemini's paid tier or the Claude API), judged on whole conversations.
- **A new look is being made** ([roadmap M24](docs/mary-roadmap.md)): Mary and Sam as two 1950s robots on a porch swing, with the day's weather behind them.
- **Windows only.** The installer isn't code-signed yet.

## Privacy and safety, in plain words

**Local first.** The incident log, her memories and the address book live on the resident's laptop, in their Windows profile. There are no accounts, no server of ours, and no tracking.

**The brain is Google's Gemini, with the resident's own key.** That's the one thing to understand before using Mary: to answer, she has to send your words to Google. Each reply sends a packet: what you just said, the recent talk, a short note of what she remembers about you, and her instructions.

What leaves the laptop depends on the talk mode:

| Talk mode | Your voice | Your words | Her voice |
|---|---|---|---|
| **Live** (the default) | Goes to Google as sound | Go to Google | Made by Google |
| **Normal** | Turned into words on the laptop | Go to Google | Made by Google, from the words of her reply |
| **Offline** | Turned into words on the laptop | Go to Google | Made on the laptop |

Offline means her *speech* is on the laptop. Her thinking is still Gemini. With no key or no internet she can't hold a conversation; the incident log, the reports and the speech-to-text keep working without either.

**Use a paid Gemini key for anyone's real conversations.** On Gemini's free tier, Google's pricing page lists content as used to improve its products. On the paid tier it isn't. The free tier is for the builder's own testing, and any other resident must be on a paid plan.

**Everything else that can leave the laptop:**
- **Listening for "Hey Mary"** happens on the laptop. Nothing is sent until she's awake.
- **Pictures:** when asked, she looks up the picture on Wikipedia, and Gemini is shown it so she knows what it really shows.
- **Email** goes from the resident's own Gmail or Yahoo account, and only after their own plain "send it" or a tap, with five seconds to stop it. She never sends or saves on her own.
- **State reports** are made on the laptop. The app prints or exports them, and the resident decides who gets one.

**Secrets.** The Gemini key and the email app password are kept in Windows Credential Manager, never in the app's files, its backups or the page. She can't read them or type them.

**The address book is locked.** Each person is sealed with AES-256-GCM, names included, with the key in Credential Manager. Gemini works from names and gets a phone number or address only when the resident's own words ask for it. If the key is missing, the book stays locked; there's no plain copy to fall back on.

**What isn't encrypted.** The incident log and her memories are ordinary database files. Anyone who can open the resident's Windows account can read them, so that account needs a PIN.

**The resident is in charge.** "Forget that" really erases a memory. A removed incident is hidden but kept, because a record of care shouldn't quietly disappear.

**How the safety rules are kept.** The builder's standing decisions are written down in [docs/decisions.md](docs/decisions.md), most with a test that fails if one is broken. The safety sections of her instructions stay word for word unless he approves new wording, and tests pin them. An emergency check runs before any tool or skill, and points to the call light, staff, 911 and 988, with the Veterans Crisis Line for veterans.

**What Mary isn't.** On screen she's a robot, and she never pretends to be a person; asked straight out, she says she's what folks call AI. She isn't a nurse, a doctor or an emergency service, and this app isn't legal advice. The regulation references are for information only; the state survey agency decides what rules were broken. In an emergency, press the call light or call 911.

## Install

**You need:** a Windows laptop with a microphone (tested on Windows 11). The app opens in its own window (WebView2), or in the default browser if WebView2 is missing. For her to hold a conversation, you need a Gemini key, added under My info. The incident log and reports work without one.

**Installer.** `CareIncidentLog-Setup-<version>.exe` installs for one user, with no admin rights. It is about 335 MB, and about 660 MB once installed. There is also a portable zip. Installers will be posted on the [GitHub Releases page](https://github.com/sketch2626/marys-porch/releases). Until a release for the current version is there, build it yourself (below).

**Old name.** The app still installs under its old name. The Start menu and desktop get two shortcuts: "Mary" and "Care Incident Log".

**SmartScreen.** The installer isn't code-signed yet, so Windows shows a warning. Choose "More info", then "Run anyway".

**Build it:**
1. Install Python 3.12. For the installer, also install Inno Setup 6. The zip builds without it.
2. Double-click `packaging\build.bat`.
3. If `models/` is missing, it downloads the three models (speech-to-text, Kokoro voice, wake word) and checks each with SHA-256.
4. The installer and zip land in `dist\`.

## For developers

Much of the code was written by Claude models under the builder's direction.

| Path | What it is |
|---|---|
| `server.py` | Stdlib-only local server and API; the incident log (SQLite) |
| `desktop.py` | The app window (pywebview); `--mary` opens her window, maximized |
| `mary.py` | Her brain: what she knows, when to get help, the Gemini talk loop |
| `mary/instructions.md` | Her instructions |
| `voices.py` | Voice choices and samples |
| `speech.py` | On-device speech-to-text |
| `wakeword.py` | Offline "Hey Mary" / "Hey Sam" |
| `assist.py` | Optional Gemini helper that tidies a spoken report |
| `memory_core.py`, `memory_dates.py` | Her long memory; birthdays and dates |
| `address_book.py` | The sealed address book |
| `secret_store.py` | Keys and passwords in Windows Credential Manager |
| `mail_core.py`, `send_gate.py` | Email, and the yes and Undo that guard every send |
| `reports.py` | The printable report and Excel export |
| `skills_core.py`, `skills/` | The skills loader, and the skills |
| `web/` | Vanilla HTML, CSS and JS screens |
| `tests/` | The test suite |
| `tools/`, `bench/` | Model downloaders and checks; the brain bench |
| `packaging/` | Installer and build scripts |
| `docs/`, `mockups/`, `contacts/` | Plans and decisions; design mock-ups; NC contact data |

**Run it.** `python server.py` serves http://localhost:8765. `Start Mary.bat` opens her window. Or run `python desktop.py --mary`. The server itself is standard-library Python. Her window, voices, speech and the address book use the packages pinned in `packaging/requirements.txt`.

**Data** lives in `%APPDATA%\CareIncidentLog`. Set the env var `TRACKER_DATA` to use another folder.

**Tests.** `python run_tests.py -q` runs over 2,300 tests on scratch data (see `tests/helpers.py`). Page scripts are checked with `node --check`.

**Skills.** New abilities are skills. Start with [docs/how-to-make-a-skill.md](docs/how-to-make-a-skill.md), [docs/skills-design.md](docs/skills-design.md) and the example in `skills/voice_comfort/`. A skill reaches the internet only through `ctx.fetch`, and only to the hosts on its card. It must pass `tests/test_skills_contract.py`.

**Brain bench.** Runs scripted resident lines against her real brain and grades the replies. See [bench/README.md](bench/README.md).

**Folder guides:** [docs/](docs/README.md), [tools/](tools/README.md), [skills/](skills/README.md), [mockups/](mockups/README.md) and [bench/](bench/README.md).

## Roadmap

Everything here is a plan unless it says done.

- **Next: Mary on her porch** ([M24](docs/mary-roadmap.md)). Two 1950s robots on a porch swing, with the real weather behind them.
- **Her brain on a paid model** ([M26](docs/mary-roadmap.md)), judged on whole conversations, with full testing, safety first.
- **Opening and filling screens by voice in Normal and Offline** ([M18b](docs/mary-roadmap.md)), not only Live.
- **A pilot at one North Carolina facility, with five residents.** The checklist is [docs/pilot-checklist.md](docs/pilot-checklist.md).
- **More to do together.** More games as skills, and a more natural voice ([roadmap](docs/mary-roadmap.md)).
- **Speak-up steps.** Help the resident work through the facility, the ombudsman and the state ([docs/speakup-plan.md](docs/speakup-plan.md)).
- **Messenger.** Mary writes the message and opens the chat, and the resident taps Send ([docs/messaging-plan.md](docs/messaging-plan.md)).
- **A code-signed installer**, so Windows stops warning.
- **A secure backend:** passkey sign-in, named or anonymous sending, and de-identified research data with consent ([docs/backend-plan.md](docs/backend-plan.md)).

## Contributing

Issues and pull requests are welcome at https://github.com/sketch2626/marys-porch.

- Read [docs/mission.md](docs/mission.md) and [docs/decisions.md](docs/decisions.md) first. A change that breaks a standing decision needs the builder's OK.
- Everything must work by voice or one big tap. Text is 20px or larger, and touch targets are 64px or larger.
- Tests must pass: `python run_tests.py -q`.
- Real resident data never goes in tests or issues.
- New abilities are skills.

## License

[GPL-3.0](LICENSE). Free to use, share and improve, so other facilities and states can use it. If you distribute a changed version, you must share its source code too.
