from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

import base64
import io
import json
import shutil
import unittest
import urllib.error
import wave
from unittest import mock

import desktop
import server
import voices

KEY = "AIzaSyTESTKEY-not-a-real-key-123"
PCM = b"\x01\x00" * 2400  # 0.1 s at 24 kHz


def b64(raw):
    return base64.b64encode(raw).decode()


class Resp:
    """Stands in for the object urlopen returns: iterable by line, readable, a context manager."""

    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    def __iter__(self):
        return iter(self.body.splitlines(keepends=True))

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body=b"{}"):
    return urllib.error.HTTPError("https://example.test/x", code, "msg", {}, io.BytesIO(body))


class Net:
    """Replaces voices._open: hands out the queued responses (or raises the queued errors) in order."""

    def __init__(self, *queue):
        self.queue = list(queue)
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def body(self, i=0):
        return json.loads(self.requests[i].data.decode("utf-8"))


def sse(*events):
    return b"".join(b"event: content.delta\ndata: " + json.dumps(e).encode() + b"\n\n" for e in events)


def audio_event(raw=PCM, **extra):
    return {"event_type": "content.delta", "delta": {"type": "audio", "data": b64(raw), **extra}}


def gen_content(raw=PCM, mime="audio/L16;codec=pcm;rate=24000"):
    return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": mime, "data": b64(raw)}}]}}]}


def wav_info(wav):
    with wave.open(io.BytesIO(wav), "rb") as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()


class VoicesCase(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        shutil.rmtree(server.DATA / "mary" / "voices", ignore_errors=True)
        (server.DATA / "mary" / "audition.log").unlink(missing_ok=True)
        (server.DATA / "mary" / "memory.json").unlink(missing_ok=True)

    def use(self, *queue):
        net = Net(*queue)
        patcher = mock.patch.object(voices, "_open", net)
        patcher.start()
        self.addCleanup(patcher.stop)
        return net

    def save_key(self):
        helpers.api("PUT", "/api/settings", {"gemini_key": KEY})

    def log_text(self):
        path = server.DATA / "mary" / "audition.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""


class SampleTests(VoicesCase):
    def test_streamed_sse_makes_a_24k_wav_and_sends_the_documented_request(self):
        net = self.use(Resp(sse(audio_event(), audio_event())))
        got = voices.tts_sample("gemini:Sulafat", KEY, server.DATA)
        self.assertEqual(wav_info(got["wav"]), (24000, 1, 2, 4800))
        self.assertTrue(got["wav"].startswith(b"RIFF"))
        self.assertEqual(got["path"], "interactions")
        self.assertFalse(got["word_timings"])
        self.assertFalse(got["cached"])
        self.assertEqual(got["audio_s"], 0.2)
        req = net.requests[0]
        self.assertTrue(req.full_url.endswith("/v1beta/interactions"))
        self.assertEqual(req.get_header("X-goog-api-key"), KEY)
        self.assertNotIn(KEY, req.full_url)
        body = net.body()
        self.assertEqual(body["model"], "gemini-3.8-flash-tts")
        self.assertTrue(body["stream"])
        self.assertEqual(body["response_format"], {"type": "audio"})
        self.assertEqual(body["generation_config"], {"speech_config": [{"voice": "Sulafat"}]})
        text = body["input"][0]["content"][0]
        self.assertEqual(text["text"], voices.LINE)
        self.assertEqual(text["annotations"], [{"type": "speech_metadata", "style": voices.STYLE}])

    def test_plain_json_bodies_work_and_a_wav_chunk_loses_its_header(self):
        wav_chunk = voices._wav(PCM, 24000)
        body = {"outputs": [{"type": "audio", "data": b64(wav_chunk), "mime_type": "audio/wav"}],
                "usage": {"timestamps": [0, 1]}}
        self.use(Resp(body), Resp([{"x": {"type": "audio", "data": b64(PCM)}}]))
        one = voices.tts_sample("Sulafat", KEY, server.DATA)
        self.assertEqual(wav_info(one["wav"])[3], 2400)  # not 2400 + header bytes read as audio
        self.assertTrue(one["word_timings"])  # a "timestamps" key was seen
        two = voices.tts_sample("gemini:Vindemiatrix", KEY, server.DATA)
        self.assertEqual(wav_info(two["wav"])[3], 2400)
        self.assertFalse(two["word_timings"])

    def test_streamed_chunk_rate_is_used(self):
        self.use(Resp(sse(audio_event(sample_rate=16000))))
        got = voices.tts_sample("gemini:Achird", KEY, server.DATA)
        self.assertEqual(wav_info(got["wav"])[0], 16000)

    def test_404_falls_back_to_generate_content(self):
        net = self.use(http_error(404, b'{"error":{"message":"not found"}}'),
                       Resp(gen_content(mime="audio/L16;codec=pcm;rate=16000")))
        got = voices.tts_sample("gemini:Algieba", KEY, server.DATA)
        self.assertEqual(got["path"], "generateContent")
        self.assertEqual(wav_info(got["wav"]), (16000, 1, 2, 2400))
        self.assertTrue(net.requests[1].full_url.endswith("/models/gemini-3.8-flash-tts:generateContent"))
        self.assertEqual(net.requests[1].get_header("X-goog-api-key"), KEY)
        voice_cfg = net.body(1)["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]
        self.assertEqual(voice_cfg, {"voiceName": "Algieba"})
        self.assertEqual(net.body(1)["generationConfig"]["responseModalities"], ["AUDIO"])

    def test_400_that_is_not_the_key_and_an_empty_answer_also_fall_back(self):
        net = self.use(http_error(400, b'{"error":{"message":"Invalid argument"}}'), Resp(gen_content()),
                       Resp(b'{"outputs": []}'), Resp(gen_content()))
        self.assertEqual(voices.tts_sample("gemini:Sulafat", KEY, server.DATA)["path"], "generateContent")
        shutil.rmtree(server.DATA / "mary" / "voices")
        self.assertEqual(voices.tts_sample("gemini:Sulafat", KEY, server.DATA)["path"], "generateContent")
        self.assertEqual(len(net.requests), 4)

    def test_key_refusals_are_bad_key_and_never_fall_back(self):
        for err in (http_error(401), http_error(403),
                    http_error(400, b'{"error":{"message":"API key not valid. Please pass a valid API key."}}')):
            net = self.use(err)
            with self.assertRaises(voices.VoiceError) as cm:
                voices.tts_sample("gemini:Sulafat", KEY, server.DATA)
            self.assertEqual(cm.exception.kind, "bad_key")
            self.assertNotIn(KEY, str(cm.exception))
            self.assertEqual(len(net.requests), 1)

    def test_other_failures_are_no_gemini(self):
        for item in (http_error(500), urllib.error.URLError("no network"), TimeoutError("slow"),
                     Resp(b"this is not json at all")):
            self.use(item)
            with self.assertRaises(voices.VoiceError) as cm:
                voices.tts_sample("gemini:Sulafat", KEY, server.DATA)
            self.assertEqual(cm.exception.kind, "no_gemini", item)

    def test_a_failure_in_the_fallback_is_reported(self):
        self.use(http_error(404), http_error(401))
        with self.assertRaises(voices.VoiceError) as cm:
            voices.tts_sample("gemini:Sulafat", KEY, server.DATA)
        self.assertEqual(cm.exception.kind, "bad_key")

    def test_unknown_voice_makes_no_network_call(self):
        net = self.use()
        for junk in ("", "gemini:Nope", "live:Achird", "kokoro:af_heart", "../../x"):
            with self.assertRaises(voices.VoiceError) as cm:
                voices.tts_sample(junk, KEY, server.DATA)
            self.assertEqual(cm.exception.kind, "unknown_voice")
        self.assertEqual(net.requests, [])

    def test_a_saved_copy_skips_the_network(self):
        self.use(Resp(sse(audio_event())))
        first = voices.tts_sample("gemini:Achernar", KEY, server.DATA)
        files = list((server.DATA / "mary" / "voices").glob("gemini_Achernar-*.wav"))
        self.assertEqual(len(files), 1)
        net = self.use()  # an empty queue: any network call fails the test
        again = voices.tts_sample("gemini:Achernar", KEY, server.DATA)
        self.assertEqual(net.requests, [])
        self.assertTrue(again["cached"])
        self.assertEqual(again["wav"], first["wav"])
        self.assertEqual(again["path"], "interactions")
        self.assertEqual(again["audio_s"], first["audio_s"])

    def test_every_sample_is_logged_ok_or_not(self):
        self.use(Resp(sse(audio_event())), http_error(500))
        voices.tts_sample("gemini:Sulafat", KEY, server.DATA)
        with self.assertRaises(voices.VoiceError):
            voices.tts_sample("gemini:Umbriel", KEY, server.DATA)
        lines = [json.loads(x) for x in self.log_text().splitlines()]
        self.assertEqual([x["ok"] for x in lines], [True, False])
        self.assertEqual(lines[0]["id"], "gemini:Sulafat")
        self.assertEqual(lines[0]["path"], "interactions")
        self.assertEqual(lines[0]["model"], "gemini-3.8-flash-tts")
        self.assertEqual(lines[1]["error"], "no_gemini")
        self.assertNotIn(KEY, self.log_text())


class TokenTests(VoicesCase):
    def remember(self, name="Ruth", fact="likes tea"):
        memory = server.mary_memory()
        memory.name = name
        memory.facts.append(fact)
        memory.save()

    def test_token_request_has_constraints_voice_and_her_system_text(self):
        self.remember()
        net = self.use(Resp({"name": "auth_tokens/abc123"}))
        got = voices.live_token("live:Achird", KEY, "mary", "Ruth", server.DATA)
        self.assertEqual(got["token"], "auth_tokens/abc123")
        self.assertEqual(got["model"], "models/gemini-3.8-live")
        self.assertEqual(got["voice"], "Achird")
        self.assertTrue(got["ws"].startswith("wss://generativelanguage.googleapis.com/ws/"))
        self.assertTrue(got["ws"].endswith("BidiGenerateContentConstrained"))
        self.assertNotIn("access_token", got["ws"])
        req = net.requests[0]
        self.assertTrue(req.full_url.endswith("/v1beta/auth_tokens"))
        self.assertEqual(req.get_header("X-goog-api-key"), KEY)
        body = net.body()
        self.assertEqual(body["uses"], 1)
        self.assertTrue(body["expireTime"].endswith("Z") and body["newSessionExpireTime"].endswith("Z"))
        self.assertLess(body["newSessionExpireTime"], body["expireTime"])
        cons = body["liveConnectConstraints"]
        self.assertEqual(cons["model"], "models/gemini-3.8-live")
        cfg = cons["config"]
        self.assertEqual(cfg["responseModalities"], ["AUDIO"])
        self.assertEqual(cfg["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"], "Achird")
        self.assertEqual((cfg["inputAudioTranscription"], cfg["outputAudioTranscription"]), ({}, {}))
        system = cfg["systemInstruction"]["parts"][0]["text"]
        self.assertIn("Mary", system)
        self.assertIn("Name: Ruth", system)
        self.assertNotIn("likes tea", system)  # no facts list in a live chat
        self.assertIn("square brackets", system)  # her tag instructions stay, so the live note switches them off
        self.assertIn("don't use them here", system)
        self.assertIn("one to three short sentences", system)

    def test_sam_gets_his_own_name(self):
        net = self.use(Resp({"name": "auth_tokens/x"}))
        voices.live_token("Umbriel", KEY, "him", "", server.DATA)
        system = net.body()["liveConnectConstraints"]["config"]["systemInstruction"]["parts"][0]["text"]
        self.assertIn("Sam", system)
        self.assertNotIn("Mary", system)

    def test_token_errors_and_logging(self):
        for item, kind in ((http_error(403), "bad_key"), (http_error(500), "no_gemini"),
                           (Resp({"nope": 1}), "no_gemini")):
            self.use(item)
            with self.assertRaises(voices.VoiceError) as cm:
                voices.live_token("Achird", KEY, "mary", "", server.DATA)
            self.assertEqual(cm.exception.kind, kind)
        with self.assertRaises(voices.VoiceError):
            voices.live_token("gemini:Nope", KEY, "mary", "", server.DATA)
        lines = [json.loads(x) for x in self.log_text().splitlines()]
        self.assertEqual(len(lines), 4)
        self.assertTrue(all(x["event"] == "token" and x["ok"] is False for x in lines))
        self.assertNotIn(KEY, self.log_text())


class RouteTests(VoicesCase):
    def test_voice_list_has_candidates_live_voices_and_no_key(self):
        self.save_key()
        status, got, headers = helpers.api("GET", "/api/mary/voices")
        self.assertEqual(status, 200)
        self.assertEqual(got["line"], voices.LINE)
        self.assertTrue(got["has_key"])
        ids = [c["id"] for c in got["candidates"]]
        self.assertEqual(ids, ["gemini:Sulafat", "gemini:Vindemiatrix", "gemini:Achernar",
                               "gemini:Achird", "gemini:Algieba", "gemini:Umbriel"])
        self.assertEqual(got["candidates"][0],
                         {"id": "gemini:Sulafat", "kind": "gemini", "voice": "Sulafat",
                          "gender": "female", "about": "Warm", "ready": True})
        self.assertEqual(got["live"]["model"], "gemini-3.8-live")
        self.assertEqual([v["id"] for v in got["live"]["voices"]][3], "live:Achird")
        self.assertEqual(got["chosen"], {"mary": "", "him": ""})
        self.assertNotIn(KEY, json.dumps(got) + str(headers))
        helpers.api("PUT", "/api/settings", {"voice_mary": "gemini:Sulafat", "voice_sam": "live:Achird"})
        self.assertEqual(helpers.api("GET", "/api/mary/voices")[1]["chosen"],
                         {"mary": "gemini:Sulafat", "him": "live:Achird"})

    def test_sample_route_returns_a_wav_with_timing_headers(self):
        self.save_key()
        self.use(Resp(sse(audio_event())), Resp(sse(audio_event())))
        status, wav, headers = helpers.api("POST", "/api/mary/voices/sample", {"id": "gemini:Sulafat"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/wav")
        self.assertEqual(wav_info(wav)[0], 24000)
        self.assertEqual(headers["X-Cached"], "0")
        self.assertEqual(headers["X-Word-Timings"], "0")
        self.assertGreaterEqual(int(headers["X-First-Sound-Ms"]), 0)
        self.assertGreaterEqual(int(headers["X-Total-Ms"]), int(headers["X-First-Sound-Ms"]))
        status, wav2, headers2 = helpers.api("POST", "/api/mary/voices/sample", {"id": "gemini:Sulafat"})
        self.assertEqual((status, headers2["X-Cached"], wav2), (200, "1", wav))

    def test_the_key_never_leaves_in_a_body_header_or_log(self):
        self.save_key()
        echo = f'{{"error":{{"message":"bad {KEY}"}}}}'.encode()
        self.use(http_error(401, echo), http_error(500, echo), Resp(sse(audio_event())),
                 http_error(403, echo), Resp({"name": "auth_tokens/t"}))
        seen = []
        for path, body in (("/api/mary/voices/sample", {"id": "gemini:Sulafat"}),
                           ("/api/mary/voices/sample", {"id": "gemini:Achird"}),
                           ("/api/mary/voices/sample", {"id": "gemini:Algieba"}),
                           ("/api/mary/live/token", {"voice": "live:Achird"}),
                           ("/api/mary/live/token", {"voice": "live:Achird"})):
            status, got, headers = helpers.api("POST", path, body)
            seen.append(got if isinstance(got, bytes) else json.dumps(got).encode())
            seen.append(str(headers).encode())
        status, got, _ = helpers.api("GET", "/api/settings")
        seen.append(json.dumps(got).encode())
        self.assertNotIn(KEY.encode(), b"".join(seen))
        self.assertNotIn(KEY, self.log_text())
        self.assertGreaterEqual(len(self.log_text().splitlines()), 5)

    def test_route_errors_are_plain_sentences(self):
        status, got, _ = helpers.api("POST", "/api/mary/voices/sample", {"id": "gemini:Sulafat"})
        self.assertEqual(status, 400)
        self.assertEqual(got, {"error": "Mary needs her Gemini key first. You can add it in My info.",
                               "bad_key": False, "no_key": True})
        status, got, _ = helpers.api("POST", "/api/mary/live/token", {"voice": "live:Achird"})
        self.assertEqual((status, got["no_key"]), (400, True))
        self.save_key()
        self.use(http_error(401), http_error(500), http_error(503))
        status, got, _ = helpers.api("POST", "/api/mary/voices/sample", {"id": "gemini:Sulafat"})
        self.assertEqual((status, got["bad_key"], got["no_key"]), (400, True, False))
        status, got, _ = helpers.api("POST", "/api/mary/voices/sample", {"id": "gemini:Achird"})
        self.assertEqual((status, got["bad_key"]), (502, False))
        self.assertTrue(got["error"].endswith("."))
        status, got, _ = helpers.api("POST", "/api/mary/live/token", {"voice": "live:Achird"})
        self.assertEqual(status, 502)
        status, got, _ = helpers.api("POST", "/api/mary/voices/sample", {"id": "gemini:Nope"})
        self.assertEqual((status, got["error"]), (400, "I don't know that voice."))

    def test_token_route_uses_the_saved_companion_and_name(self):
        self.save_key()
        helpers.api("PUT", "/api/settings", {"companion": "him"})
        memory = server.mary_memory()
        memory.name = "Ruth"
        memory.save()
        net = self.use(Resp({"name": "auth_tokens/zzz"}))
        status, got, _ = helpers.api("POST", "/api/mary/live/token", {"voice": "live:Algieba"})
        self.assertEqual(status, 200)
        self.assertEqual(got["token"], "auth_tokens/zzz")
        self.assertEqual(got["voice"], "Algieba")
        system = net.body()["liveConnectConstraints"]["config"]["systemInstruction"]["parts"][0]["text"]
        self.assertIn("Sam", system)
        self.assertIn("Name: Ruth", system)

    def test_posts_need_the_tracker_header(self):
        self.save_key()
        net = self.use()
        for path, body in (("/api/mary/voices/sample", {"id": "gemini:Sulafat"}),
                           ("/api/mary/live/token", {"voice": "live:Achird"}),
                           ("/api/mary/voices/log", {"turns": 1})):
            status, _, _ = helpers.api("POST", path, body, tracker=False)
            self.assertEqual(status, 403, path)
        self.assertEqual(net.requests, [])
        self.assertEqual(self.log_text(), "")

    def test_settings_accept_known_voice_ids_and_reject_junk(self):
        status, got, _ = helpers.api("PUT", "/api/settings",
                                     {"voice_mary": "gemini:Sulafat", "voice_sam": "live:Achird"})
        self.assertEqual((status, got["voice_mary"], got["voice_sam"]), (200, "gemini:Sulafat", "live:Achird"))
        for junk in ("gemini:Nope", "evil", "live:", ":Sulafat", "kokoro:af_heart", 5, ["gemini:Sulafat"]):
            _, got, _ = helpers.api("PUT", "/api/settings", {"voice_mary": junk, "voice_sam": junk})
            self.assertEqual((got["voice_mary"], got["voice_sam"]), ("gemini:Sulafat", "live:Achird"), junk)
        _, got, _ = helpers.api("PUT", "/api/settings", {"voice_mary": "  ", "voice_sam": "live:Umbriel"})
        self.assertEqual((got["voice_mary"], got["voice_sam"]), ("", "live:Umbriel"))  # blank clears

    def test_valid_choice(self):
        for ok in ("gemini:Sulafat", "live:Achird", "live:Umbriel"):
            self.assertTrue(voices.valid_choice(ok), ok)
        for bad in ("", None, "gemini", "gemini:", "gemini:sulafat", "live:Nope", "kokoro:x", 3):
            self.assertFalse(voices.valid_choice(bad), bad)


class LogTests(VoicesCase):
    def test_log_route_keeps_only_whitelisted_keys(self):
        status, got, _ = helpers.api("POST", "/api/mary/voices/log", {
            "event": "not-live", "id": "live:Achird", "voice": "Achird", "reply_gap_ms": "812",
            "first_audio_ms": 640.5, "turns": 4, "interruptions": 1, "seconds": 93, "close_code": 1000,
            "note": "x" * 500, "ok": True, "evil": "drop me", "gemini_key": KEY, "token": "auth_tokens/secret",
            "total_ms": "not a number", "audio_s": float("nan")})
        self.assertEqual((status, got), (200, {"ok": True}))
        line = json.loads(self.log_text().splitlines()[-1])
        self.assertEqual(line.pop("event"), "live")
        self.assertIn("ts", line)
        line.pop("ts")
        self.assertEqual(line, {"id": "live:Achird", "voice": "Achird", "reply_gap_ms": 812,
                                "first_audio_ms": 640.5, "turns": 4, "interruptions": 1, "seconds": 93,
                                "close_code": 1000, "note": "x" * 120, "ok": True})
        self.assertNotIn(KEY, self.log_text())

    def test_log_is_one_json_line_per_event_and_stays_small(self):
        path = server.DATA / "mary" / "audition.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x" * 250_000, encoding="utf-8")
        voices.log({"event": "live", "note": "line one\nline two"}, server.DATA)
        voices.log({"event": "live", "turns": 2}, server.DATA)
        lines = self.log_text().splitlines()
        self.assertEqual(len(lines), 2)  # the old oversized file was dropped first
        self.assertEqual(json.loads(lines[0])["note"], "line one\nline two")


class WindowTests(unittest.TestCase):
    def test_voices_window_is_full_screen_like_mary(self):
        opts = desktop.window_options(True, True)
        self.assertEqual(opts["title"], "Mary voices")
        self.assertEqual(opts["path"], "/mary/voices.html")
        self.assertIs(opts["kwargs"]["fullscreen"], True)
        self.assertEqual(desktop.window_options(True)["path"], "/mary.html")  # --mary is unchanged
        self.assertEqual(desktop.window_options(False)["path"], "")


if __name__ == "__main__":
    unittest.main()
