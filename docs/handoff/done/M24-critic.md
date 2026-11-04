# Handoff: M24 critic, a hard look at the graphics plan (second account, branch `other/M24-critic`)

You are a strong, independent critic. Andy, 2026-11-04: "have a critic look at this entire plan and go through it and give recommendations on any conflicts and things like that. And just have a strong critic look at" it. Don't be polite and don't agree to agree. Find what will break, what conflicts, and what's missing, and say what to do instead. Andy wants honesty over comfort.

Read `docs/handoff/_common.md` first, then:
- `docs/mission.md`;
- `docs/decisions.md` (all of it);
- the **M24** section of `docs/mary-roadmap.md` (Andy's words, the plan and the redirect), plus **M23** (brains as modules) and **M17/M18** (how Mary moves when a screen opens);
- `docs/handoff/M24-boards.md`, the boards brief;
- the redirect the hub sent the boards worker, which you'll find below;
- only what you need of `web/mary/face.js`, `face.css`, `mary.css`, `mary/leaner.md` and `mary/lean.md` (her first lines), `desktop.py`, and `packaging/build.py` (what's bundled and the installer's size);
- `docs/status.md` "Right now".

**The plan under review.** Mary becomes a real-time 3D character on a 3D porch:
- built with three.js from shapes in code, and bundled offline later;
- sitting on a porch swing, with weather and time that match the real day, or that she changes when told;
- the scene moves left as a camera move when a screen opens;
- grown-up, never childish, and not a human woman. The three concepts are a Southern animal, an honest AI being, and a creature of the worker's own;
- Sam gets a character to match.

Andy wants it appealing enough that other people will want to help with the project.

**The redirect sent to the boards worker:** real-time 3D with three.js (pinned from cdnjs for the boards, bundled offline later), soft lighting, a clay or vinyl-toy finish, built from primitives with no downloaded models, and light enough for an old laptop. The three concepts are as above, each with a face that talks and listens and a body on the swing. Weather on the strongest concept, Sam, the move-left camera, and gentle motion stay. The design note covers bundling and running cost. The worker can't see what it renders.

**Look hard at, at least:**
- **conflicts with Andy's decisions** (D1 to D19) and the mission: residents 65 to 95, no infantilizing, the honesty rule, privacy, and facilities accepting it;
- **her brain and voice:** her instructions say she "talks like a warm Southern woman," and her voice is a woman's. What changes if she's an animal or a robot, and what does the name "Mary" mean on a non-human character?
- **the hardware:** old laptops short on memory. The machine this runs on had about 0.4 GB free, while running speech-to-text, a local voice and WebView2. What does WebGL add, and what happens when it fails or there's no GPU?
- **real weather:** it needs the internet and a town, against an offline, privacy-first app;
- **process:** 3D drawn blind by a worker that can't see it render; whether WebGL boards will show on the Design canvas at all; and the cost on a tight budget;
- **fit with what exists:** her moods and face tags, captions, the listening, talking and asleep states, "Back to Mary" (D13), the M23 module plan, the installer's size, and the GPL-3.0 license;
- **order of work:** whether this should wait for, or be shaped by, the paid-model choice and M23.

**Write `docs/handoff/done/M24-critique.md`:**
- a plain-words summary for Andy, five lines at most;
- the problems, ranked by how much they matter. For each: what breaks, why, and what to do instead;
- what you'd change in the boards brief right now, if anything;
- what's good about the plan and should stay.

**Rules:** read only, apart from that one file. No app changes, no Gemini calls, no browser. If your context passes about 150K, commit what you have as `WAITING: context full`.

**Models:** this is judgment work, so do it yourself. No helpers are needed.

**Finish:** commit `DONE: M24 critique`, with the five-line summary in the message. Then stop.
