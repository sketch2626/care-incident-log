# Handoff: M9c, Mary's memory core (second account, branch `other/M9c`)

Read `docs/handoff/_common.md` first. Then read only these:
- In `docs/mary-roadmap.md`: M9c ("Andy's design"), M9e, and "Main talk mode, being decided".
- In `mary.py`: `class Memory` (around line 198), `MAX_FACTS`, `system_text()`, `LIVE_MEMORY_TOOLS`, `tell_story()`, and how `reply()` runs tools.
- In `server.py`: `mary_memory()`, `mary_live_memory_call()`, and the `/api/mary/tool` route (look for `remember_fact`).
- In `voices.py`: `LIVE_TOOLS_NOTE`. In `web/mary/app.js`: the My info panel (M4b blocks).

**Andy's design (2026-10-30), in his words:** "everything that she remembers, any personal memories, get logged… like she logs the other care lapses… and then anytime any of that information is needed… she can just pull it right up. That way it doesn't have to be sent to her every time. So she needs her own memory core in the app."

**Today:** `mary/memory.json` holds the name plus at most 40 facts (the oldest are dropped). The whole list goes to Gemini every session and turn.

**Build:**
1. **The memory store.** A `memories` table in the app's SQLite (same database, `init_db` style):
   - Fields: dated, a kind (person, family, likes, health or care, history, preference, other), the text, the source (talk, typed or said "remember…"), and `deleted_at` for soft delete. Nothing is ever hard-deleted.
   - No cap, and nothing is forgotten.
   - Move the existing `memory.json` facts in once, and leave the file in place.
2. **Always sent, kept small (about 120 words at most):**
   - the name and what to call them;
   - anything that changes her safety words, such as veteran status (Veterans Crisis Line);
   - two or three things from the last talk;
   - a one-line note that more is saved and she can look it up.
3. **`recall` tool** for Live and Normal: a search over the memories by words and kind, returning the best few with dates. Plain keyword and synonym matching is fine for now (no cloud embeddings). Run it through the same path as `remember_fact`, after the emergency gate. Tell her in the tools note: when they mention a person, a place or a past talk, recall before answering; never make up a memory.
4. **`remember_fact` writes to the table.** If a new fact updates an old one ("my daughter moved to Durham"), keep both, with the newer one winning.
5. **The resident is in charge:**
   - By voice: "What do you remember about me?" (a short spoken summary) and "forget that" / "forget about my…" (soft delete, confirmed in one line).
   - In Mary's My info panel: "What Mary remembers", a list with a big Remove on each entry (≥64px targets, ≥20px text).
   - The main app's My info gets the same list.
6. **Privacy:** memories never go anywhere except in the packet for one reply, and the recall results she asked for. Backend phase 1 will encrypt the database later, so nothing extra is needed now.

**Keep it working:** her app facts, the name rule, the safety sections word for word, and today's behavior when the table is empty. M4a may make one small fix in `app.js` and `server.py` at the same time, so keep your changes in blocks marked `M9c`.

**Tests:**
- The table and the one-time move.
- The always-sent part stays under its limit.
- `recall` finds things and returns nothing it shouldn't.
- Forget is a soft delete.
- The emergency gate runs before the tools.
- The key never appears.
- `node --check` on every changed script.

**Models:** Opus xhigh for the store, the recall tool and its wiring into Live and Normal; Opus for the My info list; Sonnet for the tests.

**Finish:** Andy has to try it, so commit `WAITING: M9c memory core ready for Andy to try` and stop. The body says, in plain words, what she remembers, how to see and remove it, and what isn't verified.
