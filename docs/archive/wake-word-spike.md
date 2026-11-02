> **Archived 2026-11-02:** the measurements behind the M6 wake-word choice. The choice is made and built (`wakeword.py`), so this is the record of why.

# M6 wake word spike (2026-10-30, second account)

Measured on Andy's laptop (Ryzen 5 7520U, 8 threads, 5.7 GB RAM; only about 0.5 GB free during the runs, so the Whisper timings are on the slow side).

## Options tried
- **openWakeWord:** there is no ready-made "hey mary" / "hey sam" model. Making one means training on tens of thousands of synthetic clips plus a large noise/speech set (gigabytes). That's about an hour on a GPU (for example a free Colab notebook); it isn't practical on this laptop. For comparison, the ready-made `hey_jarvis` model costs 6.8% of one core. It's the upgrade path if the TV turns out to be a real problem.
- **Vosk** (`vosk-model-small-en-us-0.15`, 41 MB download, 68 MB on disk) with the grammar `["hey mary", "hey sam", "[unk]"]`: very cheap and catches every "Hey Mary", but on its own it wakes on "Hey man", "Hey Larry", "Hey Barry", "Hail Mary" and sometimes TV talk (420 an hour in the TV stream).
- **Chosen: Vosk, then Whisper checks** (`wakeword.py`). Vosk proposes, and the app's own on-device Whisper (base.en, already bundled) reads the last 2.5 s. It must write "hey/hi/ok Mary|Sam". Whisper wrote "marry", "Merry", "man" and "Larry" correctly every time.

## Numbers (quick bench, 4 voices x 6 wake phrases + 29 look-alike/TV lines)
| Condition | Vosk only: hits / false | Vosk + Whisper: hits / false |
|---|---|---|
| Clean | 24/24 / 26 of 116 | **24/24 / 0 of 116** |
| Across the room (-18 dB + echo) | 24/24 / 39 | **24/24 / 0** |
| TV on (3 talkers, 5 dB below the speaker) | 17/24 / 30 | 4/24 / 0 |
| TV on (1 talker, 10 dB below) | 21/24 / 50 | 7/24 / 1 |
| 2 min of TV talk, no wake phrase | 14 false wakes (420/h) | **0** |

- **Idle CPU on the real mic:** 3.7% of one core (about 0.5% of the whole CPU). With the TV on, Whisper checks run every few seconds, which adds a lot more CPU while the TV talks.
- **RAM:** Vosk +126 MB; Whisper is shared with voice typing (about +110 MB working, 440 MB peak while it loads).
- **Delay:** Vosk spots the phrase about when it ends. Whisper's check then takes about 1.1 s with free memory, 2-4 s when memory is tight. So the "I'm listening" glow can show at once, and listening starts when the check passes.
- **Tried and dropped:** sound-alike decoys in the Vosk grammar (fewer false candidates, but fewer TV hits), and a "Hey Mary. Hey Sam." hint for Whisper (false wakes on "Hey Barry", "Hail Mary", "Sam's Club").

## The weak spot
Speech-like TV noise. The synthetic TV test is harsh, because the TV voices are the same synthetic voices as the speaker, but it's the real risk. Andy's real-room test decides whether this is good enough or openWakeWord training is worth it.

## Tools
- `python tools/wake_try.py` (`--minutes 3` each part): part 1 counts false wakes with the TV on, part 2 counts "HEARD YOU"s. Results go to `%TEMP%\wake_try_results.txt`.
- `python tools/wake_bench.py [--quick] [--live 60] [--stream-min N]`: the synthetic bench. Needs about 1 GB of free RAM; the full run takes 20-40 minutes.
- `python tools/get_wake_model.py`: fetches the Vosk model (checked by SHA-256).
