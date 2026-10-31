# Mary skills: the plug-in design (M13)

Status: **approved by Andy 2026-10-29** (first skill `voice_comfort`; in-repo reviewed skills only; switches in My info and by voice), with changes A (internet only through the core) and B (voice switching both ways, plus helper locks). Roadmap item M13 in `docs/mary-roadmap.md`.

## In plain words, for Andy

**What a skill is.** A skill is one thing Mary can do, kept in its own folder: the crossword, pictures of birds, the weather, writing down a care problem, making her voice slower or louder. Mary herself (her face, her voice, the way she talks and listens, her safety rules) is the small core that rarely changes. Everything else plugs into her.

**What adding one looks like.** Someone makes a folder under `skills/` with three things in it:
1. **A card** that says what the skill is called, what it shows, and what Mary can do with it, in plain sentences. For example: "Give an easier hint for one clue."
2. **The skill's own code**, which does the work.
3. **Its screen**, if it has one. It shows up in Mary's menu by itself.

Nobody touches Mary's brain to add it.

**How Mary learns it by herself.** When the app starts, it reads every skill's card and hands Gemini the list: "here's what you can do, and here's what's on the screen right now." That works the same way in all three talk modes. So when a resident says "this clue is too hard," Mary already knows the crossword has an "easier hint" action, and uses it. If there's no internet (Offline mode), simple skills still work from short phrases on the card, like "louder" or "slow down".

**What happens if one breaks.** Every call into a skill goes through a guard:
- If the skill crashes or hangs, the guard catches it and switches that skill off.
- Mary says "That's not working right now."
- Everything else keeps going: her talk, her safety checks, the other skills.

Before a skill is loaded at all, the app checks its card and code with automatic tests, and a skill that fails isn't loaded. A resident can switch any skill on or off just by asking Mary ("turn the crossword back on"), or in My info. Only a skill the helper **locked** during setup needs My info to change. Her emergency and safety rules aren't skills, so they can never be switched off or broken by one.

**The internet only goes through Mary's core.** A skill can't reach the internet by itself. It asks the core, and the core only lets it visit the websites listed on its card. Every visit has a time limit and a size limit, and is written in a log.

*Approved by Andy 2026-10-29, with two changes: internet only through the core (A) and voice switching in both directions (B).*

**Why it matters beyond the nursing home.** It's a small, safe way for anyone to teach an AI companion a new trick, and to have it understand that trick on its own. The card follows the same shape as MCP tools (a standard way AIs are offered tools), so a skill made for Mary could later be offered to other AIs too.

## Technical design

### 1. Where things happen today (code map, 2026-10-29)
| Mode | Instructions and tools go to Gemini | Where the page acts |
|---|---|---|
| **Normal** (laptop speech-to-text → Gemini → voice) | `mary._body()` (`mary.py:471`) builds `systemInstruction` + `contents`, with **no `tools`**. `mary._gemini_stream()` (`mary.py:417`) yields only `text` parts. Called by `server.mary_talk()` (`server.py:330`) and `Handler._mary_stream()` (`server.py:678`). | `web/mary/app.js`: `streamReply()` reads NDJSON lines (`{mood}`, `{text}`, the final `{done…}`), and `finishReply()` (`app.js:785`) acts on `emergency` / `logged`. Menu actions are the `data-act` switch in `onMenuClick()` (`app.js:935`). Screens use `registerScreen(name, {enter, leave})` (`app.js:510`). |
| **Live** (native audio, page ↔ Google directly) | Only in the audition so far. `voices.live_token()` (`voices.py:601`) locks `systemInstruction` and the voice into `bidiGenerateContentSetup`, with **no `tools`**. The page's `setup` message only names the model (`web/mary/live.js:605`). | `web/mary/live.js`: `handleText()` / `onServerContent()` (`live.js:349-416`). There's no `toolCall` handling yet. Mary's own Live session comes with M4/M5. |
| **Offline** (no Gemini) | None. `mary.reply()` without a key runs only the word-list brain (`is_emergency`, `lapse_offer`, `is_yes`), then says `OFFLINE_TEXT`. | The same as Normal. |

Today the only "action" is the incident offer: the text tags `[mood:]`, `[remember:]` and `[name:]`, plus `write=mary_write_incident`. Those stay core.

### 2. Folder layout
```
skills/
  voice_comfort/              # folder name = skill name: [a-z][a-z0-9_]{1,30}
    manifest.json             # the card (required)
    skill.py                  # server half: action handlers, view() (required if it has actions)
    screen.js                 # page half (optional): its screen and effects
    screen.css                # optional
    tests/test_voice_comfort.py   # its own tests (optional; the contract tests always run)
skills_core.py                # the loader, guard, store, Gemini adapters (core)
web/mary/skills.js            # the page half of the core: loads screen.js files, applies effects
tests/test_skills_contract.py # runs the contract on every folder in skills/
```

### 3. The manifest (`manifest.json`, contract 1)
```json
{
  "contract": 1,
  "name": "crossword",
  "version": "0.1.0",
  "title": "Crossword",
  "summary": "A crossword puzzle the resident and Mary solve together.",
  "instructions": "Offer it when they want a puzzle. Make hints easier when asked. Never just give answers unless asked.",
  "screen": {"menu_label": "Crossword", "menu_icon": "grid", "full_screen": true},
  "sees": true,
  "actions": [
    {
      "name": "set_hint",
      "description": "Rewrite one clue's hint on screen, for example to make it easier.",
      "inputSchema": {"type": "object",
                      "properties": {"clue": {"type": "string", "description": "Clue id like 3-down"},
                                     "text": {"type": "string", "maxLength": 120}},
                      "required": ["clue", "text"]},
      "annotations": {"readOnlyHint": false, "destructiveHint": false},
      "offline_phrases": []
    }
  ],
  "storage": true,
  "needs": {"internet_hosts": [], "mic": false, "modes": ["live", "normal", "offline"]},
  "offline": "works",
  "default_on": true
}
```
- **`instructions`**: at most 400 characters. It's added to her system text under "Things you can do".
- **`sees`**: true means `skill.py` has `view(state) -> str`, the live "what Mary sees" text (M12 rule), at most 600 characters.
- **`actions`**: MCP tool shape (`name`, `description`, `inputSchema`, `annotations`), in a JSON Schema subset that Gemini accepts: `object`, `string`, `integer`, `number`, `boolean`, `array`, plus `enum`, `required`, `description`, `maxLength`, `minimum` and `maximum`. Nothing else, and no `$ref`.
- **`offline_phrases`**: short trigger phrases for Offline mode, for example `["louder", "speak up", "turn it up"]`. Matched only for actions with no required inputs.
- **`offline`**: `"works"` or `"needs_internet"`. With `needs_internet`, the core makes Mary say "I need the internet for that" instead of calling the skill.
- **`storage`**: whether it gets a private store.
- **`vision`** (optional, M4a): true lets the skill ask Gemini about a picture with `ctx.look(image_bytes, mime, question)`. The host makes the call, so the skill never holds the key. It answers `""` without this field, or when anything goes wrong.
- **`memory`** (optional, M7a): true lets the skill read her memory with `ctx.recall(words, limit=6)`, which returns plain fact texts. It's read-only, and it answers `[]` without this field, or when anything goes wrong. A skill must keep those facts out of its responses, `view()` and logs. Word search uses it only to choose a theme.
- **`needs.internet_hosts`** (change A): the only hosts `ctx.fetch` may reach, as exact names or one leading wildcard label (`"*.wikipedia.org"`, `"upload.wikimedia.org"`). An empty list means no internet at all.

**`ctx.fetch(url, method="GET", params=None, headers=None, max_bytes=2_000_000, timeout=6)`** (change A) is the only way a skill reaches the internet:
- `https` only. The host must match `internet_hosts`, and the check runs again after every redirect.
- It always has a timeout (at most 8 s) and a size cap (at most 5 MB); a response over the cap is an error, not a cut-off.
- No request body: it's GET with query `params`. The core adds nothing of the resident's (no memory, no transcript, no key), so resident text goes out only when the action's own arguments carry it.
- Every fetch is logged in `skills.log` as the skill, the host, the status and the byte count. It never logs the path, the query or the response.
- It returns `{status, content_type, body: bytes}` and raises `SkillFetchError` on anything refused or failed. Offline mode refuses it at once.

### 4. The core loader (`skills_core.py`)
1. At start, scan `skills/*/manifest.json`. For each one: validate the manifest (the contract checks in section 8 that can run fast), import `skill.py` as module `skills.<name>.skill`, and check that every declared action has a handler `def <action>(ctx, **args)`. Any failure means the skill isn't loaded, with a line in `DATA\skills.log`.
2. Keep a registry: `{name: Skill(manifest, module, state, failures, on)}`. `on` = per-resident setting (section 7) and loaded and not tripped.
3. **The contract version:** the core has `SUPPORTED = {1}` plus an adapter per older version. A later contract 2 adds fields, and contract-1 skills keep loading through `adapt_v1()`. A manifest asking for an unknown, newer contract isn't loaded.
4. **Gemini declarations,** generated from the registry, never written by hand:
   - Function name: `<skill>__<action>` (letters, digits and underscores, at most 64 characters; checked by the contract).
   - `parameters` = `inputSchema`, minus the MCP-only keys.
   - Normal: `"tools": [{"functionDeclarations": [...]}]` added in `_body()`.
   - Live: the same list inside `bidiGenerateContentSetup.tools`, so it's locked into the one-use token like the instructions are.
5. **Instruction text:** `skills_core.instruction_text()` returns
   ```
   Things you can do (use these tools when they fit; never mention tool names):
   - Crossword: <instructions>
   What's on the screen now (Crossword): <view()>
   ```
   Only enabled skills are listed, and only the skill now on screen adds "What's on the screen now". It's appended to `system_text()` by one marked hook line.

### 5. How an action travels
The **server is each skill's brain and the page is its face.** All of a skill's state lives on the server, so both modes use the same handler, and nothing needs the page to answer back mid-reply.

`skills_core.call(fn_name, args) -> {"response": {...}, "effects": [...], "say": str|None}`:
- It checks that the skill exists, is on, and isn't `needs_internet` while offline. Then it validates `args` against `inputSchema` (wrong args become `{"error": "bad_input", ...}` for Gemini, not a crash).
- It runs the handler in the guard (section 6). The handler gets `ctx` (`ctx.store`, `ctx.state`, `ctx.effect(kind, data)`, `ctx.settings_get/put` for the keys its manifest declares) and returns a small JSON-able result.
- **Effects** are what the page must do, for example `{"skill":"crossword","kind":"hint","data":{...}}` or core effects like `{"kind":"show_screen","data":{"screen":"crossword"}}`.

**Normal mode:**
1. `_gemini_stream()` also yields `functionCall` parts.
2. `reply()` runs `skills_core.call()` for each one.
3. The effects are streamed to the page as NDJSON lines `{"effect": {...}}`.
4. The call goes back to Gemini as a `functionResponse` part in a second request, for her spoken follow-up.
5. At most 3 tool rounds per turn. **Gemini 3 note:** every `functionCall` part carries a `thoughtSignature` that must be sent back unchanged in the next request's history, or the API refuses it.

**Live mode:**
1. Google sends `toolCall.functionCalls[]` to the page.
2. `live.js` posts each one to `POST /api/mary/skills/call` (`X-Tracker: 1`) and gets `{response, effects}`.
3. The page applies the effects and sends `toolResponse.functionResponses[{id, name, response}]` back on the socket.
4. When a screen's view changes (the resident filled a square), the page sends `clientContent` with `turnComplete: false` and the text "What's on the screen now: …". That keeps her current without making her speak.

**Offline mode:**
1. Before `OFFLINE_TEXT`, `reply()` asks `skills_core.offline_match(text)`, which checks the `offline_phrases` of enabled, `offline: works` skills.
2. A match runs the action like any other and says the skill's `say` text (handlers return a short `say` line for this; Gemini words it in the other modes). The handler can read the whole line in `ctx.heard` (M7a; empty in the other modes), so "I found barn" can reach an action with no required inputs. A response with `"not_for_me": true` means the phrase wasn't meant for this skill (no puzzle is up), and her normal offline line runs instead.
3. "Turn <title> on/off" (and "back on", "stop the <title>") is matched offline too, against each skill's `title`, and runs `set_skill`. Then the voice switch works with no internet.

**The page:** `web/mary/skills.js` gets `GET /api/mary/skills` (enabled skills, menu entries and page script URLs) and loads each `screen.js`, which calls `MarySkills.register(name, {enter, leave, effect(kind, data)})`. It plugs into the existing `registerScreen()`, and adds menu buttons from `screen.menu_label`. Resident moves on a skill screen go to `POST /api/mary/skills/<name>/event`, which runs `skill.py`'s `on_event(ctx, event)` in the guard.

**Safety first, always:** the core's emergency check (`is_emergency`) runs on every resident line **before** any skill or tool. A skill can't see or answer an emergency line, and the emergency screen hides skill screens.

### 6. Error boundaries
- **Every call into skill code** (load, handler, `view`, `on_event`) runs through `guard()`:
  - It runs on a worker thread with a time limit (2 s default; up to 8 s if the manifest declares `"slow": true`, for example fetching a picture).
  - Any exception or timeout records a failure in `skills.log`, with the skill, the action, the error type and a short message. It never holds resident text or keys.
  - It returns `{"error": "not_working"}`.
- **The trip rule:** a crash on load, or 2 failures within 10 minutes, switches the skill off until the app restarts. Its tools are dropped from the next Gemini request and the next Live session.
- **What Mary says:** her instructions say: "If a tool answers `not_working`, say kindly that that's not working right now, and carry on." Offline, the core says it directly ("That's not working right now."). The page also shows nothing broken: on `not_working` the page leaves the skill's screen for her everyday face.
- **The page half:** every `screen.js` call is wrapped in try/catch. A throw posts `POST /api/mary/skills/<name>/broken`, which counts as a failure.
- **The honest limit:** skills run in the same Python process, so this isn't a security sandbox. The guard catches bugs, not hostile code. That's why only skills shipped in this repo and reviewed are loaded (see Risks).

### 7. Storage, switches and settings
- **Storage:** a new SQLite table `skill_data(skill TEXT, key TEXT, value TEXT, updated_at TEXT, PRIMARY KEY(skill, key))`.
  - `ctx.store.get/put/delete/keys` is bound to its own skill name by the core. There's no API that takes another skill's name, and the value is JSON, at most 64 KB per key.
  - Skills never get a database connection, the incident tables or file paths. If one needs files, `ctx.files` is a folder `DATA\skills\<name>\` with paths that are checked to stay inside it.
- **Settings it may change:** only keys listed in the manifest under `"settings": ["voice_rate", "voice_volume"]`, through `ctx.settings_put`. Anything else is refused.
- **Per-resident on/off (change B): two lists in settings.**
  - **`skills_off`**: the resident's own choice. It changes in both directions by voice ("turn the crossword back on", "stop the crossword") through the core tool `set_skill(name, on)`, or with the big switch per skill in My info ("Things Mary can do"). Residents who can't use their hands need the voice way.
  - **`skills_locked`**: set by the helper during setup, as `{name: "off"|"on"}`. A locked skill can't be changed by voice: `set_skill` answers `{"error": "locked"}` and Mary says "the person who set up your laptop chose that." Only My info's helper section (or setup) changes it. This fits the two setup modes in `docs/companion-plan.md`: "Mary only" locks the computer skills off, and "Mary plus the computer" leaves them free.
  - **Enabled** = loaded, not tripped, not locked off, and (locked on or not in `skills_off`). `set_skill` is a core tool, always present, and its `name` enum lists every loaded skill. Core features (talk, emergency, incident safety) aren't in either list.

### 8. Contract tests (`tests/test_skills_contract.py`, run for every folder in `skills/`)
1. `manifest.json` parses and has every required field. `name` = folder name, and `contract` is supported.
2. Every function name is `<skill>__<action>`, at most 64 characters, unique across all skills, and only uses the allowed characters.
3. Every `inputSchema` uses only the Gemini-safe subset, and every property has a `description`.
4. The text size limits: `instructions` at most 400 characters and descriptions at most 200. The total instruction text of all shipped skills stays under a budget (4,000 characters) so her prompt doesn't swell.
5. `skill.py` imports cleanly, with a handler for every action, and `view` when `sees`.
6. **Static safety:** `skill.py` doesn't import `server`, `sqlite3`, `mary`, `assist`, `subprocess`, `ctypes`, `multiprocessing`, `importlib`, or anything for the network (`urllib`, `http`, `requests`, `httpx`, `aiohttp`, `socket`, `ssl`, `ftplib`, `smtplib`, `websocket(s)`; change A). It doesn't call `open`, `exec`, `eval` or `__import__`. Checked from its source with `ast`; the loader runs the same check.
7. **A call smoke test:** each action is called with arguments generated from its schema (the minimal valid ones) against a scratch store. The result is JSON-able, under 4 KB, and `view()` returns a string under 600 characters. It must work with no internet: `ctx.fetch` is replaced by one that refuses, and a `needs_internet` skill must fail politely, not crash. Every `internet_hosts` entry is a valid host pattern.
8. **Effects:** every effect is a known core kind or `skill == name`.
9. **Offline phrases:** only on actions with no required inputs, and none clash across skills or with the emergency or yes/no word lists.
10. **The page half:** `screen.js` exists if `screen` is set. A tiny Node check, if Node is present, confirms it parses and calls `MarySkills.register` with its own name. Otherwise it's skipped with a note.

The loader runs checks 1-5 and 9 at start too, so a broken folder never loads even outside the test suite.

### 9. MCP shape: recommendation
**Shape actions exactly like MCP tools (`name`, `description`, `inputSchema`, `annotations`), but don't run skills through an MCP server now.**
- **Why:** the shape costs nothing, and it's the standard others know. Turning it into Gemini declarations is a few lines. Later, `mcp_server.py` (which already speaks MCP) or a small resident-safe MCP endpoint could list skills for other AIs.
- **Why not a real MCP server per skill:** that means extra processes on a cheap laptop, more to break, and nothing a resident gains today.

### 10. The first skill to port: `voice_comfort`
"Slower", "faster", "quieter", "louder", and switching between Mary and Sam. These are today's menu actions in `app.js:898-946`.
- **Why it's first:**
  - It exercises every part of the contract: actions in all three modes (with offline phrases), settings writes, page effects, menu entries and a tiny view ("Speaking speed 1.0, volume 0.9, companion Mary").
  - It's small and easy to verify, and it fixes a real gap: today she can't do "speak slower" by voice.
- **Why not incident saving yet:** it's the most important path in the app, and it's woven into the emergency and yes/no logic in `mary.reply()`. It should move to a skill only after the core is proven, as the second port, with its own careful review.
- **Not the voice picker:** the voice audition files (`voices.py`, `web/mary/voices*`) are being changed by another worker.
- A tiny example skill, `coin_flip` (a screen, storage and `view`), goes in `docs/how-to-make-a-skill.md`, and in the contract tests as a fixture.

### 11. Hooks in existing files (small, marked `# --- skills hook (M13) ---`)
- `mary.py`:
  - `_body()` adds `tools` and the instruction text.
  - `_gemini_stream()` yields `functionCall` parts.
  - `reply()` gets the tool loop, at most 3 rounds, and the offline match before `OFFLINE_TEXT`.
  - The result gains `effects`.
- `server.py`:
  - The routes `GET /api/mary/skills`, `POST /api/mary/skills/call`, `POST /api/mary/skills/<name>/event|broken` and `GET /skills/<name>/screen.js|.css`.
  - `effects` passed through `mary_talk()` and `_mary_stream()`.
  - The `skill_data` table in `init_db`.
- `web/mary/app.js`: `handleLine()` passes `{effect}` lines to `MarySkills.apply()`. The menu gets a slot for skill buttons, and the `voice_comfort` port removes its own cases from `onMenuClick()`.
- `voices.py` `live_token()`: one line, `setup["tools"] = skills_core.gemini_tools()`, plus the instruction text. **This file belongs to the voice audition worker on the main account,** so the hub coordinates this hook (or it lands with M4's real Live session). Stage 2 proves Live with a mocked socket against `live.js`-style handling in `web/mary/skills.js`, without editing `voices.py`.
- `packaging/build.py`: bundle `skills/`.

### 12. Risks
- **Prompt growth:** every skill adds text and tools. That's handled by the size limits in the contract, and only the on-screen skill sends its view.
- **Too many tools confuse the model:** stay under about 20 functions in v1. Later, send only the on-screen skill's detailed actions, plus one `open_skill(name)` for the rest.
- **Gemini 3 `thoughtSignature`:** forgetting to send it back breaks multi-step calls. A mocked test checks it's sent back.
- **Live session setup is locked in the token:** switching a skill on or off takes effect at the next Live session. That's fine for residents, and it's written in the how-to.
- **Not a sandbox:** reviewed, in-repo skills only, for now.
- **A hung handler thread can't be killed in Python:** the guard abandons it and trips the skill. A skill doing network work must use timeouts (a contract smoke test checks that calls return).

### 13. Out of scope for M13
- Pictures (M12) and games (M7) themselves. They're built as skills right after.
- Third-party or downloaded skills, a skill store, and signing.
- Running skills in a separate process.
- Mary's real Live session (M4/M5).
- Moving incident saving (second port, later).
- Google Search grounding (a core switch, not a skill).
