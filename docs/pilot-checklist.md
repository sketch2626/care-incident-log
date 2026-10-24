# Pilot checklist: 5 residents, one NC facility

> Needs revising for the companion-first direction (2026-10-24). See [companion-plan.md](companion-plan.md).

**Goal:** 5 residents use the app daily for 8 weeks. They log incidents, do daily mood check-ins, and send complaints with their name or anonymously. Nothing breaks, nobody is exposed, and every send arrives.

**Not in the pilot:**
- Research data. That needs a university partner and IRB approval first. If we want pilot data to count for research later, bring the university in before the pilot starts.
- Accounts and the public facility dashboard. Everything stays on the laptops except what residents send.

**Honest limit:** with 5 users in one building, "anonymous" hides a sender among a small group. If the facility knows who has the app, it can guess. So keep the participant list private, tell residents this plainly, and line up the ombudsman partner before the first send.

Backend design: [backend-plan.md](backend-plan.md).

## 1. Finish the app
- [ ] Review, test and commit the unfinished report-to-state edits.
- [ ] Fill `RETALIATION_REGS` from [retaliation.md](retaliation.md).
- [ ] Encrypt the local log, and add a Windows Hello or PIN lock.
- [ ] Add the daily mood check-in. It stays on the laptop; the resident picks the time and can skip it.
- [ ] Build the one-click send screen. It asks "Put your name on this?", removes names and rooms automatically, shows a preview and confirms "Delivered".
- [ ] Add facility-first emails. For serious complaints, the app drafts a formal email to the director of nursing and the administrator and recommends sending it first. If there's no reply by the date, it suggests the ombudsman, then the state. See "Facility first" in [backend-plan.md](backend-plan.md).
- [ ] Rebuild the installer, with `build.py` downloading the voice model.
- [ ] Code-sign the installer so Windows doesn't show a warning. Compare low-cost signing options.
- [ ] Test on a clean laptop like the residents': install, voice, send, uninstall, and check that a reinstall keeps the data.

## 2. Build the sending relay (the only server piece)
- [ ] Get a project domain and email address, and set up SPF, DKIM and DMARC.
- [ ] Choose hosting that signs a BAA, and an email service with delivery tracking.
- [ ] Add a fax or tracked-mail service for recipients without email.
- [ ] Set up helper enrollment with one-time codes, plus anonymous tokens. The relay can then tell that a send came from an enrolled resident, but not which one.
- [ ] Keep no IP logs, and nothing after delivery except the receipt code. Write down the retention rule.
- [ ] Add a daily send cap per laptop.
- [ ] Handle failures: the relay retries, then the app offers to print the complaint or call.
- [ ] Write an incident response plan and add `SECURITY.md`.
- [ ] Get an independent security review of the relay and fix what it finds. A university security lab, a volunteer or a paid firm could do it.
- [ ] Test-send to every real recipient, arranged with them ahead of time.

## 3. Check the facts
- [ ] Find out which recipients take email, fax or mail.
- [ ] Get the email addresses of the director of nursing, the administrator and the grievance official.
- [ ] Find out whether NC DHSR accepts anonymous complaints, and by which route.
- [ ] Re-check the ombudsman roster date in `contacts/NC.json`.
- [ ] Confirm the wording of the ombudsman confidentiality rule (45 CFR 1324) to show residents.

## 4. Legal and paperwork
- [ ] Get a lawyer's review. Try a law school clinic or legal aid for pro bono help. Topics:
  - privacy
  - the FTC Health Breach Notification Rule
  - NC breach law
  - liability for the relay
  - roommates' voices in recordings
  - residents with guardians
- [ ] Write a plain-language privacy policy and terms.
- [ ] Write the pilot agreement, in large print and read aloud.
- [ ] Draft the spoken-words consent now, for later research (not used in the pilot).
- [ ] Write a confidentiality agreement for helpers.
- [ ] Draft the starting and end surveys. The starting one is needed by setup day, so the change can be measured after 8 weeks.

## 5. People
- [ ] Brief the ombudsman partner on how anonymous complaints arrive, their part in account recovery, and that they're the first call if retaliation happens.
- [ ] Write the lost-laptop and recovery process with the helpers and the ombudsman. The helper revokes the old laptop and enrolls the new one. Also decide where encrypted backups of the log live.
- [ ] Recruit 5 willing residents who can consent for themselves. A resident with a legal guardian needs the guardian's agreement.
- [ ] Laptops: in NC, Medicaid provides refurbished laptops ($65 fee, waived if the resident can't pay). Help each resident apply. Each laptop needs Windows 11 (Pro for the locked-down kiosk), a working mic and Wi-Fi access.
- [ ] Train 1 or 2 helpers on installing, teaching and privacy, and clear them with the facility's visitor rules.
- [ ] Set up support: who residents call for help, and how fast they get an answer.
- [ ] Decide whether and when to tell the facility about the pilot.

## 6. Setup day (each resident)
- [ ] Install the app, set up the PIN or Windows Hello, and set the mood check-in time.
- [ ] Enter the facility's contacts on the My Info screen.
- [ ] Do the starting survey.
- [ ] Practice logging an incident by voice.
- [ ] Practice sending a complaint to a test inbox, and see "Delivered".
- [ ] Explain the limits of anonymity, and their retaliation rights on the rights screen.
- [ ] Sign the pilot agreement.

## 7. During the pilot
- [ ] Check in weekly for the first month, then every 2 weeks.
- [ ] Track entries, check-ins, sends delivered or failed, help requests and problems.
- [ ] If there's any sign of retaliation, contact the ombudsman partner the same day.
- [ ] Fix bugs, and have helpers install the updates.

## 8. Wrap-up
- [ ] Do the end survey and compare it with the starting survey.
- [ ] Residents keep their logs and the app.
- [ ] The relay deletes data as the retention rule says.
- [ ] Write a short report for funders and the next facility: what worked, what broke, and what residents said (with their consent).
