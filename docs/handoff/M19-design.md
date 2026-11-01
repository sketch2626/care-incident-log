# M19 design note: a secure address book

Proposal for Andy, drawn on the boards in `mockups/mary/round10/`. Nothing here is built, and the build waits for M18 to merge. Andy's words are in the M19 section of `docs/mary-roadmap.md`. Everything below about today's code comes from reading it, not from running it.

## A problem that exists today
M15c's contacts sit in the `skill_data` table, and that table is inside `incidents.db` (`server.py:694` passes `connect`). So every saved address is plain text in the log, and it's copied into up to 30 dated backups. "Forget Mark" removes him from the live table but never reaches those backups, so the promise that forget really removes him isn't kept today. `incidents.db` also has no `secure_delete`, so freed text can stay in the file. M19 fixes this, and the hub should know it before then.

## Where it lives: core, with plug-ins using it
Andy asked if it should be a plug-in: "we can plug in an address and then we can plug in other things that work in that way."

**Decided (Andy, 2026-11-01): a core module, `address_book.py`, beside `memory_core` and `mail_core`, with one narrow door for skills.** His words: "a permanent secured part of the app, and other things could just ask for permission to use it." Phone apps ask to use Contacts the same way.
- Many things use it: cards and email, M15a's reminders, a later Messenger or phone skill, and speak-up (a family member or the ombudsman).
- Its protection is core-only: the key, the forget path, and keeping details away from Gemini. A skill can't reach the key.
- Switching a skill off must never lose anyone's address.

**The door:** a card declares `needs.contacts`, and `tests/test_skills_contract.py` enforces it.
- `ctx.people.find(words)` gives a handle: id, name, relationship, and which details exist (`has_email`, `has_phone`...). No values.
- `ctx.people.send_to(handle, ...)` passes the address straight to `send_gate.py`. The skill never holds it. M15c's rule stays: an address leaves only in a page effect, never in a result, a say or a view.
- No skill keeps its own copy of anyone.

**The same pattern can hold other lists a resident keeps,** when one is really wanted. Two that would help: **My calendar** (visits, doctors, care-plan meetings, which residents have a right to attend) and **My medicines** ("they changed my pills" is a speak-up moment). Neither is part of M19, and no general framework gets built ahead of need.

## My doctors: a part of the same book (a note and a board, not built in M19)
Andy: "a separate part of that book that has her medical professionals… plugins to just add to it that then… gives her an easier way to contact her doctor's office." It fits only some residents, so it stays optional.

**Same store, not a second one.** A doctor is an entry with `kind: "doctor"` inside the same sealed row, with the same key, forget, rolling copy and helper's copy. Its fields are practice, specialty, office phone, fax, address, patient portal and notes (board H1). Rows are sealed JSON, so adding it later needs no change to the file.

**Stricter than family, because a doctor's specialty can reveal a condition ("Dr. Lee sees me for my heart"):**
- **Gemini:** doctors stay out of her everyday list of names. She looks them up only when the resident asks about a doctor. Specialty and notes go only when they ask to hear that field, never because a task "needs" them.
- **Her memories and talk history:** the same filter as the rest of the book, and it covers notes too. She never brings a doctor up on her own.
- **Logs:** ids and codes only, never a doctor's name. `mail.log` keeps the same salted hash.
- **Reports:** never included, same as the rest of the book.
- **Portal:** the card keeps the web address only. A portal password is a secret, kept out of the book, and she won't read or fill it (M18's rule).
- **Email to an office:** ordinary email isn't private, so she says that before anything about their health goes to a doctor's office. A later fax or portal skill would be weighed on its own.

**A later plug-in asks for just this part.** `needs.doctors` is separate from `needs.contacts`, so holding one gives nothing of the other. A card declaring it isn't enough: the first time, the resident hears what it wants and says yes or no ("This wants to see your doctors. All right?"). They can take that back in My info. It gets a handle and passes values through the same door, and a plug-in may add or change a doctor only with the resident's Save, like Mary.

## Security: how it's stored
| | Plain, in its own file | Encrypted, key in Credential Manager (the pick) |
|---|---|---|
| Copying the data folder (a USB stick, a support zip, a stray backup) | Everything readable | Only scrambled text |
| Pulling the drive from a lost laptop | Everything readable | Unreadable without that Windows sign-in |
| Someone sitting at the signed-in, open laptop | They can open the screen | **The same: they can open the screen** |
| New laptop | Copy the file | Needs a helper's copy (below) |
| Key lost | Nothing to lose | Book unreadable without a helper's copy |
| Cost | None | A new library, a recovery path, more tests |

**Pick: encrypt.** These are other people's addresses and their birthdays, and a nursing home is a place where a laptop can be handled by many people. Andy said "stored there securely", and build-as-if-the-state-will-read-it points the same way.

**How:**
- New file `mary/addressbook.db`, apart from the log, `secure_delete` on.
- One row per person: an id, and one AES-256-GCM sealed blob holding all their fields, **names included**, so the file has no readable list of who the resident knows. The row id is bound into the seal, so blobs can't be swapped.
- A random 256-bit key under `address_book_key` in `secret_store.py`. Its name carries the data-folder hash, so a scratch install can't see the real book.
- AES needs the `cryptography` package, pinned in `packaging/requirements.txt`: Python's standard library has no AES. The stdlib rule stays for `server.py`; only `address_book.py` imports it. Turned down: Windows DPAPI through `ctypes`. It needs no library and rests on the same sign-in, but a helper's copy needs AES anyway, and that would mean two schemes.
- The book decrypts into memory only while the app runs. 500 people, today's limit, is small enough to search without an index.

**What this doesn't do, said plainly.** It can't stop someone at the open laptop, and on a laptop with no Windows password, a thief can just sign in. Question 3 covers that. The line on the boards, "Kept only on this laptop, locked.", must only ship if it's true.

**If the key is missing, never make a new one over existing rows.** The screen says the book is locked and offers a helper's copy. Nothing is wiped.

## Backups, a new laptop, a restore
- **Daily backups:** the book stays out of `backups\`. It gets one rolling copy, `mary/addressbook_backup.db`, sealed the same way and rewritten at once after every forget, exactly as `backup_memories` does.
- **That copy only works on this laptop, with this Windows user.** Same for a restore: restored data with no key stays locked. Credential Manager entries don't travel (`CRED_PERSIST_LOCAL_MACHINE`).
- **A helper's copy is how a book moves.** In My info, "Make a helper's copy" writes one file to a USB stick and shows six plain words once, for writing on paper and keeping with family. The file is sealed with a key made from those words (`hashlib.scrypt`). On the new laptop: pick the file, type the six words, and people are merged in by name.
- **Forget can't reach a copy out on a stick.** The helper-copy screen says so, and old copies should be thrown away.

## What Gemini sees
- **Always available:** names and relationships, through `find_person`, the same as `find_contact` today. Plus which details exist, never their values.
- **Details, only when needed:** `read_detail(person, field)`, one field, only when the resident asked to hear it or their task needs it. Andy on M18: she can fill in or read an email address, "She just doesn't need to save it anywhere that it can be picked up and published somehow." That detail goes to Google in that one reply's packet.
- **Spoken details do go to Google.** When a resident says an address aloud, it's their words in the talk, kept up to 55 days on the paid tier like any other (`docs/messaging-plan.md`). Only a helper's typing avoids that, and the typed form never reaches Gemini unless someone asks her about it (F1). `docs/messaging-plan.md` table 6 and My info need updating to say so.
- **Screens:** M18's `look_at_screen` sends a listed field's value, which is too much here. New `detail` kind in `web/mary/screens.js`: the list gives names and relationships, the card gives only which fields are filled, and the form gives only what she filled herself.
- **Never kept:**
  - Her memories: the save path refuses text with an email, phone or street pattern, or any detail from the book.
  - Talk history: when a detail is said, the saved turn holds "[address]" in its place.
  - `skills.log`: already names and codes only.
  - Reports and the spreadsheet: `reports.py` never opens the book, and a test proves it.
- **One conflict:** the roadmap says details stay out of logs, but `mail.log` keeps each send's address today. Decision: it keeps a salted hash instead, and `scrub_log` matches on that. The date and result are unchanged.

## What carries over
**M15c's contacts:** moved once, at first start, field for field.
1. Read every `contact-*` row, seal it into the book, read it back to check.
2. Delete those rows from `skill_data`.
3. Clean the 30 dated backups: on a copy, delete the rows, `VACUUM`, confirm the incidents table is identical, swap it in. Any mismatch leaves that backup alone and logs a count. This touches evidence files, so it gets its own tests and an Opus coder.
- `asked` and `no_keep` carry over, so nobody's asked twice. A person with `no_keep` and nothing else stays a hidden "don't ask" mark, not a row in the list.

**Birthdays, one truth:** today every date has a memory behind it (`learn_date`). A book birthday adds a `dates` row with `source='book'` and the person's id, and no memory. M15a's reminders then work as they do now.
- Changing the birthday on the card changes that row. The same person's date learned from talk merges into it, so no double reminders.
- Mention in talk with an empty card: she asks once, "Put that on Mark's card?"
- `memory_dates.passed` keeps its job: if they say someone died, the reminders go quiet, and the card stays unless they ask. She doesn't offer to remove anyone who's died.

**What "forget Sarah" reaches:**
- Her row, with the rolling copy rewritten at once.
- Her `dates`, `date_done`, `date_sent` and `no_reminders` rows.
- Memories holding her name, and talk history (already done through `mary.py` `scrub`).
- Her address in `mail.log`, and any waiting send to her.

**What stays:** saved incidents, which are evidence, and saved cards, which are the resident's own keepsakes.

**"Forget Mark's address"** now means two things, so she asks: "His email or his mailing address?"

## Keeping an address after a first send (boards G1, G2)
- **A. Ask once:** "Sent to Tom. Keep Tom's address for next time?" Built already. One word, once per person, then "Email Tom" just works.
- **B. Keep it and say so:** "Sent to Tom. His address is in your book now. Say so if you'd rather I didn't keep it." No question, but the record exists unless they object.

**Pick: A.** It keeps the one rule the boards teach, that she never saves by herself, and a no is respected for good. B is a touch smoother, and it's the only place she'd save unprompted, about someone who isn't her user.

## What the build would take
| Piece | What | Stands alone? |
|---|---|---|
| 1 | `address_book.py`: seal, key, rows, rolling copy, locked state, tests | Yes. Opus, second account |
| 2 | The `ctx.people` door, `needs.contacts`, contract test | After 1 |
| 3 | M15c's contacts move in, `messages` uses the door, the backup clean-up | After 2. Opus, xhigh |
| 4 | Forget's reach, birthdays as `dates` rows, the ask for "address" | After 2 |
| 5 | Screens: list, find, card, form, helper mode; Up, Down; Menu item | Needs M18's frame |
| 6 | Her tools (`find_person`, `read_detail`, fills, `is_plain_save`), `detail` kind, the refuse-to-remember filter, `mail.log` hash, instructions, bench cases | After 4 and 5 |
| 7 | Helper's copy, export and import | After 1; can come last |

Order: 1 to 4 with no screen, so the contact fix lands early. Then 5, and Andy tries the list. Then 6, and Andy tries adding by voice. Then 7. Sam is the same code.

## Questions for Andy (one tap each)
1. **After a first send to someone new, does she ask or just keep it?** [Ask once] [Keep it and say so]
2. **Should "forget Sarah" also clear what Mary remembers about her?** That's what forget does today. "Take her out of my book" would remove only the card. [Yes, all of it] [Only the card and reminders]
3. **Should setup put a Windows PIN on each laptop?** The lock only helps once the laptop is locked. Anyone at an open one can see the book. [Yes, in setup] [Leave it to each resident]
4. **Should "forget everything" include the address book?** Today it clears the contacts, but a book a helper spent an hour typing is a bigger loss. She'd say so first. [Yes, she warns first] [No, the book stays]
5. **A helper's copy for a new laptop, with six words kept on paper?** Without it, a broken laptop means typing everyone in again. [Yes] [No, keep it simple]
