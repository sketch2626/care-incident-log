# Backend plan: secure accounts, sending and research data

Status: plan only, nothing built. Written 2026-10-24. Today the app keeps everything on the resident's laptop. Later on 2026-10-24 the direction changed to companion first (see [companion-plan.md](companion-plan.md)). This plan still applies, but conversations with the companion now go to Gemini, and mood check-ins can come from conversation.

## Goal
Build the online side of Care Incident Log to the standard of medical software. Residents can sign in, send complaints with their name or anonymously, and record how they feel. If they choose, they can also share de-identified data that universities can study. Security comes first at every layer: the laptop, the network, the server and the research data.

## Ground rules
1. **Local first.** The full log stays on the resident's laptop. Each kind of sharing has its own switch, and every switch starts off.
2. **Opt-in, per purpose, revocable.** Sending, mood sharing and research are separate choices. Withdrawing stops future sharing and deletes anything we still hold that can be tied to the resident.
3. **Separate who from what.** Identity (name, email, account) lives in a different system, database and key from incident and mood data. No single person or breach gets both.
4. **Collect the minimum.** If a feature works without a field, we don't collect it.
5. **Honest promises.** We never say "100% anonymous". We tell residents what anonymity covers and what can still give them away.
6. **Open and audited.** All code is public (GPL-3.0). An independent security review happens before any real resident data reaches a server.

## Threat model
| Threat | Example | Main defenses |
|---|---|---|
| The facility | Staff pick up a resident's laptop, or try to learn who complained | Encrypted local log and app lock; anonymous sending; a facility is shown only with 5+ residents; no names in shared data |
| Lost or shared laptop | Stolen, or a visitor uses it | Encrypted log, Windows Hello lock, remote sign-out |
| Account takeover | Phished password | Passkeys, so there is no password to steal |
| Server breach | Attacker reaches the database | Encryption at rest, identity split from data, field-level encryption for names and emails |
| Insider | A helper or admin snooping | Least privilege, two-person approval for raw data, append-only audit log |
| Legal demand | Subpoena for who said what | Hold as little as possible; anonymous sends keep no sender record; Certificate of Confidentiality for research data (to verify) |
| Re-identification | A researcher spots "the only resident on hall B" | 5+ rule, coarse dates, free text left out by default, data use agreements |
| Abuse | Fake or spam complaints | Only enrolled residents can send; rate limits; signed submissions |

## Data tiers
| Tier | What | Leaves the laptop? | Name attached? |
|---|---|---|---|
| 0. Local log | Everything the resident records | No | Resident's own copy |
| 1. Counts | Incidents per category per week, per facility | Opt-in | No |
| 2. Mood check-ins | Feeling scale and tags | Opt-in | No |
| 3. Research set | De-identified incidents and moods for approved studies | Separate opt-in with informed consent | No, random study ID |
| 4. Named sending | Complaints the resident signs | Only when they send | Yes, their choice |

## Sign-in and accounts
- **No passwords.** Residents aged 65 to 95 shouldn't have to manage them, and stolen or phished passwords are a leading cause of break-ins. Sign-in uses passkeys tied to the laptop: Windows Hello face, fingerprint or PIN.
- **Most sharing needs no account.** Tiers 1 to 3 use anonymous tokens (Privacy Pass style). The server can check that a submission came from an enrolled resident, but not which one. An account with an email is needed only for named sending, receipts and moving to a new laptop.
- **Enrolling a laptop:** a helper enrolls each laptop at setup with a one-time code. That's what lets the laptop get anonymous tokens. The pilot needs nothing more than this.
- **Recovery** goes through a set-up helper or a trusted contact the resident names, with an identity check. Facility staff never handle it.
- **Admins and helpers** must use hardware security keys and short sessions, and every action they take is logged.
- **Remote sign-out** removes a lost laptop from the account.

## Sending complaints: named or anonymous
Every send screen asks one question: "Put your name on this?"
- **Named:** the complaint goes from the resident's own email, or through our relay with their name in the letter. A copy stays in their log.
- **Anonymous, one click:** the app removes names and room numbers it finds and shows a preview with a single Send button. Above the button, a plain-words note says: "Details like your room number, your condition or the exact time can still point to you." Our relay sends it from a project address. After delivery, the server keeps only a receipt code that the resident holds, and the relay doesn't log IP addresses.
- **Confirmed delivery:** the resident sees "Delivered" with the time.
  - Email goes from an authenticated project domain (SPF, DKIM, DMARC) through a mail service with delivery tracking, so it doesn't land in spam.
  - Recipients without email get it by fax or tracked mail, whichever they accept. NC DHSR confirms phone, mail and fax. Its pages also list DHSR.ComplaintIntake@dhhs.nc.gov, but whether it takes complaints by email is unconfirmed (decision D1 in `docs/speakup-plan.md`).
  - If a send fails, the relay retries. The app tells the resident plainly and offers to print the complaint or show the phone number.
- Hidden metadata is stripped from attachments, such as photo location and document author.
- **Later:** anonymous replies. The recipient answers the relay address, and the reply shows up in the resident's app without revealing who they are.
- **Tell residents:** the long-term care ombudsman can't reveal a resident's or complainant's identity without consent or a court order (45 CFR 1324.11(e)(3), verified 2026-10-30). NC DHSR must keep a complainant's identity confidential (NCGS 131E-124(c)). **Still to verify:** whether NC DHSR accepts complaints with no name at all (D1).
- **Abuse limits:** only enrolled residents can send, there's a daily cap, and there's no bulk sending.

### Facility first (recommended, never required)
Most problems get fixed fastest when the facility itself is on board. So when a complaint is serious enough (by the app's urgency levels), the app drafts an email to the director of nursing and the administrator, and recommends sending that first.
- **Contacts:** the resident or a helper enters the director of nursing's, administrator's and grievance official's email addresses once, on the My Info screen.
- **The draft** is formal and dated, cites the incident record numbers, and asks for a reply by a set date. It is a grievance, and the facility must have a grievance process (F585). It goes with the resident's name so the facility can follow up.
- **Next steps:** if there's no reply or no fix by the date, the app suggests the ombudsman, then the state (DHSR). Each letter cites the earlier ones.
- **Never a gate:** residents can always go straight to the ombudsman or the state, and the app says so. Abuse, injury or immediate danger skip the ladder: the app recommends the state and ombudsman right away, alongside the facility.
- **Retaliation:** a named email tells the facility who complained. The app shows the resident's retaliation rights before sending, and flags any later incident that looks like payback.

## Mood check-ins
- A daily prompt asks "How are you feeling?" The resident picks the time and can skip it or turn it off. The prompt offers 5 faces and optional tags such as lonely, in pain, ignored, scared, respected or okay. Residents can answer by voice.
- Check-ins stay on the laptop by default. If the resident shares them, only the scale and tags go, not the spoken words. Their words are shared only with the extra consent below.
- The purpose is trends over time and across facilities, for example whether moods drop when meals are missed. Check-ins are never used to judge one resident.
- Pick a published, validated question set together with a university partner, so researchers trust the data.

### Their own words
How residents describe their feelings, especially after dealing with staff, can be powerful evidence. So sharing their words with researchers is allowed, with extra care:
- **A separate, deeper explanation**, in large text and read aloud. It covers what is shared, who can see it, and how names are removed. It also says plainly that someone who knows the resident might still recognize how they talk.
- **An extra chance to say no**, for example: "Are you sure? You can still share your feelings without your words." Saying no changes nothing else.
- **Scrubbing:** names, rooms and places are removed from the typed-out words automatically, and only approved researchers can see them.
- **Voice recordings are a further, separate choice.** A voice can identify a person on its own; HIPAA counts voice prints as an identifier. Recordings stay in the secure research workspace and are never published or handed out.
- **Withdrawing** takes the resident's words out of all future data releases.

## Research data (university partners)
- **Consent:** a separate consent screen in large plain text, read aloud on request. The app saves which consent version was signed, and the resident can withdraw any time.
- **De-identification happens on the laptop, before data leaves:** no names, rooms, birthdays or contact details. Dates are rounded to the week and ages put in bands. A facility appears only where 5+ residents take part. Free text is left out unless the resident consented and it was scrubbed. The benchmark is HIPAA Safe Harbor's 18 identifiers, even where HIPAA doesn't strictly apply.
- **Study IDs** are random and made on the laptop. The server never learns which account a study ID belongs to.
- **Access:** universities need IRB approval and a signed data use agreement that bans re-identification and passing data on. A secure analysis workspace is better than handing out files.
- **Quality:** a versioned data dictionary, a fixed category list mapped to CMS F-tags, timestamps, the CMS provider number, and a record of how each entry was made (voice, typed or imported).
- **Published statistics** add small random noise and hide any count under 5.

## Security baseline
- **Laptop:** encrypted local log (key protected by Windows), app lock with Windows Hello, encrypted backups, code-signed installer and signed updates.
- **Network:** TLS 1.3 only, and every submission is signed.
- **Server:** a HIPAA-eligible cloud under a business associate agreement (BAA). It may not be legally required, but partners will expect medical-grade hosting. Encryption at rest with managed keys. Identity and data in separate databases, accounts and keys. Least privilege, an append-only audit log, tested encrypted backups, and set retention limits.
- **Process:** review the threat model each release, scan dependencies, and get an independent pen test before launch. Add a `SECURITY.md` explaining how to report bugs, and a written plan for incidents and breach notification. Long term, get a SOC 2 audit for institutional partners.

## Legal checks before launch (with a lawyer)
- HIPAA: the project is probably not a covered entity, but partners may require HIPAA-level handling.
- The FTC Health Breach Notification Rule may cover health apps outside HIPAA.
- NC breach notification law (NCGS 75-65).
- For research: the Common Rule (45 CFR 46), IRB approval, and a Certificate of Confidentiality.
- A plain-language privacy policy and terms.

## Build phases
1. **Harden the laptop** (no server needed): encrypt the local log, add the app lock, sign the code. This protects residents now.
2. **Sending:** device enrollment, anonymous tokens, the named and anonymous relay, warnings, metadata stripping and delivery receipts.
3. **Counts (tier 1):** signed submissions, the 5+ rule and a public facility dashboard.
4. **Accounts:** passkeys, recovery through helpers, multiple devices.
5. **Mood check-ins:** local first, then shared.
6. **Research tier:** consent, the de-identification pipeline, a first university partner and IRB approval.

Each phase ends with a security review of the new piece. No real resident data reaches a server piece until its review passes. Phase 2 onward needs funding for hosting, security reviews and legal advice; see the pilot/funding plan.

The 5-resident pilot needs only phases 1 and 2. See [pilot-checklist.md](pilot-checklist.md).

## Decisions (2026-10-24)
- Anonymous sending: our own relay. It's the smoothest option: one click, with confirmed delivery.
- Mood check-ins: a daily prompt.
- Spoken words: allowed in research, with a deeper explanation and an extra chance to opt out.
- Account recovery: to be worked out with the helpers and the ombudsman partner during pilot prep.
- Facility first: for serious complaints, the app drafts emails to the director of nursing and the administrator, and recommends sending those first.
- Pilot length: 8 weeks, with surveys at the start and the end to measure the impact.
