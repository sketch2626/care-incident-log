# Pilot checklist: 5 residents, one NC facility

> Revised 2026-11-04 for the companion (Mary and Sam), with what the old companion plan held about the laptop, rollout, costs and the pitch (that plan is now `docs/archive/companion-plan.md`). The rules it names are in `docs/decisions.md`, and the M items in `docs/mary-roadmap.md`.

**Goal:** 5 residents use Mary daily for 8 weeks. They talk with her as a friend, log incidents, do daily mood check-ins, and send complaints with their name or anonymously. Nothing breaks, nobody is exposed, and every send arrives.

**Not in the pilot:**
- Research data. That needs a university partner and IRB approval first. If we want pilot data to count for research later, bring the university in before the pilot starts.
- Accounts and the public facility dashboard. Everything stays on the laptops except what residents send.

**Honest limit:** with 5 users in one building, "anonymous" hides a sender among a small group. If the facility knows who has the app, it can guess. So keep the participant list private, tell residents this plainly, and line up the ombudsman partner before the first send.

Backend design: [backend-plan.md](backend-plan.md).

## 1. Finish the app
- [ ] Speak-up S1 and S2 (`docs/speakup-plan.md`, M27), including `RETALIATION_REGS` from [retaliation.md](retaliation.md). Review and test the parked `wip/report-to-state` work, and merge what's still wanted.
- [ ] Encrypt the local log, and add a Windows Hello or PIN lock.
- [ ] Add the daily mood check-in. It stays on the laptop; the resident picks the time and can skip it.
- [ ] Build the one-click send screen. It asks "Put your name on this?", removes names and rooms automatically, shows a preview and confirms "Delivered".
- [ ] Add facility-first emails. For serious complaints, the app drafts a formal email to the director of nursing and the administrator and recommends sending it first. If there's no reply by the date, it suggests the ombudsman, then the state. See "Facility first" in [backend-plan.md](backend-plan.md).
- [x] Rebuild the installer, with `build.py` downloading the models (v0.5.0, 2026-11-02). Rebuild it after each big merge.
- [ ] Code-sign the installer so Windows doesn't show a warning. Compare low-cost signing options.
- [ ] Every resident's key on a paid tier (D21), with a setup check that tells the helper whether a key is still on the free tier.
- [ ] Her brain picked and built in (D19, M26), and its full testing on the real model, safety first (D26).
- [ ] `wake.log` keeps only a word count (D24).
- [ ] Real weather, with the town set at setup (M24).
- [ ] Lid to Mary, the two setup modes and the one-click setup tool (M28).
- [ ] The speed check and the voice on a refurbished-class laptop (M8).
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
- [ ] Laptops: in NC, the Medicaid program gives residents laptops. Many are new donated Lenovos like Andy's (Ryzen 5 7520U), and some are refurbished, for a $65 fee waived if the resident can't pay. Other states: check. The laptop spec with a price is M28. Help each resident apply. Each laptop needs Windows 11 (Pro for the locked-down kiosk), a working mic and Wi-Fi access.
- [ ] Train 1 or 2 helpers on installing, teaching and privacy, and clear them with the facility's visitor rules.
- [ ] Set up support: who residents call for help, and how fast they get an answer.
- [ ] Decide whether and when to tell the facility about the pilot.

## 6. Setup day (each resident)
- [ ] Install the app and set the mood check-in time.
- [ ] Check that their key is on a paid tier (D21), and set the town for the weather (M24).
- [ ] If they want email, connect their Gmail or Yahoo account (M15), and sign the browser in to Facebook for Messenger.
- [ ] Put a Windows PIN on the laptop (Andy, 2026-11-01). The address book's lock only helps once the laptop is locked: on a laptop with no Windows password, anyone who picks it up can sign in and open the book. Without a PIN, the line "Kept only on this laptop, locked." isn't true.
- [ ] Once their people are in the address book, make a helper's copy (My info). Keep the file on a stick and the six words on paper with family.
- [ ] Enter the facility's contacts on the My Info screen.
- [ ] Do the starting survey.
- [ ] Practice logging an incident by voice.
- [ ] Practice sending a complaint to a test inbox, and see "Delivered".
- [ ] Explain the limits of anonymity, and their retaliation rights on the rights screen.
- [ ] Sign the pilot agreement.

## 7. The companion side (from the old companion plan, 2026-10-24)
- **The pilot:** resident-only, 5 residents, 8 weeks. Measure loneliness before and after with a short, validated scale, alongside the incident data.
- **After the pilot:** pitch facilities as partners, starting with activities departments. We can promise facility first by default, systems not people, and red lines defined with the ombudsman partner. We must never promise that residents won't go to the state.
- **The pitch:** the same honest product for everyone, and we never deny what she does. Loneliness and aging funders hear companionship; advocacy and justice funders hear that residents can finally document care failures and be heard; facilities hear a partner.
- **Funding lead:** CMS Civil Money Penalty reinvestment funds, money from fines on nursing homes that states hand out for projects that help residents. Check NC's process.
- **Rough monthly cost per resident** (2026-10-24 estimates; check current prices): the conversation on Gemini Flash, for someone chatting about 2 hours a day, roughly $2 to $8; the voice $0 on the laptop, and a cloud voice maybe $10 to $20 for a heavy talker. The Claude API estimates are in M26. The pitch: companionship and a voice for under about $10 a month per resident.
- **Plain words for consent:** what they say to Mary is sent to the brain's company to work out her answer. On the paid service it isn't used to train or improve its products; Google keeps it up to 55 days for abuse checks. This goes into the consent screen and the privacy policy. Also check Gemini through Google Cloud (Vertex AI) under a BAA, for medical-grade handling.
- **Open questions:**
  - Whose AI account: one project account through our server (we pay from grants, and it's simpler), or each resident's own (they pay, and it's more private)?
  - The red lines: define them with the ombudsman partner.
  - How family consent works for residents with dementia.

## 8. During the pilot
- [ ] Check in weekly for the first month, then every 2 weeks.
- [ ] Track entries, check-ins, sends delivered or failed, help requests and problems.
- [ ] If there's any sign of retaliation, contact the ombudsman partner the same day.
- [ ] Fix bugs, and have helpers install the updates.

## 9. Wrap-up
- [ ] Do the end survey and compare it with the starting survey.
- [ ] Residents keep their logs and the app.
- [ ] The relay deletes data as the retention rule says.
- [ ] Write a short report for funders and the next facility: what worked, what broke, and what residents said (with their consent).
