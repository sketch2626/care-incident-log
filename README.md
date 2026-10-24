# Care Incident Log

**A private, voice-first app that helps nursing-home residents write down care failures and report them to the state.**

Call lights that go unanswered. Meals that never come. Baths that get skipped. These things happen every day in nursing homes, and almost none of them get written down. Care Incident Log gives residents an easy way to record what happened, in their own words, as it happens, and turns those notes into the kind of formal, dated record that state inspectors take seriously.

It was built by a nursing-home resident, for nursing-home residents.

## What it does

- **Just talk.** Tap one big button and say what happened. Speech-to-text runs **on the laptop itself**: no internet, no account, no cost.
- **Sorts it for you.** The app works out the kind of problem (call light, meal, bathing, toileting, medication, repositioning, staff conduct, falls), how long the resident waited, whether anyone came, and how serious it was.
- **Built for older eyes and hands.** Large text, large buttons, plain words, and a microphone on every question, including the ones that matter most for proof: *which staff member* and *who you told*.
- **Formal reports for the state.** It produces a printable signed statement and an Excel workbook. Each entry has a record number, the resident's own words, a neutral summary, the time it was written down, and the federal rules it likely breaks (CMS F-tags from 42 CFR Part 483, checked against CMS's crosswalk and State Operations Manual Appendix PP).
- **Optional AI helper.** Residents can turn on Google Gemini with their own free key, to tidy their words and write the formal summary. It is off by default, so nothing leaves the computer unless they choose.

Coming next: an alert that says when it is time to report, help drafting the complaint to the State Survey Agency and the Long-Term Care Ombudsman (with safeguards so reports stay well-documented and fair), retaliation warnings, and an always-on floating microphone button.

## Privacy

Everything stays on the resident's own computer, in `%APPDATA%\CareIncidentLog\`, with daily backups. There are no accounts, no cloud and no tracking. Removing an entry hides it but never destroys it, because a record of care should not quietly disappear.

## Install (Windows)

Download `CareIncidentLog-Setup-<version>.exe` from the Releases page and run it. No administrator rights are needed. The installer is not code-signed yet, so Windows SmartScreen will warn you: choose **More info → Run anyway**.

## Build from source

Requires Python 3.12 on Windows.

```bash
python server.py
```

This runs the app in your browser at http://localhost:8765. The first time you use the microphone, the speech model must be in `models\faster-whisper-base.en` (the installer build downloads it).

To build the installer, double-click `packaging\build.bat`. This needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer; a portable zip is built without it.

## Important

This app helps residents keep accurate records and contact the right agencies. It is **not legal advice**, and the regulation references are for information only: the state survey agency decides what rules were broken. In an emergency, residents should press their call light or call 911.

## License

[GPL-3.0](LICENSE). Free to use, share and improve. If you distribute a changed version, you must share its source code too.
