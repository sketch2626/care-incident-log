# M15c design: how the yes, the Undo and the send fit together

Written by the M15c worker for its helpers. `docs/handoff/M15c.md` is the brief; this is the shape every piece must follow.

## The rule
Gemini can never start a send. Only three things move a send forward, and all three are checked in core code a skill can't change:
1. the resident's own words, from the two routes that carry them (`/api/mary/talk` through `mary.reply`, and `/api/mary/heard` for Live's transcript);
2. a tap on the page (`/api/mary/skills/messages/event`);
3. the clock.

A tool call from Gemini can show the look (D2) and nothing more.

## `send_gate.py` (new, core, stdlib only)
`SendGate(mailer, clock=time.monotonic)` holds one look at a time, in memory only, under a lock. A restart forgets it, which is safe. It runs no timers and no threads: **nothing can send unless a live page asks at the end of the count.** If the window dies mid-count, nothing goes.

States: none, `look`, `counting`, `sending`. Constants: `COUNT_S = 5.0`, `COUNT_STALE_S = 30.0`, `LOOK_TTL_S = 600`, `MISSES_FOR_TAP = 2`, `MAIL_PICTURES_MAX = 600_000` (bytes in all, from the M15d note).

| Method | Who calls it | What it does |
|---|---|---|
| `arm(skill, person, to, subject, body, pictures)` → look id or raises `GateRefused(reason)` | `ctx.arm_send` | Freezes the exact content (`mail_core._freeze`). Refuses `asks_for(...)` content, more than `MAIL_PICTURES_MAX`, or a bad message. Replaces any older look. |
| `disarm(skill)` | `ctx.disarm_send` | Content changed or the screen left. No look. |
| `shown(look_id)` | `ctx.send_shown`, page only | The page really drew D2 with this look. |
| `her_words(text)` | core | Her finished turn. Sets `line_said` when it holds "five second(s)" or "5 second(s)", plus the person's first name or "email". After `say_line` was issued, "second" alone is enough, so a transcript quirk can't trap them. |
| `heard(text, garbled=False)` → `{"action": ...}` | core | See below. |
| `emergency()` | core | During `counting`, the same as `undo`. A look stays. |
| `tap()` → bool | `ctx.send_tap`, page only | True and starts the count only when `tap_open`. |
| `undo()` → bool | `ctx.send_undo`, page only, and `heard` | `counting` back to `look`. Line stays said; misses and tap go back to 0 and closed. |
| `take(skill, look_id)` → frozen content or `None` | `ctx.send_now`, page only | Atomically `counting` to `sending`, only when the look id and skill match, `now >= count_from + COUNT_S`, `now <= count_from + COUNT_STALE_S` and `asks_for` is still clear. The look is then used up, whatever the result. |

`heard` works like this. Any failed check returns `{"action": None}`.
- **`counting`:** if `STOP_WORDS` is in the words (stop, undo, wait, no, don't, cancel, hold, hang on, never mind, oops, not), call `undo` and return `stopped`. Anything else returns `quiet` (the brain stays out of it).
- **`look`, shown, plain send, line not said:** return `say_line`, with the scripted line from `line_for(person)`, and set `scripted=True`.
- **`look`, shown, plain send, line said:** `count_from = now`, state `counting`, return `count`.
- **`look`, shown, otherwise:** a miss is `garbled`, or at most 3 words that aren't all acknowledgement or decline words. The second miss sets `tap_open` and returns `tap`. "Okay", "sounds good", "yes" and "no" are made out fine, so they're neither a yes nor a miss.
- **Look older than `LOOK_TTL_S`:** drop it first.

**`is_plain_send(text, person)`.** Lower-case, with commas and full stops treated as clause breaks. Refuse the whole line on any negative or delay anywhere (don't, do not, not, never, no, wait, hold, later, tomorrow, maybe, should, if, when, did, why, whether, instead). More than 12 words is no. The **last clause** must fully match: optional fillers (mary, sam, please, now, okay, ok, yes, yeah, alright, go ahead and, just, you can, can you, could you, would you, will you, then, and) around `send (it|that|this|the card|the message|my card|my message)` with optional `now`, `off`, `please`, `on its way`, `to <the person's name or first name>`. So "now send it", "okay, send it", "that looks good. send it", "go ahead and send it" and "send it to Mark" count. "Send it to Tyler" with Mark on the envelope, "okay", "sounds good", "should I send it?" and "send it tomorrow" don't.

**`asks_for(text)`** → `"money"`, `"password"`, `"ssn"` or `None`. Narrow, so that "thank you for the money you sent at Christmas" passes:
- password, passcode, PIN number, "log in", login;
- social security, SSN, nine digits as `ddd-dd-dddd` or `ddddddddd`;
- bank account, account number, routing number, credit or debit card number;
- wire, Western Union, MoneyGram, money order, gift card(s), Zelle, Venmo, Cash App, PayPal, bitcoin, crypto;
- send/give/lend/loan/transfer/mail (me/you/him/her/them/us) (some/the) money or cash, or a `$` amount.

## `skills_core.py`
`host.gate = None`, set by the app. `host.mail_ready = None`, set by the app (`lambda: MAIL.status()["connected"]`). With no gate, sending says email isn't set up.

`SkillContext` gets `from_page = False`. `SkillHost.on_event` sets it True; nothing else does. New methods, all refused unless the card has `needs.send_mail`:
- `arm_send(person, to, subject, body, pictures)`, `disarm_send()`, `send_state()` (`{"state", "line_said", "tap_open", "look"}`, no address), `mail_ready()`.
- Page only (`from_page` True, else False or `None`): `send_shown(look)`, `send_tap()`, `send_undo()`, `send_now(look)`.
- `send_now`: `gate.take`, then `mailer.mint_ticket` here in core, then `self.send_mail(ticket, ...)` as its last step, with the stored content. **The skill never holds a ticket.** A ticket is minted per try, only after the count.

`host.resident_said(text, garbled=False)`, `host.her_words(text)`, `host.send_emergency()` wrap the gate. `resident_said` returns `None`, or `{"action", "say", "effects", "skip_brain"}`, after running the skill's module function `on_gate(ctx, action)` in the guard. `skip_brain` is True for `count`, `stopped`, `quiet`, `say_line` and `tap`. The core's `mailer` object must allow `mint_ticket`: pass `gate = SendGate(MAIL)` and leave `host.mailer` as is. Add `_host` and `gate` to `FORBIDDEN_NAMES` if the checker covers attribute names, and keep every shipped skill passing.

`host.forget_reach(about, own_name=False)` → addresses and texts removed; `host.forget_count(about)` → how many contacts match. Each runs a skill's optional module functions `on_forget(ctx, about, own_name)` → `{"addresses": [...], "texts": [...]}` and `forget_matches(ctx, about)` → int, in the guard, and then calls `gate.disarm` for any skill that removed something, and `mailer.scrub_log(addresses)`.

## `mail_core.py`
- New code `unsure`, message "I'm not sure that went." `_smtp_send` tracks when the message starts going up (`send_message` begins). Any failure from there on, other than a clear refusal reply from the server (`SMTPResponseException`, `SMTPRecipientsRefused`, `SMTPDataError`, `SMTPSenderRefused`), is `unsure`, never `offline`. Nobody retries by themselves.
- `scrub_log(addresses=None)`: under `_log_lock`, atomically rewrites `mail.log`, blanking `"to"` on lines that match case-insensitively (`None` blanks every line). Never raises. No log file is fine.
- Fix the docstring lines that say nothing mints yet.

## `mary.py` and `server.py`
- In `reply`, right after `kind = is_emergency(text)`: if `kind`, `skills.send_emergency()`; else `gated = skills.resident_said(text)`. When `gated["skip_brain"]`, add its effects, `emit` its `say`, and skip Gemini and the offer and forget logic the way the `confirmed` path skips them. The turn is saved to history as usual, so her brain knows (one mind, one voice). At the end of `reply`, `skills.her_words(spoken)` when she spoke. `skills` can be `None`, and fakes in old tests may lack these methods, so guard it with one small helper.
- `/api/mary/heard`: on emergency call `send_emergency()`. Otherwise `resident_said(text, garbled=mary.not_english(text))`, **including the garbled early return**. Add `"send": {"say", "effects", "action"}` to the JSON when not `None`.
- `/api/mary/live/said` and the route behind the page's `rememberSaid`: `her_words(text)`.
- `skill_host()`: set `host.gate = send_gate.SendGate(MAIL)` and `host.mail_ready`. Set the forget reach (below).

## Forget
`memory_core.FORGET_REACH = None`, a module-level object the server sets, with `count(about)` and `forget(about, own_name=False)`. Tests set a fake or the real host.
- `MemoryStore.others(about)`: the reach's count, 0 with none or on any error.
- `MemoryStore.forget(about)`: after its own deletes, when `about` is non-empty, adds the reach's texts to what it returns (addresses included, so `memory.scrub` drops them from talk history; they never go back to Gemini). `is_everything(about)` passes through, and clears all contacts and every `to` in `mail.log`.
- `MemoryStore.forget_name(name)`: the same with `own_name=True`: only a contact whose full name is exactly that name.
- `mary.memory_tool` and `offline_memory`: use `matching` count plus `others`, so "Forget Mark" with no saved memory still asks and works. The yes-first rule stays.

## The `messages` skill
**Contacts:** in `ctx.store`, one key per person, `contact-<slug>`, plus `contacts` (the list of slugs). Fields: `name`, `relationship`, `email`, `facebook`, `phone`, `asked` (the keep question was asked), `no_keep`. Check `SkillStore` size limits. Addresses never appear in a tool `response`, in `view`, or in a `say`. They go in page effects only. Exception: an address the resident just spoke is spelled back in `give_address`'s response, because the words came through Gemini already. A typed address never goes to Gemini.

Find a contact by exact name, first name or relationship, without case. Two hits: she asks aloud, with names only.

**Actions:**
- `send_it` (`offline_phrases` stays) in order:
  1. Nothing up: `not_for_me` when heard, else "Nothing's ready to send yet."
  2. `asks_for` on the words: pause, `paused: true`, say plainly: "This asks for money. I won't send that. If someone's asked you for it, talk it over with someone you trust first." (with the right word). Offer nothing else.
  3. `ctx.mail_ready()` false: straight to print: "Your email isn't set up, so this one can go by printing. Want it printed?"
  4. No address: `need_address: true`, show the address screen, "What's Mark's email address? You can say it, or a helper can type it."
  5. Already `counting`: `{"counting": true}`, no say.
  6. Look armed: the same line again only if it isn't `line_said`.
  7. Card without a current mail picture: `draft["look_wanted"] = True`, effect `make_mail`, "One moment."
  8. Otherwise arm, effect `look`, say `line_for(person)`.
- `give_address(address, person?)`: normalizes speech ("mark dot hollis at gmail dot com", capital and spacing fixes). Bad: asks again. Good: holds it in `ctx.state["address_wait"]`, shows it big, and returns `spelled` with "Read it letter by letter, then ask if that's right."
- `address_right(right)`: yes: on to step 7 or 8. No: clears, asks again.
- `keep_address(keep)`: the once-only answer, from `ctx.state["just_sent"]`, then the print offer.
- `save_contact(name, relationship?, facebook?, phone?)`, `find_contact(name)` → `{known, relationship, has_email}`.

**The line:** "When you say send, it goes to Mark's email. You'll have five seconds to stop it." A plain message puts "Here's what I've got." first (board G). It's core's `line_for`, so the two can't drift.

**`on_gate(ctx, action)`:**
- `count`: effect `count`, say "Going to Mark's email."
- `say_line`: the line.
- `tap`: effect `tap`, say "I didn't catch that. Say it again, or tap here."
- `stopped`: effect `look`, say "Stopped. It hasn't gone."
- `quiet`: nothing.

**`on_event`** (split the `@_locked` so `count_done` doesn't hold `_LOCK` during the 12 s send): `look_up` → `send_shown`. `tap_send` → `send_tap`, then the same as `count`. `undo` → `send_undo`, then `stopped`. `address` (typed) → like `give_address` without the spelling, straight on, with nothing about it in `say`. `left` → `disarm_send`. `picture_failed` → "The picture wouldn't make. I can send the words as a plain message, or print it." `count_done` → `send_now`:
- `ok`: effect `sent` (name, time as on board F). Save `last_sent` for `view`. If no address was saved and not `asked`/`no_keep`: set `asked`, `ctx.state["just_sent"]`, say "Sent to Mark. Keep Mark's address for next time?" Otherwise "Sent to Mark. Would you like it printed so it can be mailed?" With only print she asks only about print.
- `unsure`: "I'm not sure that went. Ask Mark if it came before we send it again." Never retry.
- other codes: the code's plain message, plus the print offer.
- `None` from the gate: `{"stale": true}`, back to the look, no say.

**Email content:** card: subject "A birthday card from <signature>" (by occasion; "A card from <signature>" otherwise), body words + blank line + signature, picture `card-<id>-mail.jpg`. Plain message: "A message from <signature>", no picture. No tag or footer (decision 8).

**The mail picture:** a new part `mail` in `PICTURE_PARTS` and in the page's `PICTURES`: 1240 by 868 from `both`'s file, quality tried at .8, .7, .6, .5 until the blob is at most 590 KB. Record `draft["mail_rev"] = rev` when its last piece lands. Stale or missing means not ready. If `look_wanted` when it lands, arm and return the effect and the line. Any change to the draft calls `disarm_send` (do it in `_keep` when words, signature, verse, front, hand or person changed).

**Manifest:** `needs.send_mail: true`, new actions, version 0.2.0, descriptions under the card's limits. The instructions: replace "Nothing sends yet: send_it says so, then offer to print." with lines that say (i) send_it when they want it sent, and when you think they're done, (ii) the app listens for "send it" itself, so never say it went unless told, (iii) never read an address aloud except when spelling one back, (iv) stay silent during the count, (v) never write to anyone on your own. `mary/instructions.md` is not touched.

## Screens (boards D2, D2b, D3, F, G, G2)
Port the `.c8-` rules needed from `mockups/mary/round8/r8.css` into `skills/messages/screen.css`, and the envelope drawing from `D2-LastLook-Mary.dc.html` into `screen.js` or an asset. Effects:
- `look` {look, name, email, kind, front|file}: D2, or G for a letter. Post `look_up` once drawn.
- `tap`: adds the one quiet Send it (`.c8-quiet`).
- `count`: D3 or G2. Undo is up and live at once. The digits 5 to 1 start after her line: `say` promise in Normal, a 2200 ms lead in Live, at most 4000 ms either way. Each digit lasts 1 s. Reduced motion: a plain changing number with no fade.
- `sent`: board F, plus the "Sent to Mark." line.
- `need_address`: envelope plus a big field (28px, 64px tall) and one button "Use this". No board exists for this; it's the only way to type one.
- `address_wait`: the address very large in letters, to check by eye.
- `make_mail`: run the picture job now, with no wait.

**At the end of the count:**
- Live: page sends `count_done`.
- Normal: the count opens the mic with `MaryApp.listenOnce`; at the end it ends the listen, waits for the words (at most 6 s, Undo still up), and posts them to `/api/mary/heard`. Only if that doesn't stop it does it send `count_done`. Normal talk must not start another reply from those words.
- Live partial words: a `MaryApp` hook gets each growing transcript during the count, and a `STOP_WORDS` hit posts `undo` at once. A failed post means no `count_done`.
- During the count in Live, her speech after the lead is hushed with `MaryLive.stopSpeaking`.
- On `leave`: `left`. Undo, and a stop heard, end the count at once.

## Never
No scheduling, no retry on its own, no reading mail, no address in logs other than `mail.log`, no change to `mary/instructions.md`, `bench/`, `tools/brain_bench.py`, `packaging/` or `mockups/`.
