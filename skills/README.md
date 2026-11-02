# Skills

Each folder here is one skill: one thing Mary can do. Mary finds them when the app starts.
Skills are reviewed and live in this repo. Switches are in My info and by voice.

| Skill | What it does |
|---|---|
| [messages](messages/) | Makes greeting cards and short letters in the resident's own words, ready to print and saved on their laptop. Their address book is here too. |
| [pictures](pictures/) | Shows a picture from Wikipedia of what the resident asks to see, so Mary can talk about it. |
| [voice_comfort](voice_comfort/) | Makes Mary's voice slower, faster, quieter or louder, switches between Mary and Sam, and turns listening for their name on or off. |
| [word_search](word_search/) | A big-print word search on a topic they like, played by voice or by touch, with hints when they ask. |

## Making a new one
- Steps: [../docs/how-to-make-a-skill.md](../docs/how-to-make-a-skill.md)
- Design and rules: [../docs/skills-design.md](../docs/skills-design.md)
- Copy `voice_comfort`. It is the example to start from.
- `tests/test_skills_contract.py` must pass.

All four are current.
