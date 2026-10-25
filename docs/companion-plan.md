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
- **Thinking:** Gemini, paid API only. Google can use free-tier conversations to improve its products, so the free tier is out. Only words go to the cloud.
  - Check: Gemini through Google Cloud (Vertex AI) under a BAA, for medical-grade handling.
  - Residents are told plainly that their conversations go to Google.
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
3. Set up lid-to-Mary, the helper setup tool and a laptop spec.
4. Before the pilot: review and merge the parked speak-up code (branch `wip/report-to-state`). It becomes her speak-up skill.
5. Revise the pilot checklist and the backend plan for the companion.
