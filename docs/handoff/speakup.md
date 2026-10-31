# Handoff: speak-up review and plan (second account, branch `other/speakup`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read only these:
- `docs/status.md`: "Build history and notes", the part about `wip/report-to-state`.
- `docs/retaliation.md`, `contacts/NC.json`, and `docs/backend-plan.md` ("Facility first" and the sending parts).
- `docs/companion-plan.md`: the speak-up parts, and why the app is companion first.
- `reports.py` and the incident parts of `server.py` on main, so you know today's care log.
- `skills_core.py`, `docs/skills-design.md`, and how Mary runs skills today (`skills/voice_comfort/`, `skills/pictures/`).

**Why:** speak-up is the heart of the mission: making care failures impossible to ignore. It becomes Mary's speak-up skill, and it must be right before the pilot (Next step 4).
- The branch `wip/report-to-state` (commit fddfdbc, 2026-10-24) holds a report-to-state backend, a send wizard, retaliation flags and quick notes. Helpers were stopped partway through, and nobody has reviewed or tested it.
- Main has changed hugely since then: Mary, skills, voices, memory.

**Do (a review and a plan, not a merge):**
1. **Review fddfdbc deeply,** for correctness, safety, privacy and legal accuracy. Run what can be run in a scratch copy (`git worktree` of that commit, scratch `TRACKER_DATA`). Note what works, what's broken and what's missing.
2. **Check every legal and contact fact against official sources** (WebSearch and WebFetch are fine; no browser):
   - CMS F-tags (Appendix PP);
   - the NC statutes (NCGS 131E-117, 131E-124);
   - the DHSR complaint line;
   - the state ombudsman number.

   Give the source link and the date checked for each. Flag anything stale.
3. **Write `docs/speakup-plan.md`:**
   - what's worth keeping from the branch;
   - what to drop;
   - how to rebuild it on today's main as Mary's speak-up skill: by voice with Mary, facility first, then the ombudsman, then the state;
   - the evidence package from the care log;
   - retaliation flagging;
   - privacy (named or anonymous), and what never leaves the laptop without the resident's clear yes;
   - a numbered build list (S1, S2, …) with "done when" lines and models, in the roadmap style;
   - **decisions for Andy,** each as a short question with options and your recommendation.
4. **Propose the contents of `RETALIATION_REGS`** from the verified citations, as a code block in the plan. Don't change `reports.py`.

**Don't:**
- change app code;
- merge;
- touch `main`;
- send anything anywhere;
- make up a citation. If you can't verify something, say so.

**Models:** Opus (xhigh) for the review and the plan; Sonnet for running tests on the old commit.

**Finish:** commit the plan (and any review notes under `docs/`) on `other/speakup` with the subject `WAITING: speak-up review and plan ready for Andy`, then stop.
