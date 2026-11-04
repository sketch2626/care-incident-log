# Speak-up plan: Mary's speak-up skill

Written 2026-10-30 (Opus 5.5, second account). Evidence and sources: `docs/speakup-review.md`. This is research, not legal advice; S12 puts it in front of real reviewers before the pilot.

**Where it stands (2026-11-04):** S0 is done (2026-10-30). S1 onward waits on Andy's answers to the decisions in section 9, numbered **SD1-SD10** so they don't clash with his standing decisions (D numbers, `docs/decisions.md`). In the roadmap this is M27.

## The idea in plain words
A resident tells Mary what's wrong, as they already do. If they want to take it further, Mary helps them do it in the order that usually works: the facility, then the ombudsman, then the state. She works out what to say, pulls the dated record together, and tells them their rights. **The resident decides every step, and the resident does the sending.** Mary never sends anything.

Mary stays a friend first. Speak-up comes up only when the resident raises a problem or asks. She never nags (her safety rules say so), and a resident who says "no" hears no more about it.

## 1. What to keep from the branch
Port these by hand onto today's main. Don't merge.

| Keep | From | Changes on the way in |
|---|---|---|
| `load_contacts`, `state_abbr`, `_safe_url`, `_safe_email` | `server.py` | Add bundling; keep the "only what the file says" approach. |
| `render_markdown` and the rights page | `server.py` | As is; add tests. |
| `retaliation` column and its "edit keeps the flag" rule | `server.py` | As is. |
| `add_submission` idea | `server.py` | Becomes the steps table (section 4). Refuse future dates. |
| `_complaint`, `build_draft`, `build_letter_html`, `build_grievance_html`, the letter CSS | `reports.py` | Take chosen incident ids, fix the plural bug, add anonymous and new wording. |
| Retaliation marker in the report and spreadsheet | `reports.py` | As is; fix the F600 label so a retaliation tag doesn't read "repeated failure". |
| The word list idea | `docs/retaliation.md` | Tighter phrases (section 6). |
| Urgency levels | `compute_status` | Keep the shape; rewrite the checks (section 3). |

## 2. What to drop
- **The automatic "care got worse after you complained" claim.** A count of log entries measures how much someone wrote down, not how care changed. Section 6 replaces it with plain dates and numbers the resident chooses to use.
- **The word-root harm and retaliation regexes** (`rough`, `push`, `threat`, `discharge`). Too many false alarms.
- **"3 or more is a pattern the state looks for"** and **"within 7 days".** No source.
- **The attached-PDF assumption.** Replaced by section 5's real delivery routes.
- **`/api/retaliation/words` and `dest_and_to`,** the route that takes `to` twice. Use plain `dest` and `ids`.
- **The floating mic, the start-with-Windows option, `/app/show` and quick notes.** Not speak-up, and `desktop.py` has moved on. The mic idea already belongs to M12; Mary covers quick notes.

## 3. How it works with Mary
**One mind, one voice.** Every line is Mary's, in the brain's conversation. The skill gives her facts and tools; it never plays a scripted line.

**Safety comes first and doesn't change.** The emergency check runs before any skill. The four safety sections stay word for word: she never promises to report anything herself, and she still can't call anyone. Nothing in this plan needs them changed.

**The ladder.** Each step is offered, never required, and she always says they can go straight to the state or ombudsman.

| Step | Who | What Mary helps with |
|---|---|---|
| 0 | Write it down | Today's incident offer. Unchanged. |
| 1 | Tell someone on the floor | The charge nurse or social worker, from her current rules. |
| 2 | Facility grievance | A letter to the Grievance Official, or words for saying it out loud. Asks for the written decision the rule promises, using the facility's own time frame. |
| 3 | Ombudsman | The regional ombudsman from the county list, or the state office, (919) 855-3400. Free, and confidential by federal rule. |
| 4 | The state | DHSR, 1-800-624-3004. A call sheet first; a letter or form if they want one. |
| Alongside | Others | County DSS Adult Protective Services, Disability Rights NC for residents with disabilities, and 911 for danger. |

**Red lines skip the ladder.** For abuse, injury, immediate danger, retaliation or a discharge threat she names the state and ombudsman right away, alongside the facility. The final red lines get defined with the ombudsman partner (`docs/pilot-checklist.md`). When a resident tells the facility about abuse or neglect, the facility has to report it up within hours (§483.12(c)(1)), so it helps to get that in writing with a time on it.

**After a step:** she asks once, around the date they expect an answer: "Did they ever get back to you?" If they say to drop it, she drops it.

**Urgency, rewritten:**
- Red only for a rating of dangerous, the resident's own retaliation flag, or a harm phrase the resident confirms.
- Nothing stays red forever. Anything older than 10 months is flagged as "the state only looks at the past year"; past 12 months it says so plainly and suggests the ombudsman.
- Her pattern line says what's true: "That's the fourth time this month."
- Any bad date is skipped, never a crash.

**The skill.** `skills/speak_up/`: `offline: "works"`, `sees: true`, `storage: true`, default on. The core stays in charge of the log.

- **A new core door.** Skills may not touch incidents, by design. So the core adds a narrow `ctx.care_log`, available only when a manifest asks for `"care_log": true`, with the contract tests updated:
  - `summary()`: counts only.
  - `choose(ids)`, `flag_retaliation(id, on)`, `add_step(...)`, `make_document(kind, ids, named)`.

  No raw SQL, and no other skill gets it. Letters are built in core `reports.py`, because they're evidence.
- **Actions (about 6, under the 20-tool limit):** `what_are_my_rights`, `who_to_call`, `get_ready_to_tell`, `make_document`, `mark_as_retaliation`, `record_step`.
- **Offline:** phrases such as "who do I call", "ombudsman number" and "my rights" work with no internet. Each runs after the emergency check. Phrases must not clash with the yes/no words.
- **Instructions** stay under 400 characters, and within the 4,000-character budget.

**The screen** (boards first; how Andy sees them is in `docs/how-we-work.md`, "Boards"): one big call sheet with the number, the hours and "what to say"; a letter view; "My rights" in big plain text. Text 20px or larger, targets 64px or larger, everything by voice or one tap, no key combos.

## 4. The evidence package
A resident picks what goes in, by voice ("just the call light ones from October") or by tapping. Built offline on the laptop by `reports.py`, with no Gemini.

**Contents:**
1. A cover letter to the chosen recipient, citing earlier steps with dates and who they went to.
2. A timeline of the chosen incidents, with record numbers, what happened, waits, who was told and what came of it.
3. Retaliation entries, marked, with the resident's stated reason.
4. The steps so far: who was told, when, how, and any reply.
5. The regulations table, using verified citations, with the existing footnote that the state makes the determinations.
6. An honest statement of how the record was made.

**Never included:** Mary's conversations, her memory of the resident, mood, health facts the resident didn't choose, other residents' names, or anything from Andy Flow they didn't select.

**Making it hold up:**
- **Attestation.** Proposed: "I declare that these entries are my own account, told or typed by me and recorded by this app at the time shown under 'Logged at'. Summaries were written by the app from my words and I have reviewed them. They are true and accurate to the best of my knowledge."
- **Each entry shows how it got there** (spoken to Mary, typed, imported) and whether it was changed later (`updated_at` isn't shown today).
- **A change history.** A new `incident_history` table keeps the old version on every edit, with a hash chain and a short code on the package. This shows a record wasn't quietly rewritten; it doesn't prove the record is true, and we must never say it does.
- **Grievance letter.** Asks for what §483.10(j)(4) gives them by name.
- **The one-year check** warns before a letter to DHSR includes older incidents.

**New `speakup_steps` table** (replaces `submissions`, in the core, not in skill storage): date, kind, recipient, method, incident ids, named or anonymous, reply date, reply note. Backed up with the database and soft delete only.

## 5. Getting it there
Pilot rule: **the app sends nothing.** A relay comes only after the security review in `docs/backend-plan.md`.

| Route | Status in NC | How |
|---|---|---|
| **Phone** | Confirmed; works for nearly everyone | Call sheet on screen. They have a right to private calls (F576). |
| **Ombudsman in person** | Confirmed program | Show the screen or hand over a copy at a visit. |
| **Mail** | Confirmed | Needs printing. Stationery and postage access is a right (F576); the resident pays. |
| **Fax** | Confirmed | Needs a helper or family. |
| **Email** | **Unconfirmed** (SD1) | Saves the document for their own mail if DHSR confirms. |
| **A copy to family or a helper** | Their choice | Save to a file; they hand it on. |

Printing at the facility shows staff the complaint, so Mary says that first.

## 6. Retaliation flagging
**Only the resident flags.** Three layers:

1. **They say it.** "I think this is because I complained" sets the flag after a plain confirmation.
2. **Mary asks, once.** On a whole phrase ("since I reported it", "told me to stop complaining", "said I have to leave", "they're getting back at me") she asks: "Do you think that's because you complained?" Live and Normal use her judgment through the skill's instructions. Offline uses a short phrase list in the core, tested against the false-alarm lines in the review. Bare "discharge", "threat" or "rough" never trigger it.
3. **The dates, not a verdict.** With a past complaint on file she can show: "You complained on March 3. You logged 2 problems in the 30 days before and 6 in the 30 days after." Shown only if the log was already running at least 60 days before the complaint, with a note that it counts what was written down. It goes in a letter only if the resident says so (SD8).

**When flagged,** she gives their rights in plain words and suggests the ombudsman; it counts as a red line. A discharge notice means "don't sign what you don't understand, and call the ombudsman now". If a laptop or phone is taken after a complaint, she can't say so on a laptop that's gone, so the rights page and setup paper mention it up front.

**Before a named facility letter,** she states their retaliation rights, as `docs/backend-plan.md` already requires.

**`RETALIATION_REGS` proposal** (not applied; `reports.py` is unchanged). Add to every incident the resident flagged:

```python
# Verified 2026-10-30 against CMS State Operations Manual Appendix PP, Rev. 232 (issued 2025-07-23).
RETALIATION_REGS = [
    {"tag": "F550", "title": "Resident Rights/Exercise of Rights", "cite": "§483.10(a)(1)-(2),(b)(1)-(2)"},
    {"tag": "F585", "title": "Grievances", "cite": "§483.10(j)(1)-(4)"},
    {"tag": "F600", "title": "Free from Abuse and Neglect", "cite": "§483.12, §483.12(a)(1)"},  # see SD2
]
```

Notes for the build:
- `_all_regs()` lets these entries replace those in `REGULATIONS`, so F550 and F600 must stay identical in both. That includes the F600 cite change in S1.
- `_describe` must not call a retaliation F600 "repeated failure — possible neglect".
- F585's title comes from Appendix PP. F550's and F600's come from main's existing table.

**Only when the facts call for it,** not on every flag:

```python
RETALIATION_REGS_DISCHARGE = [  # a discharge or transfer threat or notice
    {"tag": "F627", "title": "Inappropriate Transfer and Discharge", "cite": "§483.15(c)(1)-(2)"},
    {"tag": "F628", "title": "Transfer and Discharge Process", "cite": "§483.15(c)(2)(iii),(c)(3)-(6),(c)(8)"},
]
RETALIATION_REGS_COMMUNICATION = [  # phone, laptop, internet or mail taken or blocked
    {"tag": "F576", "title": "Right to Forms of Communication with Privacy", "cite": "§483.10(g)(6)-(9)"},
]
```
F627's title and the cites are from Appendix PP. **F628's and F576's short titles are not verified:** F628's comes from secondary sources and F576's from memory of CMS's tag list, so check both before use. Left out on purpose: F607 (protects staff, not residents) and the failure-to-protect example (exact tag not confirmed).

The NC statutes (131E-117(12), 131E-117(15)) go in the letter text and the rights page, not in this table, which is federal F-tags only.

## 7. Privacy
**Every send asks one question: "Put your name on this?"** Saying no doesn't make anyone invisible, so she says what it does cover.

| Recipient | With a name | Without a name |
|---|---|---|
| **Facility** | They know who complained. Retaliation rights come first. | Federal right to file anonymously (§483.10(j)(4)(i)). Details can still point to them, and a person who needs their own care fixed usually has to be identifiable. |
| **Ombudsman** | Won't disclose without their consent (45 CFR 1324.11(e)(3)). | Fine for advice. |
| **DHSR** | State must keep the identity confidential (131E-124(c)); the facility isn't told. Family who file need written authorization to get case details. | **Unconfirmed** (SD1). Until then, Mary doesn't say it's possible. |

**The anonymous version** removes name, room, signature and names of other people, and the "write back to me" line, then shows what's left. The old code left the room number in. A plain note warns that dates and details can still identify them. We never say "100% anonymous".

**Never leaves the laptop without a clear yes:**
- Any incident, letter or package.
- Names of staff, other residents or family.
- Their name, room, birth date or health details.
- The fact that they complained at all.

**A clear yes** means: Mary says who it's for and what's in it, and they say yes to that, for that one thing. A yes doesn't carry over and doesn't last past that moment. A record of it goes in `speakup_steps`. Today's ten-minute offer rule doesn't apply here.

**Gemini sees less, too:**
- `view()` gives counts and step names only, never the resident's words, staff names or letter text.
- Letters are built offline and shown on screen.
- Speak-up needs the paid-tier setup already required for residents' talks (D21).

**Other points:**
- A resident who can't decide clearly is out of scope for the pilot; the helper and ombudsman partner settle how to handle it.
- The state of the laptop itself matters. The encrypted log and app lock in `docs/backend-plan.md` aren't built, and a complaint record on an unlocked laptop in a shared room is a real risk. S12 weighs whether the pilot needs the lock first.
- Resident data stays out of tests; use fictional names only.

## 8. Build list
Each item gets one worker and committed checkpoints. Who runs what is in `docs/how-we-work.md`. "Andy" means he tries it.

| # | Item | Done when |
|---|---|---|
| **S0** | Fix the facts: `docs/retaliation.md`, `contacts/NC.json`, the backend plan's "to verify" (review table 1-4). Add F576, DRNC, and the one-year limit. | Docs match the review, `verified_on` is updated, tests pass. **Done 2026-10-30.** |
| **S1** | Accuracy in `reports.py`: `RETALIATION_REGS` per SD2, the neglect comment and rule per SD3, F600 cite, F760 wording, attestation per SD9. | New tests cover tags and the labels; a report reads true; a fresh look at each cite against Rev. 232. |
| **S2** | The record: `retaliation` column, `speakup_steps`, `incident_history` with hash chain, migration, entry source shown in reports. | Migration tested on an older database; edits keep history; soft delete still everywhere. |
| **S3** | Contacts and rights in the app: port the loader and rights page, bundle `contacts/` and `docs/retaliation.md` in `packaging/build.py`. | A test build finds both from a scratch `APPDATA`; missing files give a plain message. |
| **S4** | Letters and package: port and rewrite with chosen ids, follow-ups naming earlier steps, the one-year check, no plural bug, tests with fictional data. | Every scenario in the review passes; a golden-text test for each letter. |
| **S5** | Anonymous versions and the "clear yes" rule. | Tests prove no name, room or staff name in an anonymous letter; each recipient has its honest note. |
| **S6** | `ctx.care_log` core door and contract changes. | Contract tests pass; only a declaring skill gets it; a skill can't read raw text through `view()`. |
| **S7** | Boards for the call sheet, letter view and rights. | Andy approves the boards (`docs/how-we-work.md`, "Boards"). |
| **S8** | `skills/speak_up/`: actions, instructions, offline phrases, screens matching the boards. | Works in Live, Normal and Offline; emergency line never reaches it; `tests/test_skills_contract.py` passes; `node --check` passes. |
| **S9** | Retaliation: phrases, Mary's one question, dates view per SD8. | All review false-alarm lines stay quiet; true phrases ask once; offer rules unchanged. |
| **S10** | Urgency rewrite and her one follow-up. | Nothing red forever; bad dates don't crash; asks once, stops when told. |
| **S11** | Brain bench cases (M9d): frightened resident, "don't write that", retaliation, abuse, a demand to report for them, confused resident. | Passes on the real model; **Andy tries the whole ladder** with fictional data. |
| **S12** | Outside review: an ombudsman and a lawyer read the plan, letters, rights page and red lines. Compare rules with eCFR. | Their changes are in; pilot checklist updated. |

**Order:** S0, S1, S2, then S3-S5, then S6-S10, then S11-S12. S0 and S1 are safe to do now and fix live errors. SD1 can happen in parallel. Update `docs/pilot-checklist.md` and "What you can do" in `mary/instructions.md` as pieces land, and never the safety sections.

## 9. Decisions for Andy
**SD1. Who asks DHSR two questions: do you take complaints by email, and do you take them with no name?**
- A. Andy calls 1-800-624-3004, weekdays 9-12 or 1-4, a few minutes.
- B. The ombudsman partner or a helper asks.
- C. Leave email out of the pilot and never mention no-name complaints.

*Recommended: B if a contact exists soon, otherwise A. Until then, C applies.*

**SD2. When a resident flags retaliation, should the record cite F600 (abuse) as well as F550 and F585?**
- A. Always, since CMS says staff retaliation is abuse and must be cited.
- B. Only when a person on staff did it, such as a threat or rough handling.
- C. Never automatically.

*Recommended: B. It's the strongest word in the record, and the line's context is staff conduct. The code block shows it in; B would make it conditional.*

**SD3. When does a care failure cite F600 for neglect?** The law doesn't require a pattern.
- A. Keep 3+ of one kind, fixing only the wrong comment.
- B. 3+ of one kind, or any single incident rated serious or dangerous.

*Recommended: B. It fits CMS's definition, and it's still labeled "possible".*

**SD4. Should Mary read a letter out loud?** In Live and Normal, that sends its words to Google. Her offline voice would break "one talk keeps one voice".
- A. She sums it up without names or their words, and the full letter shows on screen; she reads the whole thing only if they ask, after saying it goes through Google.
- B. Never read it aloud.
- C. Always read it.

*Recommended: A. Residents with weak eyes need a way to hear it.*

**SD5. Should the facility letter say they might go to the state?** The old one did.
- A. Leave it out and stay friendly.
- B. Keep a mild line: "I know I can also contact the ombudsman or the state."
- C. Keep the old line.

*Recommended: B. It's true, calm, and stays on the facility-first spirit.*

**SD6. Do staff names go in letters by default?**
- A. Left out unless the resident says to include them, each time.
- B. Included whenever the log has them.

*Recommended: A for the facility, and ask each time for the ombudsman and state. Names help investigators, but it's their choice.*

**SD7. Who reviews before the pilot (S12)?**
- A. The regional ombudsman plus Disability Rights NC or Legal Aid of NC.
- B. A private attorney, if funding appears.
- C. Ombudsman only.

*Recommended: A. Build as if the state will read it, because it will. This also covers what human helpers must do under NC's reporting law, which I couldn't settle.*

**SD8. Keep the before-and-after numbers from section 6?**
- A. Show the resident, and use in a letter only if they say so.
- B. Show the resident only, never in a letter.
- C. Drop it.

*Recommended: A, with the 60-day rule and the honest note. A timeline can be powerful evidence, and it's their record.*

**SD9. How do residents who can't hold a pen sign?**
- A. The record states it was told to the app, with a line for a witness or mark, and the phone route needs no signature.
- B. Ask the ombudsman partner first and leave it blank for now.

*Recommended: A now, confirmed at S12.*

**SD10. What's the skill called in Mary's menu?**
- A. "Speak up".
- B. "My rights".
- C. "Get help with a problem".

*Recommended: C or B in the menu, because a menu that says "Speak up" is the scary reporting tool we said we wouldn't build, and the laptop's on the bedside table. Mary can still call it speaking up.*
