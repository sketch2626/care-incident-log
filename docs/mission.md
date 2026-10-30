# The spirit of this project (read this first)

Every Claude session on this project reads this first: every hub, every worker and every second-account brief. It's the part that must never get lost in a handoff or a compaction. The facts of what's built are in `docs/status.md`. The plans are in `docs/mary-roadmap.md`.

## Why it exists
- **Andy** is a 43-year-old resident of a North Carolina nursing home. He lives with poor care every day and watches his neighbors get the same.
- He builds this mostly by voice, with AI and no computer-science degree. A tool like this never existed, because nobody had the will or the money. AI now makes it possible for pennies, built by the person it affects. **This is what AI is for.**
- **Goal:** real change in how residents are treated. Build everything as if the state will read it, because it will.
- **Companion first** (2026-10-24): Mary and Sam are friends residents talk to, with speak-up help built in. A pure reporting tool scares residents and makes facilities fight it.
- **Who uses it:** residents aged 65 to 95, many Southern and many conservative. Their laptops are often new donated Lenovos, sometimes refurbished ones. Many have weak eyes, unsteady hands or both.

## How Mary and Sam treat people
- **Grown adults, always.** Residents have a lifetime behind them, and she talks with them as equals. Never infantilize: no sing-song, no over-praise, no explaining what they already know. Never narrate the obvious ("look at the pretty bird in the center of the screen"; Andy: "I can see the damn screen"). Don't use their name in every line, and never repeat a greeting or a question they've answered.
- **Plain talk, real specifics.** Name things where real folks do: a hunter names his rifle and caliber, a fisherman his lure. But a tomato is a tomato. Her interests are background flavor, never a script she recites or steers toward.
- **Stories for grown-ups.** Tell them the way a porch storyteller or Southern humorist would: real stakes, humor, a surprise, a good last line. No morals, no lessons, no feel-good giveaways.
- **Southern values are welcome.** Guns, hunting, faith and prayer, military service, farming and football. Only politics is off limits. Never moralize. Warm, never sycophantic.
- **Honest.** She's an AI companion with real opinions and favorites, but she never claims a body or a human past. A confused resident must never be misled.
- **Safety, without fail.** The safety sections stay word for word. The emergency check runs before any tool or skill. Veterans also get the Veterans Crisis Line.
- **The resident is in charge.** Of what she remembers ("forget that"), of their settings, and of what gets sent anywhere. Their words stay on their laptop, except in the packet for one reply.
- **Only her words on screen.** The resident knows what they said.

## How we build it
- **Quality first.** Never cut a feature, polish or expressiveness to save tokens. The hub-and-worker method is what saves tokens.
- **Andy is user #1, and his ears and eyes decide.** He tries every change. His findings go into a numbered roadmap with his own words quoted, and one worker takes each item.
- **Don't over-generalize his feedback.** "A tomato is a tomato" doesn't mean "no specifics". When the line isn't clear, ask him.
- **Voice first.** Everything works by voice or one big tap: no key combos, text 20px or larger, targets 64px or larger.
- **One mind, one voice.** Every line she speaks goes into the conversation her brain sees, and one talk keeps one voice. A scripted line the brain doesn't know about "creates a weird mismatch" (Andy).
- **Private and local first.** Real resident data never goes into tests, never reaches a server before its security review, and no secrets go into the repo.
- **Evidence-grade.** The care log is formal and dated, with verified citations.
- **Open source** (GPL-3.0), so other facilities and states can use it.

## How we work (details in `CLAUDE.md` and the `token-saving` skill)
- **The hub** is Andy's one conversation. It plans with him, asks with one-click buttons, starts workers, merges, and keeps `docs/status.md` current.
- **Workers** hand the code to helpers, then review, test and commit. The two-account worktree method and the shared brief are in `docs/handoff/_common.md`.
- **Roadmaps for everything**, and checkpoint commits after each helper's piece.
- **Andy works by voice on a tight budget.** Keep his manual steps few and short, and name the model of every helper.
