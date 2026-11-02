# Tools

Helper scripts. None run inside the app while a resident uses it.

## Model downloaders
Each downloads from the official page and checks size and SHA-256. Run: `python -I tools/<name>`.
`packaging/build.py` runs all three when `models/` is missing.
| Script | Gets |
|---|---|
| `get_whisper_model.py` | Speech-to-text (faster-whisper base.en) |
| `get_voice_model.py` | Mary's offline voice (Kokoro-82M, int8) |
| `get_wake_model.py` | Wake-word model (Vosk small English 0.15) |

## Checks and benches
| Script | What it does |
|---|---|
| `brain_bench.py` | Scripted resident lines against the real brain, every reply graded. Needs a Gemini key. |
| `wake_bench.py` | Offline benchmark for "Hey Mary" / "Hey Sam". |
| `wake_try.py` | Try the wake words on the real microphone. |
| `laptop_check.py` | Times voice, speech and wake word on this laptop and shows the tier. |
| `mary_speed.py` | Can she start answering within about 2 seconds? Needs a Gemini key. |

## Card art (messages skill)
Both are marked not bundled.
| Script | What it does |
|---|---|
| `paint_card_fronts.py` | Paints the twelve card fronts. `--check` tests what is on disk. |
| `card_font_metrics.py` | Writes letter widths for the card fonts. Run only if a font changes. |

## Dev only
| Item | What it is |
|---|---|
| `testlist/` | Dev tool for the test list. Never bundled. |
| `worker_context.py` | Shows how full each worker's conversation is. Not part of the app. |
