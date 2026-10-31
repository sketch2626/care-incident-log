# Cards and messages to family: the plan (M15)

Status: **Andy read the plan and boards on 2026-10-31.** His answers are folded in, and section 9 lists what's still open. Written 2026-10-31 on the second account. No app code yet. Boards: `mockups/mary/round8/`. Andy's words: M15 in `docs/mary-roadmap.md`.

## The short version
- **Why:** "I see that it's your son's birthday coming up next week. Would you like for me to help you make him a card that we can send to him?" And: "will you please help me send a message to my grandson?" This ties residents to their people outside.
- **Email:** Mary can really send it herself, once a helper has connected the account one time.
- **Messenger:** Mary can't send it, and no honest tool can. Meta gives personal accounts no way for an app to send to a friend. Mary writes the message, opens the chat, and the resident taps Send.
- **Pictures:** a free drawn set works offline. Pictures made to order cost about 3.4 cents each and need a paid Gemini key.
- **The rule that never bends:** nothing leaves the laptop without the resident's clear yes. Andy's own words are that yes: "Now send it."

## The routes, smoothest first (Andy: "Hey, let's build this card. Now send it. And Mary just sends it.")
Andy asked for this to be as smooth as possible. **The first three really are "Mary just sends it".** Messenger can't be, today, within Meta's rules.

| Rank | Route | The resident does | Today | Allowed? | Status |
|---|---|---|---|---|---|
| 1 | **Email, connected once by a helper** | Says "send it" | Mary sends it | Yes: it's their own account and the mail companies' own doors | **True today** for Gmail, Yahoo, and Outlook.com once registered |
| 2 | **Email from a Mary service address** (future backend) | Says "send it". No helper or account needed. | Mary sends it | Yes | Needs the backend and its security review. Son sees a new sender. |
| 3 | **Text from a Mary service number** (future backend) | Says "send it" | Mary sends it | Yes, with the phone companies' registration and the son's agreement. Not Meta. | Needs the backend. Cost in section 7. Son sees an unknown number and a link, so he must be told first. |
| 4 | **Messenger in the panel beside Mary (Andy's choice)** | Taps Paste, then Send | Mary opens the chat and readies the card | **Showing the page: our reading is yes.** Tap-to-paste: our reading is yes, not Meta's word. | **Guess:** sign-in inside an app window may be refused (test 9) |
| 5 | **Facebook Send Dialog, with a card at a private link** | Picks the friend, taps Send | Mary opens the dialog | Official, but its page is old, and it needs a Facebook app of ours | **Guess:** may be dead. Needs hosting. Sends a link, not a picture. |
| 6 | **Messenger in their normal browser** | Taps Paste, then Send | Mary opens the chat | Same as route 4 | Test 5 decides the Paste button |
| 7 | **WhatsApp link** | Taps Send (and pastes a picture) | Words are typed in for them | Yes: a documented link | Works, third-party sources. Few residents use it. |
| 8 | **Print and mail** | Prints it | Nothing to send | Yes | Printing works today. **Mailing needs the facility's help:** "we'll have to get the places, the institutions, on board to help with that." |
| 9 | **Texts through Phone Link** | Most of it | Little | Yes | Heavy setup, no pictures on iPhone |

**Ruled out, even though they'd feel smoothest:**
- **Mary filling in or pressing Send on Facebook's page by script.** See "Messenger inside Mary's window" below.
- **Relaying through Meta's Muse.** There's no documented way for an app to hand it a task. See below.
- **Unofficial Messenger tools or wrappers.** These put the resident's account at risk.

**Andy's direction (2026-10-31):** email leads, and "anything else that we can just send right to, I want to be able to do as well." On Messenger, route 4: Facebook opens in the panel beside Mary, and the resident taps to send. Build 1, 4 (falling back to 6) and 8 first, with drawn cards. Plan 2 and 3 for the backend. Watch Muse.

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

### Messenger inside Mary's window (Andy's idea, 2026-10-31)
The resident signs in to Facebook once, inside Mary's app, and stays signed in. Mary opens it straight to the right person, with her strip above the page. **This is the best Messenger route if sign-in works.** There's no browser to hunt for, and the Paste button no longer has to work across two programs. **Andy's choice (2026-10-31):** it opens "where everything else goes, the pictures and stuff", the panel beside her that games and pictures use. Facebook's page is unlikely to load inside our own page (our expectation, untested), so the build places a separate web view exactly over that panel. That panel is narrower than a full screen, so check that Facebook's chat fits in it. **Boards E2 and E3 still show Facebook across the whole screen, with the strip above it.** They need a redraw to match before M15e.

| What Mary's app does | Meta's rules | Our call |
|---|---|---|
| **Shows Facebook's page, unchanged** (a browser, in effect) | No rule against it that we found. **But** Facebook blocks sign-in from embedded browsers on Android, and developers report that some accounts are blocked while others work. Nothing confirms this for a Windows window either way. | **Do it, if test 9 passes.** Never disguise the app as another browser to get around a block. |
| **Resident taps Paste** | Terms don't address it. It's what the On-Screen Keyboard does. | **Do it.** It's our reading, and the resident's own tap. |
| **A script types the words into Facebook's box** | The terms bar "automated means" of accessing or collecting data, without permission. Meta's ad-account notices also cite automation that mimics human activity. Typing into a box isn't clearly named, even with the resident tapping Send. | **Don't.** The gain is one tap. The cost could be their account. |
| **A script attaches the picture** | Same. | **Don't.** |
| **A script presses Send** | This is a program sending as a person. The Send Dialog page says messages are for person-to-person use, "not meant for apps to send messages". | **Never.** |
| **Reading their chats** | This is exactly "collect data… using automated means". | **Never.** |

**Account review:** a new sign-in from an unfamiliar window can bring a security check. Meta doesn't publish its triggers, and appeals are reported as hard. So a helper does the first sign-in, and the worst case is a code sent to the resident's phone. We found no Meta statement on Messenger-specific automation checks or on apps that show its pages.

**Also keep the Facebook session walled off.** It lives in its own browser profile, separate from Mary's pages, and "Sign out of Facebook" is in My info.

### Meta's Muse
- **What it is:** Meta's AI agent, launched in the US on 2026-09-08 (Singapore on 2026-10-27), on the web at muse.ai, on iPhone and Android, on Mac, and inside WhatsApp. It works websites and connected apps on a person's behalf. Meta lists sending emails and party invitations among its jobs. It stops to ask before steps "like sending a message or placing an order."
- **Does it handle Messenger?** **Yes, from Andy's own use (2026-10-31):** "I can open Muse and say, tell me who all sent me new messages, summarize them… and reply to all of them… Muse is actually pretty good at it." No published source we found says so; this is his first-hand report.
- **Can Mary hand it a task?** **No documented way.** Muse Connectors (2026-09-18) run the other way: Muse calls an outside service. Sources even disagree on whether outsiders can submit one. We found no API, link or share target for starting a Muse task. A third-party wrapper (useapi.net) exists, and that's the same account risk as any unofficial tool.
- **Cost:** free with a usage meter, then $20 or $100 a month. A payment card is needed even for free.
- **What it sees:** whatever is connected, with lasting memory of the person and of others. Training on conversations is reported as **on by default**, with an opt-out. Meta says it isn't shared with ads systems and that Muse can't see passwords. Reuters reported internal reliability and security concerns.
- **Our call: watch Muse, and don't build on it yet** (Andy agrees to watch). **The open question is whether an app can hand Muse a task.** If Meta publishes a way, Muse would be Meta's own allowed route to Messenger. Until then, residents would have to run Muse themselves, and the concerns above stand: a second AI with a long memory, a payment card, and words leaving the laptop. Check again in three months. Andy's idea of Muse as the pilot's brain is now roadmap **M16** (on `main`).

Also from Meta: since 2026-01-15 the WhatsApp Business API bars general-purpose AI assistants, so **Mary can't have a WhatsApp number of her own.**

### Facebook's official share and send options
- **Send Dialog** (`facebook.com/dialog/send`): the only official thing left that fits. It needs a Facebook app ID, takes a `link`, and takes an optional `to`, which is a numeric user ID residents won't have. It's desktop-only. It opens Facebook's own box, and the person presses Send. Its page has no date and no sign of retirement. **We can't confirm that it still works.**
- **A card at a private link:** it would have to be a hard-to-guess web address on our future backend. For a picture preview, Facebook's systems must be able to fetch it, so "private" really means "anyone with the link". The son taps a link, not a picture.
- **For now:** park it until the backend exists, then test it.

### Fully hands-free: Mary's own address or number (needs the backend)
Both need `docs/backend-plan.md` first: a message would pass through a server, and the mission says nothing real reaches a server before its security review.

**Text from a Mary number.** He'd see an unknown number:
> From your mom, sent with Mary: Happy birthday, Mark. Her card: https://…

| Cost item | Amount | Source quality |
|---|---|---|
| One US text | about 0.8 cents, plus 0.25 to 0.6 cents in carrier fees | Third-party guides; they disagree slightly |
| Number | about $1.15 a month | Third-party |
| Register the sender (once) | $4.50, plus about $41.50 vetting | Twilio's support pages |
| Register the use (once, then monthly) | $15, then $1.50 to $10 a month | Twilio |
| Picture by text | Not found. So send a link, not a picture. | Guess |

- One shared number serves many residents, so it's pennies each. Twenty texts a month is about 25 cents, plus a share of the monthly fees.
- **The catch isn't money.** A text from a stranger with a link looks like a scam. The son must expect it, and carriers want proof he agreed (our understanding; check before building). A helper or the resident's first email can get that yes.
- Replies come back to our number, so this route also answers "did he write back?"

**Email from a Mary address:** no helper and no account, and the same reply and trust questions. Prices are not researched; bulk mail services are usually a fraction of a cent. Mail may land in spam until the address has a track record (guess).

### "Did my son write back?"
| Way | What's possible | Allowed? | Risk |
|---|---|---|---|
| **Email** | With the same app password (IMAP), the app can look for new mail from saved family. Gmail through sign-in instead needs a "restricted" permission, with a security audit reported at $15,000 to $75,000 (2019 figure; a laptop-only app may be exempt). | Yes: their account, their yes | **Incoming mail is where the scams are.** Her reading unknown mail aloud could feed a scam straight to a lonely resident. |
| **Messenger** | Nothing official. Reading the page by script is what the terms bar. | **No** | Mary can open the chat so they can read it themselves. |
| **Mary's number** | Yes, it's our number. | Yes | Server stores family's words |

**Recommendation, Andy decides (#14):** email only, and only mail from saved family, only when the resident asks. She reads the message to them, and nothing in it can give her an order. On Messenger she says, "I can't see Messenger, but I'll open his chat for you."

Sources: [TechCrunch on Muse](https://techcrunch.com/2026/09/08/meta-debuts-its-muse-ai-agent-will-consumers-trust-it/) (2026-09-08) · [Muse guide, third-party](https://almcorp.com/meta-muse-complete-guide-personal-ai-agent/) · [Muse connectors](https://runtimewire.com/article/meta-opens-muse-connectors-developers) (2026-09-18) · [Connector doubts](https://parallel.ai/articles/meta-muse-custom-integrations) · [Muse in Singapore](https://mustsharenews.com/meta-personal-ai-agent-muse/) · [Muse privacy, Malwarebytes](https://malwarebytes.com/blog/privacy/2026/10/metas-muse-ai-files-away-your-friendships-arguments-and-secrets) (2026-10) · [Muse training default](https://captaincompliance.com/?p=13651) · [WhatsApp AI ban](https://techcrunch.com/2025/10/18/whatssapp-changes-its-terms-to-bar-general-purpose-chatbots-from-its-platform) (2025-10-18) · [Facebook embedded-browser sign-in](https://developers.facebook.com/blog/post/2021/06/28/deprecating-support-fb-login-authentication-android-embedded-browsers/) (2021-06-28) · [developer report of the block](https://developers.facebook.com/community/threads/195638179128499/) · [Account Integrity](https://transparency.meta.com/policies/community-standards/account-integrity) · [automation notices, third-party](https://admakeai.com/blog/meta-account-flagged-automation) · [Send Dialog](https://developers.facebook.com/docs/sharing/reference/send-dialog) (no date) · [Twilio SMS guide, third-party](https://automationatlas.io/answers/twilio-pricing-explained-2026/) · [Twilio 10DLC brand](https://www.twilio.com/docs/trust-hub/registrations/a2p-10dlc-brand) · [10DLC campaign vetting](https://support.twilio.com/hc/en-us/articles/11587910480155-A2P-10DLC-Campaign-Vetting-FAQ) · [Gmail audit cost](https://www.theregister.com/2019/02/11/google_gmail_developer/) (2019-02-11)

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
**Tests 1 to 4 and 9 need a real Facebook account, so workers can't run them.** Andy or a helper can settle them in about five minutes, with a friend who agrees.

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
| 9 | **Does Facebook let a person sign in inside Mary's window, and keep them signed in?** A coder builds a tiny test window from the app's own WebView2, with no scripts on the page. Try one account, once. | Use their normal browser (route 6). Never disguise the window. |

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
- **The smooth path, as Andy put it:** the card is on screen and they say "Now send it". If that person has one saved way, that's the yes. Mary says "To Mark, by email", and five seconds of Stop follow (board D3). That's all it takes.
- **The first time,** or with a new person or a choice of ways, the "last look" screen (board D2) comes first, showing the card, the person and the way.
- The core only sends if the card and the person were on screen and then a tap or a plain "send it" came back. A hint from Gemini isn't enough.
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
| Drawn cards, email from their account, Messenger, WhatsApp, print | Free |
| Text from a Mary number (future) | About 1.2 cents each, plus shared fees; see section 1 |
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
| **M15e** Messenger | Answers to the tests in section 2, Facebook in its own walled-off window, clipboard, open the chat, the Paste strip, "Did it go?"; fallback to their browser | Andy sends a real card to a friend in under a minute, with no key combo. No script touches Facebook's page. | Opus, after Andy's five-minute test |
| **M15f** Picture making | `ctx.make_picture`, a set cartoon style, plain lines for refusals, a cost line in My info | A picture lands in a card; a refusal fails politely; no names in the prompt | Opus for code; Sonnet for tests |
| **M15g** Outlook | Register the app, device-code sign-in, Graph send | A helper connects a test Outlook.com account | Opus, once test 7 is settled |
| **M15h** WhatsApp | The `wa.me` link, phone numbers in contacts | The chat opens with the words ready | Sonnet |
| **M15i** Google sign-in | Google verification, replace the Gmail app password | Verified, with no warning screen | Opus, plus Andy's review steps |
| **M15j** Replies, if Andy says yes | Check mail from saved family, only when asked; nothing in it can instruct her | A test proves unknown senders are never read, and text in a message can't trigger a tool | Opus, `xhigh` |
| **Backend items** | Mary's address and number, in `docs/backend-plan.md` | After the backend's security review | Later |

**Later, once there's funding (Andy, 2026-10-31):** write to Meta, Google and others about the mission, and ask for access.

Order: a, b, c, d, then e, then the rest. A helper-free resident gets cards, print and Messenger with no secret to set up.

**Setup for a helper, added to the setup list:** connect email, sort out the Messenger PIN, keep the browser signed in to Facebook, and add the family's contacts.

## 9. Decisions for Andy
### Settled by Andy (2026-10-31)
| Was # | Question | Andy's answer |
|---|---|---|
| 12 | Messenger inside Mary, or their browser? | **Route 4:** Facebook opens in the panel beside Mary, and the resident taps to send. Their browser stays only as the fallback if test 9 fails. |
| 2 (part) | What leads? | **Email leads,** and send directly wherever we can. |
| 5 | Print as a third way? | **Yes,** marked as needing facility help for the mailing. |
| 13 | Meta's Muse? | **Watch it.** It does handle Messenger, from Andy's own use. Whether an app can hand it a task is still open. The pilot-brain idea is roadmap M16. |

### Still open
| # | Question | Recommendation |
|---|---|---|
| 1 | How do residents paste in Messenger? | **Mary's big Paste button,** on the strip. It needs test 5. Voice Access is the fallback. |
| 2 | Which email company first? | **Gmail and Yahoo now,** then Outlook.com, then Google sign-in to retire the Gmail app password. |
| 3 | Drawn cards, made-to-order, or both? | **Both.** Drawn is the default, because it's free and offline. A new picture is one choice among them, and only with a paid key. |
| 4 | Does a spoken yes count, or must they tap? | **Either:** a tap or "send it", then five seconds to stop. Many residents can't tap well. |
| 6 | When does she ask to keep an address? | **Once, after the first send.** Never before they've used it. |
| 7 | WhatsApp and texting? | **WhatsApp later, as M15h. Texting through Phone Link not at all for now:** no pictures on iPhone, and heavy setup. |
| 8 | Does a message say Mary helped? | **No tag.** It's their message, from their account, in their words. If they ask, she's honest. |
| 9 | Reminders for who? | **Family and friends with a date the resident gave,** one week ahead, once a year. No reminders for the dead. Holidays only if they ask. |
| 10 | Mission wording on what leaves the laptop | **Update it** to say what Google keeps on the paid tier. |
| 11 | Your five-minute Facebook test | **Please do it before M15e.** It needs a friend who agrees, and it settles the five Facebook unknowns, above all test 9, which route 4 rests on. |
| 14 | Replies: "did my son write back?" | **Email only, from saved family, only when asked.** On Messenger she opens the chat for them. |
| 15 | Mary's own number and address, once the backend exists? | **Yes, add to `docs/backend-plan.md`.** It fits "send right to". The son is told first. |
