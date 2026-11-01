from tests import helpers  # noqa: F401
"""Wake word ("Hey Mary" / "Hey Sam"): the two-stage Detector and the microphone Listener.

No real microphone or models: a fake sounddevice, a scripted fake Vosk recognizer and a
fake Whisper check.
"""
import json
import logging
import queue
import threading
import time
import unittest

import speech
import wakeword

np = speech.np
_LOG = logging.getLogger("care.wakeword")
_saved_log_disabled = _LOG.disabled


def setUpModule():
    _LOG.disabled = True  # the tests break things on purpose; keep the quiet run quiet


def tearDownModule():
    _LOG.disabled = _saved_log_disabled
RATE = wakeword.SAMPLE_RATE
BLOCK = RATE // 10                 # 0.1 s per block, like the real microphone
SILENCE = bytes(BLOCK * 2)         # one block of int16 silence
WAKE = ["hey mary"] * 6            # candidate on the 1st block, Whisper check 0.5 s later (6th)


class FakeRecognizer:
    """Stands in for vosk.KaldiRecognizer. Each AcceptWaveform() takes the next scripted
    entry: a string is a partial result, ("final", text) ends the phrase."""

    def __init__(self):
        self.lock = threading.Lock()
        self.grammar = None
        self.script = []
        self.blocks = []  # byte length of each block fed
        self.resets = 0
        self._out = json.dumps({"partial": ""})

    def say(self, *entries):
        with self.lock:
            self.script.extend(entries)

    def AcceptWaveform(self, data):
        with self.lock:
            self.blocks.append(len(data))
            entry = self.script.pop(0) if self.script else ""
        if isinstance(entry, tuple):
            self._out = json.dumps({"text": entry[1]})
            return True
        self._out = json.dumps({"partial": entry})
        return False

    def Result(self):
        return self._out

    def PartialResult(self):
        return self._out

    def Reset(self):
        with self.lock:
            self.resets += 1


class FakeConfirm:
    """Stands in for the Whisper check: returns `text` (or raises it if it is an exception)."""

    def __init__(self, text="Hey Mary."):
        self.text = text
        self.calls = []

    def __call__(self, audio):
        self.calls.append(audio)
        if isinstance(self.text, Exception):
            raise self.text
        return self.text


class FakeStream:
    def __init__(self, sd, **kw):
        self.sd, self.kw = sd, kw
        self.callback = kw["callback"]
        self.started = self.opened = self.closed = False

    def start(self):
        rate = self.kw.get("samplerate")
        if self.sd.fail_open or rate in self.sd.bad_rates:
            raise RuntimeError("PortAudio error")
        self.started = self.opened = True
        self.sd.log.append(("open", self.kw.get("dtype"), rate))

    def stop(self):
        self.started = False

    def close(self):
        if self.opened and not self.closed:
            self.sd.log.append(("close", self.kw.get("dtype")))
        self.closed = True

    def push(self, data=SILENCE):
        """One audio callback, as PortAudio would make it."""
        arr = np.frombuffer(data, dtype=np.int16).reshape(-1, 1)
        self.callback(arr, len(arr), None, None)


class FakeSD:
    class CallbackStop(Exception):
        pass

    def __init__(self):
        self.streams, self.log = [], []
        self.has_mic, self.fail_open, self.bad_rates, self.native = True, False, set(), RATE

    def query_devices(self, kind=None):
        if not self.has_mic:
            return {"max_input_channels": 0}
        return {"max_input_channels": 1, "default_samplerate": self.native}

    def InputStream(self, **kw):
        stream = FakeStream(self, **kw)
        self.streams.append(stream)
        return stream

    def _terminate(self):
        pass

    def _initialize(self):
        pass

    def live_wake(self):
        live = [s for s in self.streams if s.kw.get("dtype") == "int16" and s.started and not s.closed]
        return live[-1] if live else None


@unittest.skipIf(np is None, "numpy is not installed")
class DetectorTests(unittest.TestCase):
    def make(self, text="Hey Mary.", **kw):
        self.rec = FakeRecognizer()
        self.confirm = FakeConfirm(text)

        def factory(grammar):
            self.rec.grammar = grammar
            return self.rec

        return wakeword.Detector(recognizer_factory=factory, confirmer=self.confirm, **kw)

    def feed(self, det, *entries, extra=0):
        self.rec.say(*entries)
        events = []
        for _ in range(len(entries) + extra):
            events += det.feed(SILENCE)
        return events

    def test_grammar_is_the_two_names_plus_unknown(self):
        self.make()
        self.assertEqual(json.loads(self.rec.grammar), ["hey mary", "hey sam", "[unk]"])
        self.assertEqual(wakeword.GRAMMAR, ["hey mary", "hey sam", "[unk]"])

    def test_confirmed_wake_fires_once(self):
        det = self.make("Hey Mary.")
        script = ["", "hey", "hey mary"] + ["hey mary [unk]"] * 6 + [("final", "hey mary [unk]"), "", ""]
        events = self.feed(det, *script)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["name"], "mary")
        self.assertEqual(ev["confirm_text"], "Hey Mary.")
        self.assertIn("hey mary", ev["stage1_text"])
        self.assertAlmostEqual(ev["audio_t"], 0.8)  # candidate at 0.3 s + 0.5 s wait
        self.assertIsInstance(ev["confirm_ms"], float)
        self.assertEqual(len(self.confirm.calls), 1)
        clip = self.confirm.calls[0]
        self.assertEqual(clip.dtype, np.float32)
        self.assertEqual(len(clip), 8 * BLOCK)  # all 0.8 s so far (less than the 2.5 s window)
        stats = det.stats()
        self.assertEqual((stats["candidates"], stats["confirmed"], stats["rejected"]), (1, 1, 0))
        self.assertGreaterEqual(self.rec.resets, 1)

    def test_clip_is_the_last_two_and_a_half_seconds(self):
        det = self.make("Hey Mary.")
        self.feed(det, *[""] * 40)  # 4 s of audio first
        self.feed(det, *WAKE)
        self.assertEqual(len(self.confirm.calls[0]), int(wakeword.CONFIRM_SECONDS * RATE))

    def test_whisper_rejects_look_alikes(self):
        for heard in ("Hey man, how is it going?", "Hey Larry, pass the salt.", "Hey, marry me.",
                      "Merry Christmas.", ""):
            with self.subTest(heard=heard):
                det = self.make(heard)
                self.assertEqual(self.feed(det, *["hey mary [unk]"] * 6), [])
                self.assertEqual(len(self.confirm.calls), 1)
                self.assertEqual(det.stats()["rejected"], 1)
                self.assertEqual(det.stats()["confirmed"], 0)
                self.assertGreaterEqual(self.rec.resets, 1)

    def test_confirm_pattern(self):
        for text in ("Hey Mary.", "Hey, Mary!", "hi mary", "Okay Mary,", "OK, Sam.", "hey marie", "Hey Sam",
                     "Mary had a lamb", "and and Mary can you and and and", "Mary ain't a m-",
                     "Mary 8 and Miss Sam"):  # the last four: the bare name early on; Vosk already heard it
            with self.subTest(text=text):
                self.assertIsNotNone(wakeword.CONFIRM_RE.search(text.lower()))
        for text in ("Hey man", "Hey Larry", "Hey, marry me", "Merry Christmas",
                     "Hey Samuel", "hey maryland", "The menu is uhh", "the cord she automatically went."):
            with self.subTest(text=text):
                self.assertIsNone(wakeword.CONFIRM_RE.search(text.lower()))

    def test_marry_is_not_a_candidate(self):
        det = self.make()
        script = ["[unk] mary [unk]"] * 8 + [("final", "[unk] mary [unk]")]
        self.assertEqual(self.feed(det, *script), [])
        self.assertEqual(det.stats()["candidates"], 0)
        self.assertEqual(self.confirm.calls, [])

    def test_hey_sam(self):
        det = self.make("Hey Sam.")
        events = self.feed(det, *["hey sam"] * 6)
        self.assertEqual([e["name"] for e in events], ["sam"])

    def test_end_of_phrase_confirms_without_waiting(self):
        det = self.make("Hey Mary!")
        events = self.feed(det, "hey mary", ("final", "hey mary"))
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0]["audio_t"], 0.2)

    def test_refractory_ignores_the_name_for_two_seconds(self):
        det = self.make("Hey Mary.")
        self.assertEqual(len(self.feed(det, *WAKE)), 1)
        self.assertEqual(self.feed(det, *WAKE), [])  # said again at once: ignored, never checked
        self.assertEqual(len(self.confirm.calls), 1)
        self.feed(det, *[""] * 20)  # 2 s later
        self.assertEqual(len(self.feed(det, *WAKE)), 1)
        self.assertEqual(len(self.confirm.calls), 2)

    def test_stage_one_only_wakes_on_every_candidate(self):
        det = self.make(confirm=False)
        events = self.feed(det, "", "hey mary")
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]["confirm_text"])
        self.assertAlmostEqual(events[0]["audio_t"], 0.2)
        self.assertEqual(self.confirm.calls, [])

    def test_candidate_and_rejected_hooks(self):
        det = self.make("Hey man, how is it going?")
        seen = []
        det.on_candidate = lambda info: seen.append(("heard", dict(info), len(self.confirm.calls)))
        det.on_rejected = lambda info: seen.append(("almost", dict(info), len(self.confirm.calls)))
        self.assertEqual(self.feed(det, "", *["hey mary [unk]"] * 6), [])
        self.assertEqual([k for k, _i, _n in seen], ["heard", "almost"])
        heard, almost = seen[0][1], seen[1][1]
        self.assertEqual(seen[0][2], 0)  # told before Whisper was asked
        self.assertEqual((heard["name"], heard["audio_t"]), ("mary", 0.2))
        self.assertEqual((almost["confirm_text"], almost["name"]), ("Hey man, how is it going?", "mary"))
        self.assertIsInstance(almost["confirm_ms"], float)
        det.on_candidate = det.on_rejected = lambda info: 1 / 0  # a broken hook never breaks feed()
        self.confirm.text = "Hey Mary."
        self.feed(det, *[""] * 20)
        self.assertEqual(len(self.feed(det, *WAKE)), 1)

    def test_one_name_detector_ignores_the_other(self):
        det = self.make("Hey Mary.", names=("sam",))
        self.assertEqual(json.loads(self.rec.grammar), ["hey sam", "[unk]"])
        self.assertEqual(self.feed(det, *WAKE), [])
        self.assertEqual(self.confirm.calls, [])
        self.confirm.text = "Hey Sam."
        self.assertEqual([e["name"] for e in self.feed(det, *["hey sam"] * 6)], ["sam"])

    def test_failed_check_is_no_wake_and_sets_problem(self):
        det = self.make(RuntimeError("model broke"))
        self.assertEqual(self.feed(det, *WAKE), [])
        self.assertEqual(det.stats()["errors"], 1)
        self.assertTrue(det.problem)
        self.confirm.text = "Hey Mary."
        self.assertEqual(len(self.feed(det, *WAKE)), 1)
        self.assertIsNone(det.problem)


@unittest.skipIf(np is None, "numpy is not installed")
class ListenerTests(unittest.TestCase):
    def setUp(self):
        self.sd = FakeSD()
        self.saved = (speech._sd, speech._sd_loaded, speech._missing_dependency, speech.warm_up,
                      wakeword._listener, wakeword.REOPEN_RETRY_S, wakeword._vosk_installed)
        speech._sd, speech._sd_loaded = self.sd, True
        speech._missing_dependency = lambda: None
        speech.warm_up = lambda: None  # never load the real speech model
        wakeword.REOPEN_RETRY_S = 0.05
        self.rec = FakeRecognizer()
        self.confirm = FakeConfirm("Hey Mary.")
        self.grammars = []  # the grammar of each Detector the listener built
        self.L = wakeword._Listener(detector_factory=lambda names: wakeword.Detector(
            names=names, recognizer_factory=lambda grammar: self.grammars.append(json.loads(grammar)) or self.rec,
            confirmer=self.confirm))
        wakeword._listener = self.L
        self.heard = []

    def tearDown(self):
        self.L.stop()
        with speech._rec_lock:
            if speech._rec is not None:
                speech._rec.abort()
                speech._rec = None
        (speech._sd, speech._sd_loaded, speech._missing_dependency, speech.warm_up,
         wakeword._listener, wakeword.REOPEN_RETRY_S, wakeword._vosk_installed) = self.saved

    def wait_for(self, check, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = check()
            if value:
                return value
            time.sleep(0.01)
        self.fail("timed out waiting")

    def started(self):
        self.L.start(on_wake=self.heard.append)
        return self.wait_for(self.sd.live_wake)

    def say(self, stream, *entries):
        self.rec.say(*entries)
        for _ in entries:
            stream.push()

    def test_wake_event_reaches_wait_and_callback(self):
        s = self.started()
        self.assertEqual((s.kw["samplerate"], s.kw["channels"], s.kw["dtype"], s.kw["blocksize"]),
                         (16000, 1, "int16", 1600))
        self.say(s, *WAKE)
        ev = self.L.wait(0, timeout=3)
        self.assertIsNotNone(ev)
        self.assertEqual((ev["seq"], ev["name"], ev["companion"]), (1, "mary", "mary"))
        st = self.L.status()
        self.assertEqual((st["enabled"], st["running"], st["listening"], st["wakes"]), (True, True, True, 1))
        self.assertEqual((st["paused_by"], st["problem"], st["last"]["seq"]), ([], None, 1))
        self.wait_for(lambda: self.heard)
        self.assertEqual(self.heard[0]["seq"], 1)
        self.assertIsNone(self.L.wait(1, timeout=0.1))

    def test_whisper_rejection_gives_no_event(self):
        self.confirm.text = "Hey man, how is it going?"
        s = self.started()
        self.say(s, *["hey mary [unk]"] * 6)
        self.wait_for(lambda: self.confirm.calls)
        self.assertIsNone(self.L.wait(0, timeout=0.2))
        self.assertEqual(self.L.status()["wakes"], 0)

    def test_only_the_chosen_companion_name_wakes(self):
        self.L.set_companion("him")
        self.confirm.text = "Hey Sam."
        s = self.started()
        self.assertEqual(self.grammars, [["hey sam", "[unk]"]])
        self.say(s, *["hey sam"] * 6)
        ev = self.L.wait(0, timeout=3)
        self.assertEqual((ev["name"], ev["companion"]), ("sam", "sam"))
        self.confirm.text = "Hey Mary."
        self.say(s, *[""] * 20)  # past the 2 s after a wake
        self.say(s, *WAKE)  # "Hey Mary" while Sam is chosen: not even a candidate
        self.assertIsNone(self.L.wait(1, timeout=0.3))
        self.assertEqual(len(self.confirm.calls), 1)
        self.L.set_companion("mary")  # the worker builds a Mary detector
        self.wait_for(lambda: len(self.grammars) == 2)
        self.assertEqual(self.grammars[1], ["hey mary", "[unk]"])
        self.assertTrue(self.wait_for(lambda: self.L.status()["running"]))
        self.say(s, *WAKE)
        ev = self.L.wait(1, timeout=3)
        self.assertEqual((ev["seq"], ev["name"], ev["companion"]), (2, "mary", "mary"))

    def test_heard_and_almost_notes(self):
        notes = []
        self.L.start(on_note=notes.append)
        s = self.wait_for(self.sd.live_wake)
        self.confirm.text = "Hey man, how is it going?"
        self.say(s, *["hey mary [unk]"] * 6)
        self.wait_for(lambda: len(notes) >= 2)
        self.assertEqual([n["type"] for n in notes], ["heard", "almost"])
        self.assertEqual((notes[0]["name"], notes[0]["companion"]), ("mary", "mary"))
        self.assertEqual(notes[1]["confirm_text"], "Hey man, how is it going?")
        self.assertIsNone(self.L.wait(0, timeout=0.1))
        self.confirm.text = "Hey Mary."
        self.say(s, *WAKE)
        self.assertIsNotNone(self.L.wait(0, timeout=3))
        self.assertEqual([n["type"] for n in notes], ["heard", "almost", "heard"])

    def test_pause_closes_stream_and_resume_reopens(self):
        s = self.started()
        self.L.pause("speaking")
        self.assertTrue(s.closed)  # released before pause() returns
        st = self.L.status()
        self.assertEqual((st["listening"], st["paused_by"]), (False, ["speaking"]))
        n_fed = len(self.rec.blocks)
        resets = self.rec.resets
        s.push()  # late audio from the closed stream is ignored
        s.push()
        self.L.resume("speaking")
        s2 = self.wait_for(lambda: self.sd.live_wake() not in (None, s) and self.sd.live_wake())
        s2.push()
        self.wait_for(lambda: len(self.rec.blocks) > n_fed)
        time.sleep(0.05)
        self.assertEqual(len(self.rec.blocks), n_fed + 1)
        self.assertGreater(self.rec.resets, resets)  # recognizer reset for the fresh stream
        self.assertEqual(self.L.status()["paused_by"], [])

    def test_overlapping_pause_reasons(self):
        self.started()
        self.L.pause("speaking")
        self.L.pause("call")
        self.L.resume("speaking")
        time.sleep(0.3)
        self.assertIsNone(self.sd.live_wake())
        self.assertEqual(self.L.status()["paused_by"], ["call"])
        self.L.resume("call")
        self.wait_for(self.sd.live_wake)

    def test_voice_typing_pauses_and_resumes_wake_word(self):
        s = self.started()
        speech.start()
        self.assertTrue(s.closed)
        st = self.L.status()
        self.assertEqual((st["listening"], st["paused_by"]), (False, ["listen"]))
        log = self.sd.log
        self.assertLess(log.index(("close", "int16")), log.index(("open", "float32", 16000)))
        speech.stop()
        self.wait_for(lambda: self.L.status()["listening"])
        self.assertEqual(self.L.status()["paused_by"], [])

    def test_failed_voice_typing_start_does_not_leave_wake_word_paused(self):
        self.started()
        self.sd.has_mic = False
        with self.assertRaises(RuntimeError):
            speech.start()
        self.assertNotIn("listen", self.L.status()["paused_by"])

    def test_queue_overflow_drops_oldest_and_callback_never_raises(self):
        q = queue.Queue(maxsize=3)
        cb = self.L._callback_for(7, RATE, q)
        for i in range(5):
            cb(np.full((BLOCK, 1), i, dtype=np.int16), BLOCK, None, None)
        items = [q.get_nowait() for _ in range(3)]
        self.assertTrue(q.empty())
        self.assertEqual([int(np.frombuffer(data, dtype=np.int16)[0]) for _g, _r, data in items], [2, 3, 4])
        self.assertEqual(self.L._dropped, 2)
        cb(None, 0, None, None)  # broken input: must not raise

    def test_reopen_failure_sets_problem_then_recovers(self):
        self.sd.has_mic = False
        self.L.start()
        st = self.wait_for(lambda: (lambda s: s if s["problem"] else None)(self.L.status()))
        self.assertFalse(st["listening"])
        self.assertIn("microphone", st["problem"].lower())
        self.assertIn("Mary", st["problem"])
        self.sd.has_mic = True
        self.wait_for(lambda: self.L.status()["listening"])
        self.assertIsNone(self.L.status()["problem"])
        self.L.pause("x")
        self.sd.fail_open = True
        self.L.resume("x")
        st = self.wait_for(lambda: (lambda s: s if s["problem"] else None)(self.L.status()))
        self.assertIn("could not be used", st["problem"])
        self.sd.fail_open = False
        self.wait_for(lambda: self.L.status()["listening"])

    def test_native_rate_fallback_is_resampled(self):
        self.sd.bad_rates = {16000}
        self.sd.native = 48000
        s = self.started()
        self.assertEqual((s.kw["samplerate"], s.kw["blocksize"]), (48000, 4800))
        s.push(bytes(4800 * 2))
        self.wait_for(lambda: self.rec.blocks)
        self.assertEqual(self.rec.blocks[0], BLOCK * 2)

    def test_wait_long_poll_and_timeout(self):
        s = self.started()
        t0 = time.monotonic()
        self.assertIsNone(self.L.wait(0, timeout=0.2))
        self.assertGreaterEqual(time.monotonic() - t0, 0.15)
        got = []
        waiter = threading.Thread(target=lambda: got.append(self.L.wait(0, timeout=5)))
        waiter.start()
        time.sleep(0.05)
        self.say(s, *WAKE)
        waiter.join(5)
        self.assertEqual(got[0]["seq"], 1)
        got.clear()
        waiter = threading.Thread(target=lambda: got.append(self.L.wait(1, timeout=10)))
        waiter.start()
        time.sleep(0.05)
        self.L.stop()  # a waiting long-poll returns at once
        waiter.join(2)
        self.assertFalse(waiter.is_alive())
        self.assertEqual(got, [None])

    def test_stop_joins_worker_and_restart_works(self):
        s = self.started()
        thread = self.L._thread
        self.L.stop()
        self.assertFalse(thread.is_alive())
        self.assertTrue(s.closed)
        st = self.L.status()
        self.assertEqual((st["enabled"], st["running"], st["listening"]), (False, False, False))
        s2 = self.started()
        self.assertIsNot(s2, s)

    def test_detector_that_cannot_start_sets_problem(self):
        def broken(names):
            raise RuntimeError("no model")
        self.L = wakeword._Listener(detector_factory=broken)
        wakeword._listener = self.L
        self.L.start()
        st = self.wait_for(lambda: (lambda s: s if s["problem"] else None)(self.L.status()))
        self.assertFalse(st["running"])
        self.assertIn("could not start", st["problem"])

    def test_available_and_real_start_report_missing_vosk(self):
        wakeword._vosk_installed = lambda: False
        ok, reason = wakeword.available()
        self.assertFalse(ok)
        self.assertIn("Hey Mary", reason)
        with self.assertRaises(RuntimeError):
            wakeword._Listener().start()


if __name__ == "__main__":
    unittest.main()
