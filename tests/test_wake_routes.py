from tests import helpers  # noqa: F401
"""M6: the wake word routes (/api/wake/wait, /api/wake/hold, /api/wake/status), the wake_word setting,
the poll lease, the page hold, the pause after a wake and wake.log.

No real microphone or models: the fake sounddevice, Vosk recognizer and Whisper check from test_wakeword.
"""
import json
import logging
import time
import unittest

import server
import speech
import wakeword
from tests.test_wakeword import FakeConfirm, FakeRecognizer, FakeSD

np = speech.np
_LOG = logging.getLogger("care.wakeword")
CONSTS = ("WAKE_WAIT_S", "WAKE_LEASE_S", "WAKE_HOLD_S", "WAKE_WOKE_S", "WAKE_TICK_S", "WAKE_LOG_MAX", "DATA")


@unittest.skipIf(np is None, "numpy is not installed")
class WakeRouteTests(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        self.saved = (speech._sd, speech._sd_loaded, speech._missing_dependency, speech.warm_up,
                      wakeword._listener, wakeword.REOPEN_RETRY_S, wakeword.available, wakeword._vosk_installed,
                      server.WAKE, _LOG.disabled, {k: getattr(server, k) for k in CONSTS})
        _LOG.disabled = True  # the tests break things on purpose; keep the quiet run quiet
        self.sd = FakeSD()
        speech._sd, speech._sd_loaded = self.sd, True
        speech._missing_dependency = lambda: None
        speech.warm_up = lambda: None  # never load the real speech model
        wakeword.REOPEN_RETRY_S = 0.05
        wakeword.available = lambda: (True, "")
        self.rec, self.confirm, self.grammars = FakeRecognizer(), FakeConfirm("Hey Mary."), []
        self.L = wakeword._Listener(detector_factory=lambda names: wakeword.Detector(
            names=names, recognizer_factory=lambda g: self.grammars.append(json.loads(g)) or self.rec,
            confirmer=self.confirm))
        wakeword._listener = self.L
        server.WAKE = server.WakeLink()
        server.WAKE_WAIT_S, server.WAKE_TICK_S = 2.0, 0.05
        self.log = server.DATA / "wake.log"
        for p in (self.log, server.DATA / "wake.log.1"):
            p.unlink(missing_ok=True)

    def tearDown(self):
        server.WAKE.stop("test over")
        self.L.stop()
        (speech._sd, speech._sd_loaded, speech._missing_dependency, speech.warm_up,
         wakeword._listener, wakeword.REOPEN_RETRY_S, wakeword.available, wakeword._vosk_installed,
         server.WAKE, _LOG.disabled, consts) = self.saved
        for k, v in consts.items():
            setattr(server, k, v)
        for p in (self.log, server.DATA / "wake.log.1"):
            p.unlink(missing_ok=True)

    # ---- helpers ----
    def wait_for(self, check, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = check()
            if value:
                return value
            time.sleep(0.01)
        self.fail("timed out waiting")

    def poll(self, after=0, wait=None):
        if wait is not None:
            server.WAKE_WAIT_S = wait
        status, body, _ = helpers.api("GET", f"/api/wake/wait?after={after}")
        self.assertEqual(status, 200)
        return body

    def status(self):
        return helpers.api("GET", "/api/wake/status")[1]

    def hold(self, on, **kw):
        return helpers.api("POST", "/api/wake/hold", {"on": on}, **kw)

    def put(self, **settings):
        self.assertEqual(helpers.api("PUT", "/api/settings", settings)[0], 200)

    def say(self, stream, *entries):
        self.rec.say(*entries)
        for _ in entries:
            stream.push()

    def opened(self):
        """First poll: the listener starts and opens the (fake) microphone."""
        seq = self.poll(0, wait=0.05)["seq"]
        return seq, self.wait_for(self.sd.live_wake)

    def log_lines(self):
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    # ---- the setting ----
    def test_setting_defaults_on_and_takes_1_or_0(self):
        mary = lambda: helpers.api("GET", "/api/mary/status")[1]
        self.assertIs(mary()["wake_word"], True)
        self.assertIs(mary()["wake_ready"], True)
        self.assertIs(self.status()["wake_word"], True)
        self.put(wake_word="0")
        self.assertIs(mary()["wake_word"], False)
        self.put(wake_word="maybe")  # not '1' or '0': ignored
        self.assertIs(mary()["wake_word"], False)
        self.put(wake_word="on")
        self.assertIs(mary()["wake_word"], True)
        self.assertEqual(server.mary_app_facts("mary")["wake_word"], True)

    def test_server_start_and_status_never_open_the_mic(self):
        st = self.status()
        self.assertEqual((st["enabled"], st["listening"], st["page"], st["ready"]), (False, False, False, True))
        self.assertEqual(st["phrase"], "Hey Mary")
        self.assertEqual(self.sd.streams, [])

    # ---- the long-poll ----
    def test_first_poll_starts_listening_and_quiet_poll_has_no_event(self):
        seq, s = self.opened()
        self.assertEqual(self.grammars, [["hey mary", "[unk]"]])
        body = self.poll(seq, wait=0.1)
        self.assertEqual((body["seq"], body["event"], body["off"]), (seq, None, False))
        st = body["status"]
        self.assertEqual((st["enabled"], st["listening"], st["page"], st["wake_word"]), (True, True, True, True))
        self.assertTrue(any(" start  name=\"mary\"" in line for line in self.log_lines()))

    def test_heard_then_wake_then_woke_pause(self):
        server.WAKE_WOKE_S = 0.4
        seq, s = self.opened()
        self.say(s, "hey mary")  # Vosk hears the name: the page may glow at once
        heard = self.poll(seq)
        self.assertEqual((heard["event"]["type"], heard["event"]["name"]), ("heard", "mary"))
        self.assertEqual(heard["event"]["seq"], heard["seq"])
        self.assertEqual(self.confirm.calls, [])  # told before Whisper was asked
        self.say(s, *["hey mary"] * 5)
        wake = self.poll(heard["seq"])
        ev = wake["event"]
        self.assertEqual((ev["type"], ev["name"], ev["companion"], ev["seq"]), ("wake", "mary", "mary", heard["seq"] + 1))
        self.assertIn("woke", wake["status"]["paused_by"])  # her own greeting cannot wake her
        self.assertTrue(wake["status"]["woke"])
        self.assertTrue(s.closed)
        self.wait_for(lambda: self.status()["paused_by"] == [])  # the pause ends by itself
        self.wait_for(self.sd.live_wake)
        line = [x for x in self.log_lines() if "  wake  " in x][0]
        self.assertIn('vosk="hey mary"', line)
        self.assertIn('whisper="Hey Mary."', line)
        self.assertIn("ms=", line)

    def test_hold_releases_the_woke_pause_and_expires(self):
        seq, s = self.opened()
        self.say(s, *["hey mary"] * 6)
        self.wait_for(lambda: "woke" in self.status()["paused_by"])
        status, body, _ = self.hold(True)
        self.assertEqual(status, 200)
        self.assertEqual((body["ok"], body["held"]), (True, True))
        self.assertEqual(body["status"]["paused_by"], ["page"])  # the hold took over from the woke pause
        self.assertEqual(self.hold(False)[1]["status"]["paused_by"], [])
        self.wait_for(self.sd.live_wake)
        server.WAKE_HOLD_S = 0.3
        self.hold(True)
        self.wait_for(lambda: self.sd.live_wake() is None)
        self.wait_for(lambda: self.status()["paused_by"] == [])  # a crashed page cannot leave it held
        self.assertFalse(self.status()["held"])
        self.wait_for(self.sd.live_wake)

    def test_hold_needs_the_tracker_header(self):
        self.assertEqual(self.hold(True, tracker=False)[0], 403)
        self.assertEqual(self.status()["paused_by"], [])

    def test_lease_watchdog_lets_go_of_the_mic(self):
        server.WAKE_LEASE_S = 0.3
        seq, s = self.opened()
        self.wait_for(lambda: not self.status()["enabled"])
        self.assertTrue(s.closed)
        self.assertFalse(self.status()["page"])
        self.assertTrue(any("  stop  why=" in line for line in self.log_lines()))
        self.opened()  # the next poll starts it again

    def test_turning_the_setting_off_stops_at_once(self):
        seq, s = self.opened()
        self.put(wake_word="0")
        self.assertTrue(s.closed)
        self.assertFalse(self.status()["enabled"])
        t0 = time.monotonic()
        body = self.poll(seq, wait=5)
        self.assertLess(time.monotonic() - t0, 2)
        self.assertEqual((body["off"], body["event"]), (True, None))
        self.assertEqual(len(self.sd.streams), 1)  # never opened again while off
        self.put(wake_word="1")
        self.opened()

    def test_sam_wakes_only_on_his_name(self):
        self.put(companion="him")
        seq, s = self.opened()
        self.assertEqual(self.grammars[-1], ["hey sam", "[unk]"])
        self.assertEqual(self.status()["phrase"], "Hey Sam")
        self.say(s, *["hey mary"] * 6)
        self.assertIsNone(self.poll(seq, wait=0.3)["event"])
        self.confirm.text = "Hey Sam."
        self.say(s, *["hey sam"] * 6)
        ev = self.wait_for(lambda: (lambda b: b["event"] if b["event"] and b["event"]["type"] == "wake" else None)(
            self.poll(seq, wait=2)))
        self.assertEqual((ev["name"], ev["companion"]), ("sam", "sam"))
        self.put(companion="mary")  # a new choice: the worker listens for the new name
        self.wait_for(lambda: self.grammars[-1] == ["hey mary", "[unk]"])

    def test_near_miss_is_logged_without_an_event(self):
        self.confirm.text = "Hey man, how is it going?"
        seq, s = self.opened()
        self.say(s, *["hey mary [unk]"] * 6)
        self.wait_for(lambda: any("  almost  " in x for x in self.log_lines()))
        line = [x for x in self.log_lines() if "  almost  " in x][0]
        self.assertIn('whisper="Hey man, how is it going?"', line)
        self.assertIn('vosk="hey mary [unk]"', line)
        body = self.poll(seq, wait=0.1)
        self.assertEqual(body["event"]["type"], "heard")  # only the glow; no wake followed
        self.assertEqual(self.status()["wakes"], 0)

    # ---- wake.log ----
    def test_log_rotates_and_never_raises(self):
        server.WAKE_LOG_MAX = 200
        for i in range(12):
            server.wake_log("almost", name="mary", whisper=f"line {i}")
        old = server.DATA / "wake.log.1"
        self.assertTrue(old.exists())
        self.assertLessEqual(self.log.stat().st_size, 200 + 100)
        self.assertTrue(all(len(x.split("  ")) >= 3 for x in self.log_lines()))
        server.DATA = server.DATA / "missing" / "folder"
        server.wake_log("wake", name="mary")  # cannot write: no error

    # ---- not installed ----
    def test_missing_vosk_answers_plainly(self):
        wakeword.available = self.saved[6]
        wakeword._vosk_installed = lambda: False
        t0 = time.monotonic()
        body = self.poll(0, wait=5)
        self.assertLess(time.monotonic() - t0, 2)
        st = body["status"]
        self.assertEqual((body["event"], body["off"], st["ready"], st["enabled"]), (None, False, False, False))
        self.assertIn("Hey Mary", st["reason"])
        self.assertIs(helpers.api("GET", "/api/mary/status")[1]["wake_ready"], False)
        self.assertEqual(self.hold(True)[0], 200)
        self.assertEqual(self.hold(False)[0], 200)
        self.assertEqual(self.sd.streams, [])


if __name__ == "__main__":
    unittest.main()
