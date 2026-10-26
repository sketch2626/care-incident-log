from tests import helpers  # noqa: F401
"""Live voice-activity reading (speech._Recording meter + GET /api/listen/level).

No microphone: synthetic chunks are fed straight to the audio callback with a fake clock.
"""
import unittest

import server
import speech
from tests.helpers import api

np = speech.np
RATE = speech.SAMPLE_RATE
CHUNK = RATE // 10  # 0.1 s per callback


class _FakeSD:
    class CallbackStop(Exception):
        pass


class _FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _noise(rng, rms, n=CHUNK):
    return (rng.standard_normal(n) * rms).astype(np.float32)


def _tone(rng, amplitude, start, n=CHUNK, noise_rms=0.0005):
    t = (start + np.arange(n)) / RATE
    wave = amplitude * np.sin(2 * np.pi * 300 * t)
    return (wave + rng.standard_normal(n) * noise_rms).astype(np.float32)


@unittest.skipIf(np is None, "numpy is not installed")
class VoiceActivityTests(unittest.TestCase):
    def setUp(self):
        self.clock = _FakeClock()
        self._saved_clock = speech._clock
        speech._clock = self.clock
        self.rec = speech._Recording(_FakeSD())
        self.rng = np.random.default_rng(1234)
        self.pos = 0  # samples fed so far, keeps the tone phase continuous

    def tearDown(self):
        speech._clock = self._saved_clock

    def feed(self, chunk):
        """One audio callback: the clock moves on by the chunk's length first."""
        self.clock.t += len(chunk) / RATE
        self.rec._callback(chunk.reshape(-1, 1), len(chunk), None, None)
        self.pos += len(chunk)
        return self.rec.reading()

    def feed_silence(self, seconds, rms=0.0005):
        out = None
        for _ in range(int(round(seconds * 10))):
            out = self.feed(_noise(self.rng, rms))
            self.assertTrue(0.0 <= out["level"] <= 1.0)
        return out

    def feed_tone(self, seconds, amplitude=0.05):
        out = None
        for _ in range(int(round(seconds * 10))):
            out = self.feed(_tone(self.rng, amplitude, self.pos))
            self.assertTrue(0.0 <= out["level"] <= 1.0)
        return out

    def test_starts_with_no_voice_and_quiet_counts_from_start(self):
        r = self.rec.reading()
        self.assertTrue(r["recording"])
        self.assertFalse(r["heard_voice"])
        self.assertEqual(r["quiet_s"], 0.0)
        r = self.feed_silence(1.0)
        self.assertFalse(r["heard_voice"])
        self.assertAlmostEqual(r["quiet_s"], 1.0, delta=0.05)
        self.assertAlmostEqual(r["elapsed_s"], 1.0, delta=0.05)
        self.assertLess(r["level"], 0.2)

    def test_speech_then_silence(self):
        self.feed_silence(0.5)
        r = self.feed_tone(0.2)
        self.assertFalse(r["heard_voice"])  # 0.2 s is not yet "someone spoke"
        r = self.feed_tone(0.8)
        self.assertTrue(r["heard_voice"])
        self.assertLess(r["quiet_s"], 0.15)
        self.assertGreater(r["level"], 0.4)
        quiet = []
        for _ in range(20):  # 2 s of trailing silence
            quiet.append(self.feed(_noise(self.rng, 0.0005))["quiet_s"])
        self.assertEqual(quiet, sorted(quiet))
        self.assertAlmostEqual(quiet[9], 1.0, delta=0.15)
        self.assertGreaterEqual(quiet[-1], 1.4)
        self.assertAlmostEqual(quiet[-1], 2.0, delta=0.15)
        r = self.rec.reading()
        self.assertTrue(r["heard_voice"])  # stays true after the voice stops
        self.assertLess(r["level"], 0.1)   # meter has settled back down
        self.assertAlmostEqual(r["elapsed_s"], 3.5, delta=0.05)

    def test_steady_background_noise_is_never_voice(self):
        for rms in (0.0005, 0.003, 0.01, 0.03):
            with self.subTest(noise_rms=rms):
                self.setUp()
                r = self.feed_silence(6.0, rms=rms)
                self.assertFalse(r["heard_voice"])
                self.assertEqual(self.rec.voice_s, 0.0)
                self.assertGreater(r["quiet_s"], 5.9)

    def test_faint_speech_on_a_quiet_laptop_mic_still_counts(self):
        self.feed_silence(0.5)
        r = self.feed_tone(0.6, amplitude=0.0057)  # about 0.004 RMS
        self.assertTrue(r["heard_voice"])

    def test_speech_over_steady_background_noise(self):
        self.feed_silence(2.0, rms=0.01)
        r = self.feed_tone(0.8, amplitude=0.12)
        self.assertTrue(r["heard_voice"])
        r = self.feed_silence(1.5, rms=0.01)
        self.assertGreaterEqual(r["quiet_s"], 1.4)

    def test_speech_with_pauses_from_the_very_first_chunk_is_heard(self):
        # The person talks the moment the mic opens: the first chunk may be speech, so the
        # starting background estimate is capped and drops at the first short pause.
        for _ in range(4):
            self.feed_tone(0.3)
            r = self.feed_silence(0.1)
        self.assertTrue(r["heard_voice"])

    def test_full_scale_audio_keeps_level_in_range(self):
        loud = np.ones(CHUNK, dtype=np.float32)
        for _ in range(10):
            r = self.feed(loud)
            self.assertTrue(0.0 <= r["level"] <= 1.0)
        self.assertEqual(r["level"], 1.0)

    def test_a_bad_chunk_never_raises_in_the_audio_callback(self):
        self.rec._callback(np.zeros((0, 1), dtype=np.float32), 0, None, None)
        self.rec._meter(None)  # not even an array
        self.assertFalse(self.rec.reading()["heard_voice"])


class LevelRouteTests(unittest.TestCase):
    """helpers.py sets server._speech = False so tests never open the mic; swap the real module in
    only for the level route, which just reads the recording state."""

    def test_without_speech_engine_reading_is_all_zeros(self):
        status, body, _ = api("GET", "/api/listen/level", tracker=False)
        self.assertEqual(status, 200)
        self.assertEqual(body, {"recording": False, "level": 0, "heard_voice": False,
                                "quiet_s": 0, "elapsed_s": 0})

    @unittest.skipIf(np is None, "numpy is not installed")
    def test_idle_with_speech_engine_reading_is_all_zeros(self):
        server._speech = speech
        try:
            status, body, _ = api("GET", "/api/listen/level", tracker=False)
        finally:
            server._speech = False
        self.assertEqual(status, 200)
        self.assertIs(body["recording"], False)
        self.assertIs(body["heard_voice"], False)
        for key in ("level", "quiet_s", "elapsed_s"):
            self.assertEqual(body[key], 0)

    @unittest.skipIf(np is None, "numpy is not installed")
    def test_route_reports_a_recording_in_progress(self):
        rec = speech._Recording(_FakeSD())
        server._speech = speech
        with speech._rec_lock:
            speech._rec = rec
        try:
            status, body, _ = api("GET", "/api/listen/level", tracker=False)
        finally:
            with speech._rec_lock:
                speech._rec = None
            server._speech = False
        self.assertEqual(status, 200)
        self.assertIs(body["recording"], True)
        self.assertEqual(set(body), {"recording", "level", "heard_voice", "quiet_s", "elapsed_s"})
        self.assertIs(body["heard_voice"], False)


if __name__ == "__main__":
    unittest.main()
