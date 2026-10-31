# Cards and messages to family: the plan (M15)

Status: **plan and boards, waiting for Andy.** Written 2026-10-31 on the second account. No app code yet. Boards: `mockups/mary/round8/`. Andy's words: M15 in `docs/mary-roadmap.md`.

## The short version
- **Why:** "I see that it's your son's birthday coming up next week. Would you like for me to help you make him a card that we can send to him?" And: "will you please help me send a message to my grandson?" This ties residents to their people outside.
- **Email:** Mary can really send it herself, once a helper has connected the account one time.
- **Messenger:** Mary can't send it, and no honest tool can. Meta gives personal accounts no way for an app to send to a friend. Mary writes the message, opens the chat, and the resident taps Send.
- **Pictures:** a free drawn set works offline. Pictures made to order cost about 3.4 cents each and need a paid Gemini key.
- **The rule that never bends:** nothing leaves the laptop without the resident's clear yes, after Mary has read it back.

---

## 1. Research: what's true today
Checked 2026-10-31. A date after a source is the date on that page. "No date" means the page shows none. Guesses are kept apart in section 2.

### Email
| Service | What works | What a helper does once | Catch |
|---|---|---|---|
| **Gmail** | A 16-character **app password** over SMTP. Google says these are "not recommended" but still offers them. | Turn on 2-Step Verification, make the app password, and paste it into Mary. | It stops working when the Google password changes. It's missing on security-key-only or Advanced Protection accounts. |
| **Gmail, the better way later** | Sign-in through Google (OAuth) with the `gmail.send` permission. | One click on Google's sign-in page. | `gmail.send` is a "sensitive" permission, so **the app needs Google's verification first.** Until then, third-party guides say: at most 100 test users, and the sign-in dies after 7 days. **The device-code flow is not allowed for Gmail:** no Gmail permission is on Google's list. |
| **Yahoo** | An **app password** over SMTP. | Make it under Account Security, "External connections". | Yahoo decides who is eligible, and "customer care can't override" that. Use a browser that has been signed in for several days. Forum users in May and June 2026 report the option missing or broken. It survives a password change. |
| **Outlook.com / Hotmail** | **Sign-in only (OAuth), no app passwords.** Microsoft Graph `Mail.Send` works for personal accounts. The device-code flow works with personal accounts: Mary shows a short code, the helper signs in, and it lasts 15 minutes. | Type the code and sign in. | We must register the app with Microsoft first. An app registered with a personal Microsoft account can't be publisher-verified. Microsoft's own page says it "will fully remove" basic sign-in and gives no date; one vendor guide says it ended 2024-09-16. Plan as if it's gone. |

**Keeping the secret safe.** Windows Credential Manager stores a generic secret per Windows user, up to 2,560 bytes (`5*512`). That's plenty for an app password. A Microsoft refresh token may be longer and may need splitting across entries. It's reachable from Python with no new package (`ctypes`). It is never in `settings`, the database, a backup or a log, and never reaches the page or Gemini.

Sources: [Google app passwords](https://support.google.com/mail/answer/185833) (no date) · [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) (2026-09-10) · [Google device flow scopes](https://developers.google.com/identity/protocols/oauth2/limited-input-device) (2026-10-16) · [Google workspace: less secure apps](https://knowledge.workspace.google.com/admin/sync/transition-from-less-secure-apps-to-oauth) · [third-party note on the 7-day limit](https://docs.unified.to/skills/gmail-oauth-app/SKILL.md) · [Yahoo app passwords](https://help.yahoo.com/kb/SLN15241.html) (no date) · [Yahoo forum reports](https://helpforum.sky.com/t5/Email/App-Password-Screen-Broken-Can-t-Generate-New-App-Password-s/m-p/5304376) (2026) · [Outlook basic sign-in](https://support.microsoft.com/en-us/office/f4202ebf-89c6-4a8a-bec3-3d60cf7deaef) (2024-02-27) · [Graph sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail) (2026-06-19) · [Microsoft device code](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code) (2026-06-15) · [Publisher verification](https://learn.microsoft.com/en-ca/entra/identity-platform/publisher-verification-overview) · [CREDENTIALW](https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw) (2025-11-25)

### Facebook Messenger
**The honest answer: there's no official way for an app to send a message from a personal account to a friend.**
- **The official Messenger tools are for business Pages only.** "A Facebook Page is required," and the person must start the conversation with the Page first.
- **Scripts that drive Facebook are the wrong road.** Meta's terms say you "may not access or collect data from our Products using automated means (without our prior permission)", and that it can "suspend or permanently disable" an account for serious or repeated breaches. Tools that click Send for you are at the least in that danger zone. A resident's Facebook is how they see their grandchildren. We won't risk it.
- **Messenger on a computer has changed.** The Windows app ended 2025-12-15. Meta's notice said "Starting April 2026, messenger.com will no longer be available for messaging… You can use facebook.com/messages." One Meta help page still says to visit messenger.com. So Mary must open `facebook.com/messages`, and we must test it.
- **Links that open a chat:** `m.me/<username>` is documented only for Pages. Its `text=` setting (a prefilled message) is also documented only for Pages. Third-party guides flatly disagree on whether prefill works.
- **The old Send Dialog** still has a page, with no sign it's retired. It sends a public web link, not a picture, so the card would need to be hosted somewhere. There is no backend for that yet, and the page itself says messages are person-to-person.
- **Encrypted chats:** personal chats are end-to-end encrypted by default. On a new browser Messenger may ask for a PIN to bring back the history, and Meta can't reset it for you. The helper should sort this out at setup, once.

**The best honest flow** (boards E1 to E3):
1. Mary writes it with them. They say yes to the words.
2. She puts the card, or the words, on the Windows clipboard.
3. She opens that person's chat at `facebook.com/messages`.
4. A slim Mary strip stays at the top of the screen, with one big **Paste** button.
5. They tap Paste. The card lands in the chat.
6. **They tap Send themselves.** Mary never touches Facebook's page and never reads it.
7. She can't see whether it went, so she asks: "Did it go?"

**Why a Paste button:** paste normally needs a key combo or a right-click, and both are out for our residents. The words are printed on the card picture, so a card needs one paste, not two. A plain message also needs one.

Sources: [Messenger Platform overview](https://developers.facebook.com/docs/messenger-platform/guidelines) · [Send API rules](https://developers.facebook.com/docs/messenger-platform/send-messages/) · [Facebook terms](https://www.facebook.com/terms) (effective 2025-01-01) · [m.me links](https://developers.secure.facebook.com/docs/messenger-platform/discovery/m-me-links) (no date) · [TechCrunch on the desktop app](https://techcrunch.com/2025/12/15/facebook-messengers-desktop-app-is-no-more/) (2025-12-15) · [Social Media Today on messenger.com](https://www.socialmediatoday.com/news/metas-shutting-down-its-messenger-website/812497/) · [Meta help: Messenger app](https://www.facebook.com/help/messenger-app/804132271957789) · [Send Dialog](https://developers.facebook.com/docs/sharing/reference/send-dialog) · [Meta on encrypted chats](https://messengernews.fb.com/2024/03/28/end-to-end-encryption-what-you-need-to-know) (2024-03-28) · [restoring chats](https://www.messenger.com/help/431055522328649/?locale=en_US)

### Others residents use
- **Who's where:** Pew's 2025 survey says Facebook and YouTube are the only sites a majority of every age group uses, and only 19% of people 65+ use Instagram. So Andy is right: Facebook is where they are. An older Pew figure had WhatsApp at about 6% for this age group (the year isn't clear).
- **WhatsApp:** the only one with a true prefill. `https://wa.me/15551234567?text=<words>` opens the chat with the words typed, and the resident presses Send. WhatsApp's own help page wouldn't load, so this rests on third-party guides that all agree. It needs a phone number, and pictures need a paste.
- **Texting through Phone Link:** on Android, texts and pictures work from the PC. **On iPhone, no pictures and no group messages:** "Phone Link for iOS currently does not support the sending or receiving of images." We found no working way for an app to open it with a message ready. It needs a paired phone and a helper.
- **Print it:** no internet, no account and no risk. Many in this age group would rather hold a card than get a link.

Sources: [Pew 2025](https://www.pewresearch.org/internet/2025/11/20/americans-social-media-use-2025) (fieldwork 2025-02-05 to 06-18) · [older Pew figures in McKnight's](https://www.mcknightsseniorliving.com/?p=24501) · [WhatsApp links, third-party](https://support.dotdigital.com/en/articles/11331301-click-to-chat-for-whatsapp) · [Phone Link](https://support.microsoft.com/en-gb/windows/apps/phonelink/send-and-receive-text-messages-from-your-pc)

### Making pictures
Prices are paid-tier, per picture, from Google's pricing page (updated 2026-10-30):

| Model | 1K picture | Notes |
|---|---|---|
| `gemini-3.1-flash-lite-image` (Nano Banana 2 Lite) | **$0.0336** | Google's fastest and cheapest. 1K only, and enough for a card. Sizes include 4:3 and 5:4. |
| `gemini-nano-banana-2.1` | $0.0336 | Google's main model, same price. |
| `gemini-3.1-flash-image` | $0.067 | The previous generation. |
| `gemini-3-pro-image` | $0.134 | Too dear for a card. |
| `gemini-2.5-flash-image` | $0.039 | Shuts down 2027-03-15. Don't build on it. |

- **There's no free tier for pictures.** So a resident without a paid key must still have nice cards. That makes the drawn set necessary, not a nice extra.
- **Privacy on the paid tier:** Google says it doesn't use paid prompts or responses to improve its products. It does keep prompts and outputs **55 days** to watch for abuse, and flagged items can be read by authorized staff. The page shows no way to turn that off. The free tier is far worse: people can read it, and it's used for improvement.
- **Every picture carries an invisible SynthID watermark.**
- **Safety filters:** a blocked request fails with an error, and child-safety blocks can't be changed. The safety page doesn't say how this applies to the picture models, so Mary needs a plain line for any refusal.
- **Spelling:** the app prints the words on the card itself. The picture model never draws them, so names are always spelled right, and names and personal words never go to Google for a picture.

Sources: [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) (2026-10-30) · [Gemini API terms](https://ai.google.dev/gemini-api/terms) (2026-04-28) · [Abuse monitoring](https://ai.google.dev/gemini-api/docs/usage-policies) (2026-06-09) · [Safety settings](https://ai.google.dev/gemini-api/docs/safety-settings) (2026-10-15) · [Image generation](https://ai.google.dev/gemini-api/docs/image-generation)

---

## 2. What we don't know yet (guesses, to test)
**Four of these need a real Facebook account and a browser, so workers can't test them.** Andy or a helper can settle them in about five minutes, with a friend who agrees.

| # | Question | If the answer is no |
|---|---|---|
| 1 | Does `facebook.com/messages/t/<username>` or `m.me/<username>` open the chat with a friend today? | Open `facebook.com/messages`, and Mary says who to look for. |
| 2 | Does `m.me/<username>?text=hello` prefill for a friend? (Likely not.) | Paste, as planned. |
| 3 | Does the typing cursor land in the chat's message box on arrival? | The strip tells them to tap the box first. One more tap. |
| 4 | Does a picture pasted from Windows land in the chat ready to send? | Save the card, and open the picture picker. Harder. |
| 5 | Can a strip take a tap without pulling focus off the browser? (`WS_EX_NOACTIVATE`, tested by a coder on a scratch page.) | Fall back to Windows Voice Access: say "paste", then "click Send". |
| 6 | Does Gmail's app password keep working across many sends? Google's page has one odd line, "can only be checked once"; we read that as "you enter it once". Long experience says it's fine. | Test once with a throwaway account before building. |
| 7 | Do personal Outlook.com accounts accept consent for an app that isn't publisher-verified? The evidence is from 2020 and about work accounts. | Outlook.com residents use the open-in-webmail way until it's settled. |
| 8 | Do Gmail, Outlook and Yahoo compose links still take a prefilled address and text? (From memory, not checked.) | Open plain webmail. |

**A note on the Paste button and Meta's rules.** The terms say nothing about a resident-tapped paste. It's the same thing the Windows On-Screen Keyboard does. The resident does the tap, one message at a time, and the resident taps Send. Mary reads nothing from Facebook. We think that's on the right side of the line, but that's our reading, not Meta's word.

---

## 3. The flows
### The birthday reminder
1. **Learning the date.** When a resident says "Mark's birthday is November 7th", the memory keeps it, as it does today. **New:** the date itself is saved as month and day, who it's for, and what it is. Today memories only carry the day they were said (`created_at`), so a brain can't count down to anything.
2. **When she raises it.** The first talk 8 to 5 days ahead of the date. That window means a missed day doesn't lose it.
3. **Once.** It goes to her brain as one quiet note, and she says it in her own words, so it's one mind and one voice. Then it's marked done for the year, whatever they answer. She never brings it up twice.
4. **Never for someone who has died.** If a memory says that person has passed, there is no reminder and no card offer. A dead husband's birthday should only come up if the resident raises it. "Don't remind me about him" stops it for good.
5. **No birthdays guessed.** She only uses dates the resident gave her.

### Making a card
1. They pick a design by voice or tap (board B).
2. They say the words. Mary may help, **in their voice, never hers.** She offers a line only if they ask. She doesn't add feeling they didn't express, and she reads it back.
3. The card is shown with their words printed on it (board C). They can change the words or the design at any time.
4. "This is it" goes on to sending. A card is also saved on their laptop, so it's never lost.

The occasions: birthdays first, then holidays, get-well, sympathy and thank-you notes (staff included). Each is a set of designs, not a new feature.

### A plain message
"Help me send a message to my grandson." No design step: they say it, she shows it (board G), they say yes, and it goes by whichever way that person uses. If they say "tell Tyler I'm proud of him", she writes it as them, in their words, and shows it first.

### Sending
| Way | Who presses Send | After |
|---|---|---|
| **Email** | Mary, after their yes. A five-second **Stop** follows, in case they change their mind. | "Sent to Mark." |
| **Messenger** | **The resident**, in Facebook. | She asks, "Did it go?" |
| **WhatsApp** (later) | The resident. | Same. |
| **Print** | The resident, at the printer. | Paper in hand. |

## 4. Who does what
**Mary does by herself:** notices the date, offers once, helps with words when asked, fills in the card, finds the saved contact, puts it on the clipboard, opens the chat.

**The resident always does:** decides whether to send at all, picks who, says or taps yes after the read-back, taps Send in Facebook.

**The yes is hard-wired, not left to Gemini.** A brain can be talked into things, and a resident can be confused.
- Sending happens only through a "last look" screen (board D2), which shows the card, the person and the way.
- The core only sends if that screen was shown and then a tap or a plain "send it" came back. A hint from Gemini isn't enough.
- "Okay" or "sounds good" in the middle of a chat doesn't count.
- **Mary never writes to anyone on her own, never sends on a schedule, and never reads replies.** Outbound only, one message at a time.
- **She won't help send money, passwords or Social Security numbers.** If a message asks for those, she pauses and says so plainly. Lonely, older people get targeted, and this feature must not become a tool for that.
- The care log stays separate: no incident goes out through this feature unless the resident dictates it into a message.

## 5. Contacts
- **Kept only if they want.** After the first send she asks once, "Keep his address for next time?" (board F). No is fine, and it's never asked about that person again.
- **What's kept:** name, relationship, email, and Facebook username or phone number. Kept on the laptop, in the skill's own store, apart from the care log and in no report.
- **Never sent to Gemini wholesale.** Her brain gets the names only. The address is used by the core when sending.
- **"Forget Mark's address" really removes it.** "Forget Mark" removes the contact and his dates too, and a test proves it. Memory's `forget` must reach these two new stores, which it doesn't do today.
- **Facebook names are the hard part.** Residents rarely know a username. A helper sets it up, or Mary opens the messages page and they find the person themselves.

## 6. Privacy: what goes where
| Goes to | What | When |
|---|---|---|
| **Google (Gemini)** | Their spoken words for the reply, as in any talk | Every talk |
| **Google (picture)** | Only a description of the picture: "a largemouth bass jumping at sunrise". Never names or the message. | Only if they ask for a new picture |
| **Their email company** | The card and message, from their own account | After their yes |
| **Meta** | Whatever they paste and send, from their own account | Their own tap |
| **Nobody** | Contacts, dates, saved cards, the mail secret | Stay on the laptop |

Say it plainly in My info: on the paid tier Google keeps what's sent for 55 days for abuse checks. That goes further than the mission's line "their words stay on their laptop, except in the packet for one reply", so **the mission wording deserves a look** whatever Andy decides here.

Separate find, not part of M15: the Gemini key is in the app's settings store (`server.py:70`). A worker should check if it's plain text, and move it to Credential Manager along with the mail secret.

## 7. Costs
| Item | Cost |
|---|---|
| Drawn cards, email, Messenger, WhatsApp, print | Free |
| One new picture | about 3.4 cents |
| A busy year: 12 cards, about 3 tries each | about $1.20 |
| Google app sign-in verification (later) | Possibly nothing but time; a demo video and a review |
| Microsoft app registration | To be checked; verification needs a work account and a partner ID |

Wording help runs on the normal talk model, so a card adds pennies at most.

## 8. Build list
Two core gaps come first. **`ctx.fetch` is GET-only, with no request body, and no SMTP,** so neither mail nor pictures can go through it. Rather than loosen it, add two narrow core services: `ctx.send_mail` (the skill never sees the secret) and `ctx.make_picture`. Both are logged and listed on the skill's card. The skill waits for M13b's tool groups.

| Item | What | Done when | Who |
|---|---|---|---|
| **M15a** Dates | Save birthdays as dates; reminder once, 8 to 5 days ahead; none for the dead; forget clears them | Tests with a fake clock: once only, across restarts and a missed week; "forget" removes it; Andy hears it in a talk | Opus coder on the second account |
| **M15b** Cards | The `messages` skill, the screen, 12 drawn designs, words printed on the card, saved as a picture, print | Boards A to C matched; offline works; long words fit; Andy approves | Opus for code; Sonnet for tests |
| **M15c** Contacts and last look | The contact store, the hard-wired yes, Stop, real forget | A test proves nothing sends without the yes, and a chatty "okay" doesn't count | Opus, `xhigh` |
| **M15d** Mail | Credential Manager, `ctx.send_mail`, Gmail and Yahoo, helper setup in My info | Sends to a scratch mailbox; the secret isn't in the database, backups, logs or the page | Opus, `xhigh` |
| **M15e** Messenger | Answers to the tests in section 2, clipboard, open the chat, the Paste strip, "Did it go?" | Andy sends a real card to a friend in under a minute, with no key combo | Opus, after Andy's five-minute test |
| **M15f** Picture making | `ctx.make_picture`, a set cartoon style, plain lines for refusals, a cost line in My info | A picture lands in a card; a refusal fails politely; no names in the prompt | Opus for code; Sonnet for tests |
| **M15g** Outlook | Register the app, device-code sign-in, Graph send | A helper connects a test Outlook.com account | Opus, once test 7 is settled |
| **M15h** WhatsApp | The `wa.me` link, phone numbers in contacts | The chat opens with the words ready | Sonnet |
| **M15i** Google sign-in | Google verification, replace the Gmail app password | Verified, with no warning screen | Opus, plus Andy's review steps |

Order: a, b, c, d, then e, then the rest. A helper-free resident gets cards, print and Messenger with no secret to set up.

**Setup for a helper, added to the setup list:** connect email, sort out the Messenger PIN, keep the browser signed in to Facebook, and add the family's contacts.

## 9. Decisions for Andy
| # | Question | Recommendation |
|---|---|---|
| 1 | How do residents paste in Messenger? | **Mary's big Paste button**, on the strip (boards E2, E3). It needs test 5. Voice Access is the fallback. |
| 2 | Which email first? | **Gmail and Yahoo with app passwords now.** Outlook.com next, then Google sign-in to retire the Gmail app password. |
| 3 | Drawn cards, made-to-order, or both? | **Both.** Drawn is the default, because it's free and offline. A new picture is one choice among them, and only with a paid key. |
| 4 | Does a spoken yes count, or must they tap? | **Either:** a tap or "send it", after the read-back, then five seconds to stop. Many residents can't tap well. |
| 5 | Print as a third way? | **Yes.** Free, no accounts, and a card to hold. Needs someone to mail it. |
| 6 | When does she ask to keep an address? | **Once, after the first send.** Never before they've used it. |
| 7 | WhatsApp and texting? | **WhatsApp later, as M15h. Texting through Phone Link not at all for now:** no pictures on iPhone, and heavy setup. |
| 8 | Does a message say Mary helped? | **No tag.** It's their message, from their account, in their words. If they ask, she's honest. |
| 9 | Reminders for who? | **Family and friends with a date the resident gave,** one week ahead, once a year. No reminders for the dead. Holidays only if they ask. |
| 10 | Mission wording on what leaves the laptop | **Update it** to say what Google keeps on the paid tier. |
| 11 | Your five-minute Facebook test | **Please do it before M15e.** It needs a friend who agrees, and it settles four unknowns. |
