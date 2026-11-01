# How to make a skill for Mary

A skill is one thing Mary can do, like a coin flip, a crossword or a slower voice.
Each skill is a folder. Mary finds it when the app starts. You never edit her core to add one.
This project is licensed GPL-3.0. Your skill is released under the same license.

## 1. What a skill is

- The card (`manifest.json`) says what the skill is and what Mary can do with it.
- The code (`skill.py`) does the work.
- The page part (`screen.js`) draws on screen, if the skill has a screen.

## 2. The folder

```
skills/coin_flip/
  manifest.json   the card (required)
  skill.py        the code (required)
  screen.js       the page part (only if the card has "screen")
  screen.css      the page style (optional)
```

The folder name must match `name` in the card.

## 3. The tiny example: coin_flip

The full example is in `tests/skill_fixtures/coin_flip/`. It uses a screen, storage and `view`.

### manifest.json

```json
{
  "contract": 1,
  "name": "coin_flip",
  "version": "0.1.0",
  "title": "Coin flip",
  "summary": "Mary flips a coin and shows it on screen.",
  "instructions": "Offer it when they want to let chance decide something. Say heads or tails warmly.",
  "screen": {"menu_label": "Flip a coin", "menu_icon": "coin", "full_screen": false},
  "sees": true,
  "actions": [
    {
      "name": "flip",
      "description": "Flip a coin and show heads or tails on screen.",
      "inputSchema": {"type": "object", "properties": {}},
      "annotations": {"readOnlyHint": false, "destructiveHint": false},
      "offline_phrases": ["flip a coin"]
    },
    {
      "name": "set_coin",
      "description": "Choose which coin to show, for example a quarter.",
      "inputSchema": {"type": "object",
                      "properties": {"coin": {"type": "string", "enum": ["penny", "nickel", "dime", "quarter"],
                                              "description": "Which coin"}},
                      "required": ["coin"]},
      "annotations": {"readOnlyHint": false, "destructiveHint": false}
    }
  ],
  "storage": true,
  "needs": {"internet_hosts": [], "mic": false, "send_mail": false, "modes": ["live", "normal", "offline"]},
  "offline": "works",
  "default_on": true
}
```

- `contract` is the card format version. Use `1`.
- `name`, `version`, `title` and `summary` say who the skill is, in plain words.
- `instructions` tells Mary when to offer it. Keep it under 400 characters.
- `screen` sets the menu label and icon. `sees: true` means `view()` exists.
- `actions` lists what Mary can call. Each one has a description and an input schema. Give the text your action needs most as the first text field: when she passes plain words, that's where they go.
- `"always": true` on an action lets her use it from any group, with no opening. It's only for what residents need in the middle of anything, like louder and quieter. At most 4 on a card; keep it rare.
- `offline_phrases` are short phrases that work with no internet.
- `storage: true` gives the skill a private store. `needs` lists its internet hosts, mic, modes and whether it may send email.
- `offline` is `works` or `needs_internet`. `default_on` sets the start state.
- `vision: true` (optional) lets the skill ask Gemini about a picture with `ctx.look(image_bytes, mime, question)`.
- `memory: true` (optional) lets the skill read her memory with `ctx.recall(words)`. It gives back plain facts and can't change them. Never put those facts in a reply, in `view()` or in a log.
- `needs.send_mail: true` (optional) lets the skill send an email from the resident's own account with `ctx.send_mail(ticket, to, subject, body, pictures=())`. The skill never sees the password. Each email needs a one-time ticket, and only the core can mint one, from the resident's own "send it". Set `"slow": true` as well, because a send can take up to 12 seconds, and make the send the last thing the action does.

### skill.py

```python
"""Coin flip, a tiny test skill: flips a coin, counts flips in its store, and shows the coin on screen."""
import random


def flip(ctx):
    """Heads or tails, shown on screen, with a short line for offline mode."""
    side = random.choice(["heads", "tails"])
    count = (ctx.store.get("flips") or 0) + 1
    ctx.store.put("flips", count)
    ctx.state["last"] = side
    ctx.effect("show_screen", {"screen": "coin_flip"})
    ctx.effect("coin", {"side": side, "coin": ctx.state.get("coin", "quarter")})
    return {"side": side, "flips": count, "say": f"It's {side}."}


def set_coin(ctx, coin):
    """Which coin the screen shows."""
    ctx.state["coin"] = coin
    ctx.effect("coin", {"coin": coin})
    return {"coin": coin, "say": f"I'll use a {coin}."}


def on_event(ctx, event):
    """A tap on the coin flips it."""
    if event.get("type") == "tap":
        return flip(ctx)
    return {"ignored": True}


def view(state):
    """What Mary sees on the screen."""
    if "last" not in state:
        return "A coin, not flipped yet."
    return f"A {state.get('coin', 'quarter')} showing {state['last']}."
```

- `flip` picks a side, counts it in the store, and sends effects to the screen.
- `set_coin` changes which coin the screen shows.
- `on_event` lets a tap on the coin flip it.
- `view` is the short text Mary sees about the screen.

### screen.js

```javascript
// Coin flip's page half: shows the coin and plays its effects. All its state lives on the server.
MarySkills.register('coin_flip', {
  enter(el) {
    el.innerHTML = '<div class="coin-flip" aria-live="polite">Tap the coin to flip it</div>';
  },
  leave(el) {
    el.innerHTML = '';
  },
  effect(kind, data) {
    if (kind !== 'coin') return;
    const box = document.querySelector('.coin-flip');
    if (box && data.side) box.textContent = 'It\'s ' + data.side + '!';
  }
});
```

- `MarySkills.register` gives the page part its skill name.
- `enter` draws the box, and `leave` clears it.
- `effect` runs when the server sends a `coin` effect.

### Side by side with Mary

A skill that shows something big, like a picture or a game, can stand next to Mary instead of covering her. Add `aside: true` to `register`:

```js
MarySkills.register('my_game', { aside: true, enter(el) { /* draw */ }, leave(el) { /* clear */ } });
```

- Mary slides over to the left 40% of the window and turns toward your screen. She stays big, glances back and forth, and her words sit under her.
- Your box is the right 60% of the window. It has no padding or background, so her warm background shows through.
- Keep clear of the Menu button at the top right. Leave about 124px at the top and 290px at the right of that row.
- When your screen closes for any reason, even an emergency, she goes back to her full face. You don't call anything.

## 4. The rules

- **Safety first.** Emergencies never reach a skill. Mary's safety checks run before any skill.
- **A crash is contained.** If a skill crashes or hangs, it is switched off. Mary says "That's not working right now."
- **No network imports.** Skill code may not import `urllib`, `http`, `requests`, `socket` or similar.
- **Internet only through `ctx.fetch`.** It reaches only hosts in `needs.internet_hosts`. An empty list means no internet.
- **Email only through `ctx.send_mail`.** The card needs `needs.send_mail` and `"slow": true`, and every email needs a one-time ticket from the core. A skill can't mint a ticket, never sees the password, and may not import `mail_core` or `secret_store`.
- **Storage only through `ctx.store`** (small JSON values) **and `ctx.files`** (the skill's own folder). Do not open files or databases yourself. No skill can read another skill's data.
- **Showing a saved image.** A skill can show an image it saved in `ctx.files` at `/api/mary/skills/<name>/image/<file>` (jpg, png, gif, webp or svg). An svg can't run scripts or load anything from outside itself, so it has to carry its own fonts and pictures.
- **Files you ship with the skill.** `ctx.asset(name)` gives the bytes of a file in the skill's own `assets` folder. Subfolders are fine, and nothing outside that folder can be read.
- **Bundled fonts.** `ctx.font(file)` gives the bytes of a font in `web/mary/fonts`, by its bare file name, such as `cinzel.woff2`.
- **Printing.** `ctx.has_printer()` says whether this computer has a real printer. Offer printing only when it's true, and never ask the system yourself.
- **Settings only those listed.** A skill may change only the settings its card names.
- **No risky calls.** No `subprocess`, `sqlite3`, `importlib`, `open`, `exec`, `eval` or `__import__`.
- **Text limits.** `instructions` is 400 characters at most. Each description is 200 at most. `view()` is 600 at most.
- **Offline phrases.** Only on actions with no required inputs. No phrase may clash with another skill, or with the emergency or yes/no words. An action can read the whole line in `ctx.heard`, and it can answer `{"not_for_me": True}` when the phrase wasn't meant for it, so her normal offline line runs.

## 5. How Mary learns it

You do not edit her brain. When the app starts, it reads every card.
Each skill is one group. Her prompt always lists your `title` and `summary` in one line, so write the summary to say plainly what the skill is for. When the talk turns to it she opens your group with `open_skill`, which gives her your `instructions` and actions, and runs an action with `use_skill`. While your skill is on screen she has them without opening it.
This works the same in Live, Normal and Offline modes. Offline mode uses only the `offline_phrases`, which need no group.

A game adds `setAside: true` to its `MarySkills.register` call. Then a picture doesn't end it: its page is hidden just as it is, and comes back when the picture closes, with no `leave` or `enter` call. A skill on top of it can read `MarySkills.backLabel()` to name it on a Back button, and gets an optional `backChanged()` if the game ends while hidden.

## 6. Testing

Run `python run_tests.py -q`. It runs the contract tests on every folder in `skills/`. The ten checks are:

1. The card parses, has every field, its name matches the folder, and its contract is supported.
2. Function names are `<skill>__<action>`, at most 64 characters, and unique across all skills.
3. Input schemas use only the Gemini-safe subset, and every property has a description.
4. Text limits hold, and all shipped instructions fit the 4,000 character budget.
5. `skill.py` imports cleanly, has a handler for each action, and has `view` when `sees` is true.
6. Static safety: no banned imports or calls, checked from the source with `ast`.
7. Each action runs on a scratch store with no internet, returns small JSON, and `view()` stays under 600 characters.
8. Every effect is a known core kind or the skill's own name.
9. Offline phrases sit only on no-input actions, and none clash.
10. `screen.js` exists when `screen` is set, and registers its own name (checked with Node if Node is installed).

Checks 1-5 and 9 also run when the app starts, so a broken folder never loads.

## 7. Switching on and off

- A resident can switch any skill on or off by voice, for example "turn the crossword back on".
- A resident can also switch skills in My info.
- A helper can lock a skill during setup. A locked skill changes only in My info.
- Mary's emergency and safety rules are not skills. No skill can switch them off.

## 8. What loads

For now, only reviewed skills that ship in this repo are loaded. To add one, open a pull request with your folder. A reviewer checks it, and then it ships with the app.
