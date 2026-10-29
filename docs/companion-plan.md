# Companion plan

Status: direction set 2026-10-24 with Andy. Everything here is open to debate as we learn. [backend-plan.md](backend-plan.md) and [pilot-checklist.md](pilot-checklist.md) still apply, but they need revising for this.

## The idea
A friendly animated companion fills most of the screen. Residents simply talk to her as a friend, and she keeps them company. She's built into the same app, so when something goes wrong, she helps them speak up, starting with the facility.

## Why the change
- **Adoption.** Residents fear retaliation, and a tool for telling on staff scares them. Facilities would fight it too. A companion helps from day one.
- **Loneliness** is a real daily harm, so companionship is the biggest immediate gain.
- **Easier logging.** Residents just talk, and she fills in the details.
- **Funding.** Funders already pay to fight loneliness in older adults.

## Principles
1. **Honest about what she does.** She's never a disguised reporting tool, and the code is public.
2. **On the resident's side.** She runs on their laptop, and the facility doesn't control her.
3. **Asks before writing anything down,** for example: "Sounds like dinner was late again. Want me to note that?" She never logs silently.
4. **Points at systems, not people.** She doesn't name staff by default. Patterns show understaffing.
5. **Facility first, never a gate.** Her default advice is to go to the facility first. A red line means the state and the ombudsman right away. Residents can always go to the state, because that's their legal right.
6. **Never just disappears.** If the cloud or the funding fails, a basic offline mode keeps working, and family can choose to keep her going.
7. **Honest that she's an AI,** gently, whenever she's asked.
8. **Nudges toward people,** like family calls and activities. She doesn't replace them.
9. **Never plays doctor.** In an emergency she says: press the call light, get staff, call 911.

## Character
- **Her name is Mary.** Residents can rename her.
- **One really good default:** female, super friendly and kind. Her animated face fills most of the screen, shows expressions, and her mouth moves when she speaks.
- **Changeable:** residents can change her look, switch to a male companion with a male voice, or create a whole new character if they're able to.
- **Must-haves:** captions of everything she says; adjustable speed and volume; big, high-contrast visuals; works by voice alone.

## How she works (first version)
- **Listening:** speech-to-text on the laptop, using the existing `speech.py`. The resident's voice never leaves the laptop.
- **Waking her:** "Hey Mary", detected on the laptop (for example with openWakeWord), so residents who can't use their hands can start talking. The room isn't recorded all the time.
- **Thinking:** Gemini. Only words go to the cloud. See "Gemini free tier and privacy" below for which tier is used when.
  - Check: Gemini through Google Cloud (Vertex AI) under a BAA, for medical-grade handling.
  - Residents are told plainly that their conversations go to Google.

### Gemini free tier and privacy (decided by Andy; written down 2026-10-29)
- **The issue:** on Gemini's free tier, Google's pricing page lists content as "Used to improve our products". Google may read and use what's sent. On the paid tier it doesn't. Residents' talks can include health details, names and complaints about staff, so they must never go through the free tier.
- **Now, while Andy is the only tester:** use the free tier. Andy made a fresh free-tier key just for this project, and only his own test talks go through it. He knows Google may use them, and he accepts that.
- **Later in testing:** Andy expects to add money to that same key. That moves it to the paid tier (no product-improvement use) and unlocks better models, for example a newer Flash, for speed and quality.
- **Before any other resident uses Mary** (the pilot and beyond), it's paid tier only, or Vertex AI under a BAA if that gets checked and set up. Each resident's own key, or a funded key, must be on a paid plan before setup. Helpers check this during setup.
- **Plain words for residents and consent:** "What you say to Mary is sent to Google's Gemini to work out her answer. We use Google's paid service, where Google doesn't use your words to train or improve its products." This goes into the consent screen and the privacy policy (`docs/backend-plan.md`, `docs/pilot-checklist.md`).
- **In the app:** the audition (M2) and the early tests run on Andy's free key, and nothing here changes the code. Before the pilot, add a setup check that tells the helper whether a key is on the free tier (roadmap M8 or the pilot checklist).
- **Speaking:** the friendliest, least robotic voice the budget allows.
  - Start with a free voice that runs on the laptop, for example Kokoro: open, natural-sounding and private.
  - Test it by ear against paid cloud voices from Google or ElevenLabs.
  - Check speed on a typical resident laptop.
- **Memory:** what she knows about the resident (name, family, likes, routine) stays on the laptop, encrypted.
- **Speak-up skill:** the existing log, formal reports, facility-first emails and state contacts.

## The laptop
- **Where it comes from:** in North Carolina, Medicaid provides refurbished laptops. There's a $65 refurbishing fee, waived if the resident can't pay. Other states: check.
- **Open the lid, type the PIN, see Mary:** a 4-digit Windows PIN, then Mary opens full screen on her own and stays open. A locked-down "Mary only" kiosk needs Windows 11 Pro.
- **A one-click setup tool,** so helpers can prepare a laptop without technical skills.
- **A spec:** the cheapest laptop that runs Mary well, with a good mic, loud enough speakers and a big screen.
- **Later:** Mary runs the computer for them (email, video calls, anything they ask), using a big lab's computer-use AI or our own model.

## Her instructions (the most important piece)
Gemini's instructions decide how she behaves with these residents at all times. They're kept as a versioned file in the repo, and tested against scripted conversations before every change.
- **Personality and tone:** warm, patient and cheerful, and she never argues with someone who is confused.
- **The principles above.**
- **Emergency signs mean get help now:** chest pain, a fall, trouble breathing, stroke signs, autonomic dysreflexia signs for residents with spinal cord injuries, and thoughts of self-harm.
- **When and how to offer to log something,** and the red lines.
- **Example tests:**
  - "I fell this morning."
  - "Are you a real person?"
  - "That aide is so rude to me."
  - "Nobody came for 2 hours." She should offer to note it, without naming the aide.

## Rough monthly cost per resident (check current prices)
- **Conversation:** Gemini Flash, for someone chatting about 2 hours a day, roughly $2 to $8.
- **Voice:** $0 on the laptop. A cloud voice might add about $10 to $20 for a heavy talker, and premium voices more.
- **Pitch:** companionship and a voice for under about $10 a month per resident.

## The pitch
It's the same honest product for everyone, and we never deny what she does. We emphasize what each audience cares about:
- **Loneliness and aging funders:** companionship.
- **Advocacy and justice funders:** residents can finally document care failures and be heard.
- **Facilities (after the pilot):** a partner. Facility first by default, and systems, not people.
- **Funding lead:** CMS Civil Money Penalty reinvestment funds. That's money from fines on nursing homes, which states hand out for projects that help residents. Check NC's process.

## Rollout
- **Pilot:** resident-only, 5 residents, 8 weeks. Measure loneliness before and after with a short, validated scale, alongside the incident data.
- **After the pilot:** pitch facilities as partners, starting with activities departments. We can promise:
  - facility first by default
  - systems, not people
  - red lines defined with the ombudsman partner

  We must never promise that residents won't go to the state.

## Family messages and calls (Andy, 2026-10-25)
Residents say "Mary, message my daughter and tell her this" or "Mary, put a call through to my son", and it all happens from Mary's screen.
- **Contacts:** a short list of family and friends, set up by a helper or family member and kept on the laptop. Each has a name, a relation (daughter, son…), a photo, and a phone or email.
- **Messages:** Mary writes the message and reads it back in a big caption, then sends it only after a clear "Send it". The screen confirms with "Sent to …". Messages go only to people on the list.
- **Calls:** "Calling …", then a simple in-call screen with big "Hang up" and "Louder" buttons. Later, incoming calls from family too.
- **To research before building** (costs and accessibility):
  - Texting: an SMS service (a small per-message cost, plus a number), email, or Windows Phone Link with the resident's own phone (check whether it has any API).
  - Calling: a calling service from the laptop's mic and speaker, or a video-call link family can open.
  - Who pays per-message and per-minute costs.
- **Safety:** an emergency still means the call light, staff or 911 first. Mary can also message a chosen family member during an emergency if the resident asks.
- **Mock-ups:** the message and call screens are on the face canvas (round 2/3 boards, `mockups/mary/round2/`).

## Screen and power (Andy, 2026-10-25)
When the laptop is plugged in, the screen never turns off or goes black.
- After a while with no talk, Mary gently goes to sleep: her sleepy expression, with slow breathing.
- Later, her background softly dims.
- A voice or a tap wakes her.

On battery, she has her sleepy mode, plus the normal Windows screen timeout to save power.

## Games with Mary (Andy, 2026-10-25)
Mary can suggest a game ("Hey, do you want to play a game, or do a word search?"). When the resident says yes, her face turns in 3D: the right side recedes into the screen, so she's angled toward the game on the right while still big and alive. She glances back and forth between the game and the person. Andy chose this over shrinking her into a corner.
- **She helps them play:** she gives hints when asked, makes moves by voice ("put the red seven on the black eight"), cheers them on, and never takes over.
- **Starting games** (not locked in): word search first, since many older people love them. Also tic-tac-toe, solitaire, and later checkers, crosswords, trivia and memory games.
- **Built for ages 65-95:** huge letters and cards, high contrast, tap or voice, no timers or pressure, and gentle wins.
- **Mock-ups first:** a game-mode board showing Mary scooted aside next to a word search, then tic-tac-toe and solitaire.

## Mary and the computer (Andy, 2026-10-25)
The laptop must not be a one-trick pony: many residents in their 80s used computers for years. Mary is the home base, and she helps with the whole computer. "If a computer can do it, we can make it happen." Three levels:
1. **Mary's own skills, in her screen.** She turns aside in 3D, as in game mode, and the content fills the right side.
   - **Pictures:** "Show me a picture of a bird." Photos come from free libraries with no key (Wikimedia Commons, or Openverse with its mature-content filter on), with a safety filter on every search and credit lines where needed. She talks about each photo and takes "next one" or "bigger". Family photos too: "Show me my grandkids", from the family messages feature.
   - **Also:** games, music ("play Frank Sinatra"), weather, the news read aloud, reminders, and family messages and calls.
   - Note: Bing's image API is retired, and Google's is closed to new users.
2. **Mary opens things for you:** "Open YouTube and play The Andy Griffith Show", "open my email", "open Facebook". The app or site opens normally, and Mary shrinks to a floating button that's always on top ("Mary, come back"). Start from the floating mic button parked on `wip/report-to-state`.
3. **Mary operates the computer for you.** She clicks, types and reads the screen with a computer-use AI model. **Only after the pilot**, and only if residents ask for it. Level 2's pilot data decides. Build levels 1-2 so level 3 can be added later without rework.
   - Firm rules: she never types passwords or card numbers, and she always reads back before she sends or buys anything.
   - She also warns about scams ("That pop-up looks like a scam; don't call that number").

**Two setup modes**, picked by the helper:
- "Mary only": she's the whole screen, for dementia or residents new to computers. A true lockdown needs Windows 11 Pro; on Home it's a soft lock.
- "Mary plus the computer": Mary opens with the lid and is home base, with the full laptop available.

## Future (with funding)
- Government or foundation money to train or fine-tune an AI for this cause, for example an open-weight model fine-tuned on conversations residents consented to share.

## Open questions
- Whose AI account: one project account through our server (we pay from grants, and it's simpler), or each resident's own (they pay, and it's more private)?
- The red lines: define them with the ombudsman partner.
- The voice: decide by listening.
- How family consent works for residents with dementia.

## Next steps
1. ~~Write her first instructions and the test conversations.~~ **Done 2026-10-25** (ed6ec4e, 5ecb2d2): `mary/instructions.md` (v1), 13 cases in `tests/mary_conversations.json`, `mary.py` (streamed Gemini reply, memory in `<data>\mary\memory.json`, offline emergency line first, offer-to-write via `guess_incident()`, never logs), speed test `tools/mary_speed.py`.
   - Speed on Andy's laptop (AMD Ryzen, 8 threads): speech model loads in about 1 s. Speech-to-text has a median of 1.1 s and a p90 of 5.5 s, with 99% of words right. The slow turns come from beam search with the vocabulary prompt in `speech.py`. **Fixed 2026-10-25:** `speech.py` now uses greedy decoding (`beam_size=1`) and keeps the prompt. Over three runs, the median is 0.95-1.64 s and the p90 is 1.85-2.71 s, with words still 99% right. The spread is likely other load on the laptop.
   - Gemini time to first words isn't measured yet, because no key is saved. Run `python tools/mary_speed.py` with `GEMINI_API_KEY` set. The same run checks her live behavior against the cases.
   - Not yet: memory encryption (backend phase 1), and bundling `mary/` in the installer.
2. Prototype the face, the talk loop and the wake word in the desktop app, with Andy as the first user.
3. Family messages and calls (section above): research the options and costs, then build from the approved mock-ups.
4. Games with Mary (section above): mock-ups, then build, starting with word search.
5. Mary and the computer (section above): level 1 skills (pictures first), then level 2 (opening apps and sites, the floating Mary button) before the pilot. Level 3 comes after the pilot, only if residents ask.
6. Set up lid-to-Mary with the two setup modes, the helper setup tool and a laptop spec.
7. Before the pilot: review and merge the parked speak-up code (branch `wip/report-to-state`). It becomes her speak-up skill.
8. Revise the pilot checklist and the backend plan for the companion.
