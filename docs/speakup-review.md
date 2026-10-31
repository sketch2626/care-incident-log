# Speak-up review: branch `wip/report-to-state` (fddfdbc) and the legal facts

Reviewed 2026-10-30 by a worker on the second account: Opus 5.5 for the code review, fact check and plan, and a Sonnet 5.5 helper for running the old commit. The plan built on this review is `docs/speakup-plan.md`.

This is research, not legal advice. Nothing here has been read by a lawyer or an ombudsman yet (see S12 in the plan).

## The short version
- **The old commit runs, and it's worth mining, but it shouldn't be merged.** Main's `server.py` has moved so far (about 1,500 changed lines) that a merge isn't practical. Every useful piece is a small port.
- **It wasn't finished.** It has no screens, no tests and no citations behind its retaliation paragraph. Without `contacts/` and `docs/retaliation.md`, which it never committed, a letter goes to "North Carolina State Survey Agency" with no address.
- **Three legal facts on main are stale or wrong,** and one code comment misstates the law. See "What must change" below.
- **The biggest find:** the official DHSR pages carry a complaint email address that our contacts file says doesn't exist. We don't yet know if complaints are accepted that way.

## What must change on main (facts)
| # | Where | Today | Should be | Why |
|---|---|---|---|---|
| 1 | `docs/retaliation.md` lines 37-38, `contacts/NC.json` lines 70-75 | Discharge rules cited to **F622** | **F627** | CMS moved them, effective 2025-04-25, surveyors from 2025-04-28. F622 is now an empty heading saying so. |
| 2 | `docs/retaliation.md` line 39, `contacts/NC.json` line 78 | Discharge notice cited to **F623** | **F628** | The same move. |
| 3 | `contacts/NC.json` line 109 | Appendix PP link | The `som107ap_pp_guidelines_ltcf.pdf` link | The old link serves **Rev. 225 (2024-08-08)**, from before the move. |
| 4 | `contacts/NC.json` lines 9, 13, 14 | `email: null`, `accepts_email_complaints: false`, "shows no email address" | Record `DHSR.ComplaintIntake@dhhs.nc.gov`; set `accepts_email_complaints` to `null` (unknown) until confirmed | Both DHSR pages have a "Send an email" link. The address is hidden in the page and appears only when the link is used, which is likely why the 2026-10-24 check missed it. The pages don't say whether complaints are taken this way. |
| 5 | `reports.py` line 91 | "CMS needs a pattern for neglect" | Remove the claim | CMS says the opposite (quoted below). The 3+ rule is ours, not the law's. |
| 6 | `reports.py` line 30 (`ATTESTATION`) | "each entry … was written by me" | Wording that fits dictation and Mary | Mary and Gemini write `formal_summary`. A signed line must be literally true. |
| 7 | `reports.py` line 59 (F600 cite) | `§483.12(a)(1)` | `§483.12, §483.12(a)(1)` | (a)(1) is the abuse line. Neglect is in the opening of §483.12, which is also under F600. |
| 8 | `reports.py` `_RULES`, `medication` | F760 on every medication problem | F760 only when it sounds significant, or soften | F760 covers **significant** medication errors. A late pill isn't always one. |

## The fact check (all checked 2026-10-30)
| Fact | Result | Source |
|---|---|---|
| Appendix PP current version | **Rev. 232, issued 2025-07-23.** CMS transmittals 234-250 (to 2026-10-16) touch other parts of the manual, none touch Appendix PP. Transmittal 233 returned "not found", so I couldn't read it. | [Appendix PP](https://www.cms.gov/Regulations-and-Guidance/Guidance/Manuals/downloads/som107ap_pp_guidelines_ltcf.pdf), [transmittals](https://www.cms.gov/files/document/r250soma.pdf) |
| F585 Grievances, §483.10(j) | Verified. Includes the right to file anonymously, a named Grievance Official, a written decision on request, and keeping results at least 3 years. | Appendix PP, F585 |
| F550 Exercise of rights, §483.10(a)-(b) | Verified. "without interference, coercion, discrimination, or reprisal". CMS's example: keeping a resident out of group activities as a reprisal. | Appendix PP, F550 |
| F600 Abuse and neglect, §483.12 | Verified. "Retaliation by staff is abuse, regardless of whether harm was intended, and must be cited." **Context:** that line sits in a passage on staff reacting to resident behavior, so it's strongest for staff getting back at someone. F550 is the more direct rule for retaliation over a complaint. | Appendix PP, F600 |
| Neglect needs no pattern | Verified: "Neglect may be the result of a pattern of failures or may be the result of one or more failures involving one resident and one staff person." | Appendix PP, F600 |
| Facility must report abuse fast, §483.12(c)(1) | Verified: to the administrator and other officials, within 2 hours if abuse or serious injury, otherwise within 24 hours. | Appendix PP, §483.12(c)(1) |
| Failing to protect after a report | Verified text: "Retaliation occurs against a resident who reports an alleged violation" is an example of failing to protect. It sits in the section after F609; I didn't pin down its exact tag heading, presumably F610. **Not cited in the proposal for that reason.** | Appendix PP |
| F607 | Verified, but it protects **staff** who report crimes, not residents. Left out of `RETALIATION_REGS`. | Appendix PP, F607 |
| F627, F628 | Verified. F627 holds the six allowed reasons and "may not transfer or discharge … while the appeal is pending". F628 holds the notice: 30 days, reason, appeal rights, ombudsman contact. | Appendix PP, F622-F628 |
| F576 communication | **New to us, verified.** Private phone calls, keeping a cell phone, internet "to the extent available to the facility", and mail. It matters if a laptop or phone is taken after a complaint. | Appendix PP, F576 |
| The other 10 tags in `REGULATIONS` (F725, F919, F809, F692, F677, F561, F690, F760, F686, F689) | All exist in Rev. 232 and the cites match. **Not checked:** the short titles, which come from CMS's tag list, not Appendix PP. | Appendix PP |
| §483.35(a) | Cite still right. A 2025-12-03 rule (90 FR 55697) changed the section; the waiver paragraph is now (e). Appendix PP still says (f). | [Cornell LII](https://www.law.cornell.edu/cfr/text/42/483.35) |
| NCGS 131E-117(12), (15) | Verified; last amended 1997. | [ncleg.gov](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_131E/GS_131E-117.html) |
| NCGS 131E-119 | Verified. | [ncleg.gov](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_131E/GS_131E-119.html) |
| NCGS 131E-124 | Verified. Start: immediately (life-threatening), 24 hours (abuse), 48 hours (neglect), two weeks (other); finish in 30 days. Identities stay confidential. **Add:** a complainant learns about a named resident's case only with written authorization from that resident, their legal representative or responsible party. That affects family who file. | [ncleg.gov](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_131E/GS_131E-124.html) |
| DHSR complaint line | **1-800-624-3004** (within NC), 919-855-4500. Weekdays 9-12 and 1-4, except holidays. Fax 919-715-7724. 2711 Mail Service Center, Raleigh, NC 27699-2711. An older county handout says 8:30-4; the DHSR page is the one to trust. | [File a complaint](https://info.ncdhhs.gov/dhsr/ciu/filecomplaint.html), [unit page](https://info.ncdhhs.gov/dhsr/ciu/index.html) |
| DHSR limits | Only incidents **from the past year**. Investigations are unannounced. Identifying details aren't shared with the facility. There's no online form; the printable form was last revised 12/2007 and asks for the resident's name, birth date and room. | same; [form](https://info.ncdhhs.gov/dhsr/ciu/pdf/complaint_form2.pdf) |
| DHSR and facility first | Its poster "strongly encourages" trying the facility first. Encouraged, not required. | [poster (2010)](https://info.ncdhhs.gov/DHSR/ciu/pdf/ComplaintIntakeUnitPoster.pdf) |
| State ombudsman | **(919) 855-3400**, 2101 Mail Service Center, Raleigh, NC 27699-2101. The program page itself shows only the general 1-800-662-7030. | [May 2026 roster](https://www.ncdhhs.gov/ombudsman-listed-area-agency-aging-8/open), [county list](https://www.ncdhhs.gov/ombudsman-county-3/open), [program page](https://www.ncdhhs.gov/divisions/aging/long-term-care-ombudsman) |
| Ombudsman confidentiality | Verified: no disclosure of a resident's or complainant's identity without consent or a court order. Consent can be spoken or visual if documented. This closes the "to verify" in `docs/backend-plan.md`. | [45 CFR 1324.11(e)(3), Cornell LII](https://www.law.cornell.edu/cfr/text/45/1324.11) |
| Adult Protective Services | The directory link works. "Any person" with reasonable cause to believe a disabled adult needs protective services must report. **Not checked:** the statute's definition of "disabled adult", or what this means for human helpers. | [108A-102](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_108A/GS_108A-102.html), [directory](https://www.ncdhhs.gov/localDSS) |
| Disability Rights NC | **New to us, verified.** Federally designated protection and advocacy group, 1-877-235-4210. Useful for younger residents with disabilities. | [DRNC](https://disabilityrightsnc.org/contact-us/) |

**A note on sources.** The eCFR site turned away automated readers and I didn't try to get past it. Federal nursing home rules were read as quoted in Appendix PP; §483.35 and 45 CFR 1324.11 came from Cornell's Legal Information Institute. A person should compare these with eCFR once. The NC statutes came through a page summarizer, so S12's reviewer should read 131E-124 in full.

**Couldn't verify:**
- Whether DHSR accepts complaints by email.
- Whether DHSR accepts complaints with no name at all. Its pages promise the facility won't be told, which isn't the same thing.
- That "F610" is the tag for the failure-to-protect example.
- The Appendix PP short titles.
- Transmittal 233.

## What the old code does (run 2026-10-30, scratch data, Sonnet 5.5 helper)
**Worked:** migration from the older database, soft delete everywhere, HTML escaping, the retaliation marker in the report and spreadsheet, the rule that an edit keeps the flag, no network use with Gemini off, and the `X-Tracker` and Host checks.

**Broken:**
- **A typo in a letter to the state:** "I believe 2 of these incidentss happened because I complained."
- **A brand-new log reads as retaliation.** 0 incidents before a first grievance and 3 after raises "Care got worse after you complained", and that claim goes in the letter. Someone who just started logging would be making a false statement about care. This is the most serious flaw.
- **False alarms.** The red "rough treatment" check fired on "they took roughly 40 minutes", "pushed my wheelchair to lunch", "pushed back my bath", "pinched nerve", "nobody hit me" and "grabbed my tray". The retaliation check fired on "my discharge from the hospital", "the discharge from my wound" and "take away my tray".
- **One bad date row stops everything.** With any submission on file, `/api/status` and every letter return an error. Main's `clean_incident` is stricter, but direct database rows could still do it.
- **Red forever.** A 13-month-old dangerous incident stays red, and nothing mentions DHSR's one-year limit.
- **Follow-up letters** quote a future-dated complaint, don't say who it went to, and never mention an earlier grievance.
- **Date checks:** `2026-13-45` is accepted in a letter's date range.

**Missing:**
- Choosing which incidents go in a letter. Every route takes dates only, and `?ids=` is ignored.
- Any anonymous version. With no name it still prints the room number and signs "A resident".
- Any law behind the retaliation paragraph (`RETALIATION_REGS` is empty).
- Screens (`#send`, `#rights`), tests, and any way to do it by voice.
- Packaging: `packaging/build.py` bundles neither `contacts/` nor `docs/`, so even on main an installed app wouldn't find them.
- A delivery route. It writes an "attached PDF" letter, but in NC the confirmed routes are phone, mail and fax, and it's unclear how a resident prints.

**Doubtful claims in its wording:**
- "3 or more is a pattern the state looks for." I found no source. It's the app's own rule, so it must not be told to residents as the state's.
- "Please give it to me within 7 days." No rule sets 7 days. The rule is the facility's own "reasonable expected time frame".
- "the printable report saved as a PDF, and the spreadsheet" assumes a printer and email.

**Already fixed on main, or not real problems:** the size limit and the non-object JSON crash are handled by `_body()`. A foreign `Origin` isn't checked, but a browser can't send `X-Tracker` across sites because `OPTIONS` is refused, so that stays safe.

**Note:** the helper's `?ids=` count used a bad regex, so "ids ignored" rests on reading the route code. `RETALIATION_WORDS` is also read once at start-up, which is fine once the file ships with the app.
