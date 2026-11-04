from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

import base64
import io
import json
import shutil
import sys
import time
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


PCM2 = b"\x02\x00" * 2400


class SlowResp(Resp):
    """A Resp that counts the lines read so far, to show a chunk leaves before the rest of the answer arrives."""

    def __init__(self, body):
        super().__init__(body)
        self.read_lines = 0

    def __iter__(self):
        for line in self.body.splitlines(keepends=True):
            self.read_lines += 1
            yield line


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

    def test_stream_hands_over_the_first_chunk_before_the_second_line_is_read(self):
        resp = SlowResp(sse(audio_event(PCM), audio_event(PCM2)))  # 3 lines per event
        self.use(resp)
        gen = voices.tts_stream("gemini:Sulafat", KEY, server.DATA)
        self.assertEqual(next(gen), {"pcm": PCM, "rate": 24000, "channels": 1, "cached": False, "path": "interactions"})
        self.assertEqual(resp.read_lines, 2)  # the first event line and its data line, nothing more
        self.assertEqual(next(gen), {"pcm": PCM2, "rate": 24000, "channels": 1})
        self.assertEqual(list(gen), [])
        self.assertEqual(resp.read_lines, 6)
        files = list((server.DATA / "mary" / "voices").glob("gemini_Sulafat-*.wav"))
        self.assertEqual(len(files), 1)  # saved once the last chunk was out
        self.assertEqual(wav_info(files[0].read_bytes())[3], 4800)
        (line,) = [json.loads(x) for x in self.log_text().splitlines()]
        self.assertEqual((line["ok"], line["path"], line["audio_s"]), (True, "interactions", 0.2))

    def test_stream_keeps_whole_samples_when_a_chunk_ends_mid_sample(self):
        self.use(Resp(sse(audio_event(PCM + b"\x05"), audio_event(b"\x00" + PCM2))))
        chunks = list(voices.tts_stream("gemini:Sulafat", KEY, server.DATA))
        self.assertEqual(chunks[0]["pcm"], PCM)
        self.assertEqual(chunks[1]["pcm"], b"\x05\x00" + PCM2)

    def test_stopping_early_logs_stopped_once_saves_nothing_and_writes_no_success_line(self):
        self.use(Resp(sse(audio_event(PCM), audio_event(PCM2))))
        gen = voices.tts_stream("gemini:Sulafat", KEY, server.DATA)
        next(gen)
        gen.close()
        gen.close()
        self.assertFalse((server.DATA / "mary" / "voices").exists())
        (line,) = [json.loads(x) for x in self.log_text().splitlines()]
        self.assertEqual((line["ok"], line["error"], line["id"]), (False, "stopped", "gemini:Sulafat"))

    def test_stream_falls_back_to_generate_content_only_when_nothing_came_out(self):
        net = self.use(Resp(b'{"outputs": []}'), Resp(gen_content()))
        chunks = list(voices.tts_stream("gemini:Sulafat", KEY, server.DATA))
        self.assertEqual(chunks, [{"pcm": PCM, "rate": 24000, "channels": 1, "cached": False, "path": "generateContent"}])
        self.assertEqual(len(net.requests), 2)


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
        self.assertTrue(got["ws"].endswith("v1beta.GenerativeService.BidiGenerateContentConstrained"))
        self.assertNotIn("access_token", got["ws"])
        req = net.requests[0]
        self.assertTrue(req.full_url.endswith("/v1beta/auth_tokens"))
        self.assertEqual(req.get_header("X-goog-api-key"), KEY)
        body = net.body()
        self.assertEqual(body["uses"], 1)
        self.assertTrue(body["expireTime"].endswith("Z") and body["newSessionExpireTime"].endswith("Z"))
        self.assertLess(body["newSessionExpireTime"], body["expireTime"])
        self.assertNotIn("liveConnectConstraints", body)  # the name Google refused on 2026-10-29
        self.assertNotIn("fieldMask", body)  # no mask: every field is locked
        cfg = body["bidiGenerateContentSetup"]
        self.assertEqual(cfg["model"], "models/gemini-3.8-live")
        gen = cfg["generationConfig"]
        self.assertEqual(gen["responseModalities"], ["AUDIO"])
        self.assertEqual(gen["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"], "Achird")
        self.assertEqual(cfg["inputAudioTranscription"], {"languageCodes": ["en-US"]})  # M4a: English hint
        self.assertEqual(cfg["outputAudioTranscription"], {})
        system = cfg["systemInstruction"]["parts"][0]["text"]
        self.assertIn("Mary", system)
        self.assertIn("Name: Ruth", system)
        self.assertNotIn("likes tea", system)  # no facts list in a live chat
        self.assertIn("square brackets", system)
        self.assertNotIn("[mood", system)  # M4a: no tag rules at all, so nothing for Live to say out loud
        self.assertNotIn("don't use them here", system)
        self.assertIn("menu of options", system)  # M4a: no more one-to-three-sentence cap

    def test_token_tries_v1alpha_when_v1beta_does_not_know_the_fields(self):
        unknown = (b'{"error":{"status":"INVALID_ARGUMENT","message":"Invalid JSON payload received. '
                   b'Unknown name \\"bidiGenerateContentSetup\\" at \'auth_token\'"}}')
        net = self.use(http_error(400, unknown), Resp({"name": "auth_tokens/alpha"}))
        got = voices.live_token("live:Achird", KEY, "mary", "", server.DATA)
        self.assertEqual(got["token"], "auth_tokens/alpha")
        self.assertTrue(got["ws"].endswith("v1alpha.GenerativeService.BidiGenerateContentConstrained"))
        self.assertTrue(net.requests[1].full_url.endswith("/v1alpha/auth_tokens"))
        self.assertEqual(net.body(1), net.body(0))
        line = json.loads(self.log_text().splitlines()[-1])
        self.assertEqual((line["ok"], line["path"]), (True, "v1alpha"))
        self.assertIn("Unknown name", line["note"])  # why the first try failed

    def test_token_other_errors_are_not_retried_and_free_limit_is_busy(self):
        net = self.use(http_error(500, b'{"error":{"status":"INTERNAL","message":"oops"}}'))
        with self.assertRaises(voices.VoiceError) as cm:
            voices.live_token("live:Achird", KEY, "mary", "", server.DATA)
        self.assertEqual((cm.exception.kind, len(net.requests)), ("no_gemini", 1))
        self.use(http_error(429, b'{"error":{"status":"RESOURCE_EXHAUSTED","message":"quota"}}'))
        with self.assertRaises(voices.VoiceError) as cm:
            voices.live_token("live:Achird", KEY, "mary", "", server.DATA)
        self.assertEqual(cm.exception.kind, "busy")
        body, status = server.voice_failure("busy")
        self.assertEqual(status, 503)
        self.assertIn("free limit", body["error"])

    def test_sam_gets_his_own_name(self):
        net = self.use(Resp({"name": "auth_tokens/x"}))
        voices.live_token("Umbriel", KEY, "him", "", server.DATA)
        system = net.body()["bidiGenerateContentSetup"]["systemInstruction"]["parts"][0]["text"]
        self.assertIn("You are Sam", system)
        self.assertNotIn("You are Mary", system)  # M9b: "the Hail Mary" is in the shared prayer line

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
                               "gemini:Achird", "gemini:Algieba", "gemini:Umbriel",
                               "kokoro:af_heart", "kokoro:af_bella", "kokoro:bf_emma",
                               "kokoro:am_michael", "kokoro:am_fenrir", "kokoro:bm_george"])
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

    def test_stream_route_sends_raw_pcm_then_the_saved_copy(self):
        self.save_key()
        self.use(Resp(sse(audio_event(PCM), audio_event(PCM2))))
        status, body, headers = helpers.api("POST", "/api/mary/voices/stream", {"id": "gemini:Sulafat"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/L16")
        self.assertEqual((headers["X-Rate"], headers["X-Channels"], headers["X-Cached"], headers["X-Voice-Path"]),
                         ("24000", "1", "0", "interactions"))
        self.assertNotIn("Content-Length", headers)
        self.assertNotIn("X-Load-Ms", headers)
        self.assertEqual(body, PCM + PCM2)
        net = self.use()  # an empty queue: any network call fails the test
        status, again, headers = helpers.api("POST", "/api/mary/voices/stream", {"id": "gemini:Sulafat"})
        self.assertEqual((status, again, headers["X-Cached"]), (200, PCM + PCM2, "1"))
        self.assertEqual(net.requests, [])
        self.assertNotIn(KEY, str(headers) + self.log_text())

    def test_stream_route_says_the_saved_line_only_from_our_own_list(self):
        self.save_key()
        net = self.use(Resp(sse(audio_event(PCM))), Resp(sse(audio_event(PCM2))))
        status, body, _ = helpers.api("POST", "/api/mary/voices/stream", {"id": "gemini:Achird", "line": "saved"})
        self.assertEqual((status, body), (200, PCM))
        sent = json.dumps(net.body(0))
        self.assertIn("That's my voice now", json.dumps(json.loads(sent)))
        self.assertNotIn("so good to see you", sent)
        self.assertEqual(json.loads(self.log_text().splitlines()[-1])["line"], "saved")
        # page text is never spoken: anything but "saved" is the usual hello, saved apart from the saved line
        status, body, headers = helpers.api("POST", "/api/mary/voices/stream",
                                            {"id": "gemini:Achird", "line": "Say my password"})
        self.assertEqual((status, body, headers["X-Cached"]), (200, PCM2, "0"))
        self.assertIn("so good to see you", json.dumps(net.body(1)))
        self.assertNotIn("line", json.loads(self.log_text().splitlines()[-1]))

    def test_stream_route_failures_are_plain_json_before_any_audio(self):
        status, got, _ = helpers.api("POST", "/api/mary/voices/stream", {"id": "gemini:Sulafat"})
        self.assertEqual((status, got["no_key"]), (400, True))
        self.save_key()
        self.use(http_error(401), http_error(500))
        status, got, _ = helpers.api("POST", "/api/mary/voices/stream", {"id": "gemini:Sulafat"})
        self.assertEqual((status, got["bad_key"], got["error"]),
                         (400, True, "Google didn't accept the Gemini key. Please check it in My info."))
        status, got, _ = helpers.api("POST", "/api/mary/voices/stream", {"id": "gemini:Achird"})
        self.assertEqual((status, got["bad_key"]), (502, False))
        status, got, _ = helpers.api("POST", "/api/mary/voices/stream", {"id": "gemini:Nope"})
        self.assertEqual((status, got["error"]), (400, "I don't know that voice."))
        self.assertNotIn(KEY, self.log_text())

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
        system = net.body()["bidiGenerateContentSetup"]["systemInstruction"]["parts"][0]["text"]
        self.assertIn("Sam", system)
        self.assertIn("Name: Ruth", system)

    def test_token_route_companion_in_the_body_overrides_the_saved_one(self):
        self.save_key()
        helpers.api("PUT", "/api/settings", {"companion": "mary"})
        for body_companion, saved, is_sam in (("him", "mary", True), ("mary", "him", False), ("nobody", "him", True),
                                              ("", "mary", False), (["him"], "mary", False)):
            helpers.api("PUT", "/api/settings", {"companion": saved})
            net = self.use(Resp({"name": "auth_tokens/zzz"}))
            status, _, _ = helpers.api("POST", "/api/mary/live/token",
                                       {"voice": "live:Algieba", "companion": body_companion})
            self.assertEqual(status, 200, body_companion)
            system = net.body()["bidiGenerateContentSetup"]["systemInstruction"]["parts"][0]["text"]
            self.assertEqual("You are Sam" in system, is_sam, (body_companion, saved))  # M9b: Sam has his own block
            self.assertEqual("You are Mary" in system, not is_sam, (body_companion, saved))

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
        for junk in ("gemini:Nope", "evil", "live:", ":Sulafat", "kokoro:Sulafat", "kokoro:", 5, ["gemini:Sulafat"]):
            _, got, _ = helpers.api("PUT", "/api/settings", {"voice_mary": junk, "voice_sam": junk})
            self.assertEqual((got["voice_mary"], got["voice_sam"]), ("gemini:Sulafat", "live:Achird"), junk)
        _, got, _ = helpers.api("PUT", "/api/settings", {"voice_mary": "  ", "voice_sam": "live:Umbriel"})
        self.assertEqual((got["voice_mary"], got["voice_sam"]), ("", "live:Umbriel"))  # blank clears

    def test_valid_choice(self):
        for ok in ("gemini:Sulafat", "live:Achird", "live:Umbriel", "kokoro:af_heart", "kokoro:bm_george"):
            self.assertTrue(voices.valid_choice(ok), ok)
        for bad in ("", None, "gemini", "gemini:", "gemini:sulafat", "live:Nope", "kokoro:x", "kokoro:AF_HEART",
                    "kokoro:Sulafat", "gemini:af_heart", 3):
            self.assertFalse(voices.valid_choice(bad), bad)


class FakeKokoro:
    """Stands in for kokoro_onnx.Kokoro: 0.1 s of audio per sentence, no model, no onnxruntime."""

    def __init__(self):
        self.calls = []

    def create(self, text, voice, speed=1.0, lang="en-us"):
        self.calls.append((text, voice, speed, lang))
        return [0.0, 0.5, -0.5, 1.5, -1.5] * 480, 24000


class KokoroTests(VoicesCase):
    def setUp(self):
        super().setUp()
        self.fake = FakeKokoro()
        self.loads = 0
        voices._kokoro = None
        self.addCleanup(setattr, voices, "_kokoro", None)
        for name, new in (("kokoro_ready", lambda: True), ("_load_kokoro", self.load)):
            patcher = mock.patch.object(voices, name, new)
            patcher.start()
            self.addCleanup(patcher.stop)

    def load(self):
        self.loads += 1
        time.sleep(0.02)
        return self.fake

    def lines(self):
        return [json.loads(x) for x in self.log_text().splitlines()]

    def test_the_offline_voice_needs_no_key_and_returns_a_wav(self):
        status, wav, headers = helpers.api("POST", "/api/mary/voices/sample", {"id": "kokoro:af_heart"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/wav")
        rate, _, _, frames = wav_info(wav)
        self.assertEqual(rate, 24000)
        self.assertEqual(frames, 3 * 2400 + 2 * int(24000 * voices.KOKORO_PAUSE_S))  # three sentences, two pauses
        self.assertEqual((headers["X-Voice-Path"], headers["X-Cached"], headers["X-Word-Timings"]), ("kokoro", "0", "0"))
        self.assertGreaterEqual(float(headers["X-Rtf"]), 0)
        self.assertEqual(headers["X-Audio-S"], "0.6")
        self.assertEqual([c[0] for c in self.fake.calls],
                         ["Hello there!", "It's so good to see you today.",
                          "I'm right here whenever you'd like to talk, or just to keep you company."])
        self.assertEqual({c[1:] for c in self.fake.calls}, {("af_heart", 1.0, "en-us")})

    def test_british_voices_use_british_english(self):
        voices.kokoro_sample("kokoro:bf_emma", server.DATA)
        voices.kokoro_sample("kokoro:bm_george", server.DATA)
        voices.kokoro_sample("kokoro:am_fenrir", server.DATA)
        langs = {c[1]: c[3] for c in self.fake.calls}
        self.assertEqual(langs, {"bf_emma": "en-gb", "bm_george": "en-gb", "am_fenrir": "en-us"})

    def test_the_model_loads_once_and_only_the_first_call_reports_it(self):
        first = voices.kokoro_sample("kokoro:af_bella", server.DATA)
        again = voices.kokoro_sample("kokoro:am_michael", server.DATA)
        self.assertEqual(self.loads, 1)
        self.assertGreaterEqual(first["load_ms"], 10)  # the fake load sleeps 15 ms
        self.assertGreaterEqual(first["first_sound_ms"], first["load_ms"])
        self.assertEqual(again["load_ms"], 0)
        self.assertGreaterEqual(first["total_ms"], first["first_sound_ms"])
        for got in (first, again):
            self.assertEqual((got["path"], got["word_timings"], got["cached"], got["audio_s"]), ("kokoro", False, False, 0.6))
            self.assertGreaterEqual(got["rtf"], 0)
        self.assertFalse((server.DATA / "mary" / "voices").exists())  # never saved: every play measures again

    def test_samples_are_logged_with_speed_numbers(self):
        voices.kokoro_sample("kokoro:am_michael", server.DATA)
        (line,) = self.lines()
        self.assertEqual((line["ok"], line["id"], line["voice"], line["path"]), (True, "kokoro:am_michael", "am_michael", "kokoro"))
        for key in ("rtf", "load_ms", "first_sound_ms", "total_ms", "audio_s"):
            self.assertIn(key, line)
        self.assertEqual(line["audio_s"], 0.6)

    def test_stream_gives_one_chunk_per_sentence_with_the_pause_before_all_but_the_first(self):
        gen = voices.kokoro_stream("kokoro:af_heart", server.DATA)
        first = next(gen)
        self.assertEqual((first["rate"], first["channels"], first["cached"], first["path"]), (24000, 1, False, "kokoro"))
        self.assertGreaterEqual(first["load_ms"], 10)
        self.assertEqual(len(first["pcm"]), 4800)
        self.assertEqual(len(self.fake.calls), 1)  # the next sentence is not made until it is asked for
        rest = list(gen)
        gap = 2 * int(24000 * voices.KOKORO_PAUSE_S)
        self.assertEqual([len(c["pcm"]) for c in rest], [gap + 4800] * 2)
        self.assertTrue(all(c["pcm"][:gap] == b"\x00" * gap for c in rest))
        self.assertTrue(all(set(c) == {"pcm", "rate", "channels"} for c in rest))
        (line,) = self.lines()
        self.assertEqual((line["ok"], line["path"], line["audio_s"]), (True, "kokoro", 0.6))

    def test_stopping_early_logs_stopped_and_no_success_line(self):
        gen = voices.kokoro_stream("kokoro:am_michael", server.DATA)
        next(gen)
        gen.close()
        (line,) = self.lines()
        self.assertEqual((line["ok"], line["error"], line["id"]), (False, "stopped", "kokoro:am_michael"))
        self.assertEqual(len(self.fake.calls), 1)

    def test_offline_voice_can_say_the_saved_line(self):
        chunks = list(voices.kokoro_stream("kokoro:am_michael", server.DATA, text=voices.SAVED_LINE))
        self.assertEqual(len(chunks), 2)
        self.assertEqual([c[0] for c in self.fake.calls], ["Got it.", "That's my voice now."])
        self.assertEqual(json.loads(self.log_text().splitlines()[-1])["line"], "saved")

    def test_stream_route_needs_no_key_and_says_how_long_the_load_took(self):
        status, body, headers = helpers.api("POST", "/api/mary/voices/stream", {"id": "kokoro:af_heart"})
        self.assertEqual((status, headers["Content-Type"], headers["X-Rate"], headers["X-Voice-Path"], headers["X-Cached"]),
                         (200, "audio/L16", "24000", "kokoro", "0"))
        self.assertGreaterEqual(int(headers["X-Load-Ms"]), 10)
        self.assertEqual(len(body), 3 * 4800 + 2 * 2 * int(24000 * voices.KOKORO_PAUSE_S))
        with mock.patch.object(voices, "kokoro_ready", lambda: False):
            status, got, _ = helpers.api("POST", "/api/mary/voices/stream", {"id": "kokoro:af_heart"})
        self.assertEqual((status, got["bad_key"]), (503, False))

    def test_not_installed_is_a_plain_503_and_is_logged(self):
        with mock.patch.object(voices, "kokoro_ready", lambda: False):
            status, got, _ = helpers.api("POST", "/api/mary/voices/sample", {"id": "kokoro:af_heart"})
            self.assertEqual(status, 503)
            self.assertEqual(got, {"error": "The offline voice isn't installed on this computer yet.",
                                   "bad_key": False, "no_key": False})
            with self.assertRaises(voices.VoiceError) as cm:
                voices.kokoro_sample("kokoro:af_heart", server.DATA)
            self.assertEqual(cm.exception.kind, "no_offline")
        self.assertEqual(self.loads, 0)
        self.assertEqual([(x["ok"], x["error"]) for x in self.lines()], [(False, "no_offline")] * 2)

    def test_an_engine_that_breaks_is_no_offline_and_can_try_again(self):
        def boom():
            raise RuntimeError(r"cannot open C:\Users\Someone\secret\kokoro.onnx")
        with mock.patch.object(voices, "_load_kokoro", boom):
            status, got, _ = helpers.api("POST", "/api/mary/voices/sample", {"id": "kokoro:af_heart"})
        self.assertEqual(status, 503)
        self.assertNotIn("Someone", json.dumps(got))
        self.assertIsNone(voices._kokoro)
        self.assertEqual(voices.kokoro_sample("kokoro:af_heart", server.DATA)["path"], "kokoro")  # next try loads fine
        self.fake.create = mock.Mock(side_effect=ValueError("bad phonemes"))
        status, got, _ = helpers.api("POST", "/api/mary/voices/sample", {"id": "kokoro:af_heart"})
        self.assertEqual(status, 503)

    def test_unknown_offline_voice_is_refused_without_the_engine(self):
        status, got, _ = helpers.api("POST", "/api/mary/voices/sample", {"id": "kokoro:nope"})
        self.assertEqual((status, got["error"]), (400, "I don't know that voice."))
        status, got, _ = helpers.api("POST", "/api/mary/voices/sample", {"id": "gemini:Sulafat"})  # Gemini still needs the key
        self.assertEqual((status, got["no_key"]), (400, True))
        self.assertEqual(self.loads, 0)

    def test_candidates_say_whether_the_offline_voices_are_ready(self):
        offline = [c for c in voices.candidates() if c["kind"] == "kokoro"]
        self.assertEqual(len(offline), 6)
        self.assertTrue(all(c["ready"] for c in offline))
        self.assertEqual({c["gender"] for c in offline}, {"female", "male"})
        with mock.patch.object(voices, "kokoro_ready", lambda: False):
            self.assertFalse(any(c["ready"] for c in voices.candidates() if c["kind"] == "kokoro"))
            self.assertTrue(all(c["ready"] for c in voices.candidates() if c["kind"] == "gemini"))

    def test_the_settings_keep_an_offline_voice_choice(self):
        _, got, _ = helpers.api("PUT", "/api/settings", {"voice_mary": "kokoro:af_heart", "voice_sam": "kokoro:am_michael"})
        self.assertEqual((got["voice_mary"], got["voice_sam"]), ("kokoro:af_heart", "kokoro:am_michael"))


class KokoroReadyTests(unittest.TestCase):
    def test_ready_needs_both_files_and_the_package_without_importing_it(self):
        files = (voices.Path("m.onnx"), voices.Path("v.bin"))
        spec = object()
        with mock.patch.object(voices, "_kokoro_files", lambda: files), \
                mock.patch("importlib.util.find_spec", lambda name: spec if name == "kokoro_onnx" else None):
            self.assertTrue(voices.kokoro_ready())
        with mock.patch.object(voices, "_kokoro_files", lambda: None), \
                mock.patch("importlib.util.find_spec", lambda name: spec):
            self.assertFalse(voices.kokoro_ready())
        with mock.patch.object(voices, "_kokoro_files", lambda: files), \
                mock.patch("importlib.util.find_spec", lambda name: None):
            self.assertFalse(voices.kokoro_ready())

    def test_files_are_found_in_the_app_folder_or_the_data_folder(self):
        root = server.DATA / "kokoro-test"
        shutil.rmtree(root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, root, True)
        (root / "app").mkdir(parents=True)
        with mock.patch.object(voices, "_HERE", root / "app"), mock.patch.dict("os.environ", {"APPDATA": str(root / "ad")}):
            self.assertIsNone(voices._kokoro_files())
            folder = root / "ad" / "CareIncidentLog" / "models" / "kokoro"
            folder.mkdir(parents=True)
            (folder / voices.KOKORO_MODEL).write_bytes(b"x")
            self.assertIsNone(voices._kokoro_files())  # one file is not enough
            (folder / voices.KOKORO_VOICE_FILE).write_bytes(b"x")
            self.assertEqual(voices._kokoro_files(), (folder / voices.KOKORO_MODEL, folder / voices.KOKORO_VOICE_FILE))
            app = root / "app" / "models" / "kokoro"
            app.mkdir(parents=True)
            (app / voices.KOKORO_MODEL).write_bytes(b"x")
            (app / voices.KOKORO_VOICE_FILE).write_bytes(b"x")
            self.assertEqual(voices._kokoro_files()[0], app / voices.KOKORO_MODEL)  # the app's own folder wins

    def test_samples_become_clipped_16_bit_with_or_without_numpy(self):
        samples = [0.0, 0.5, -0.5, 1.5, -1.5]
        want = b"\x00\x00" + (16383).to_bytes(2, "little", signed=True) + (-16383).to_bytes(2, "little", signed=True) \
            + (32767).to_bytes(2, "little", signed=True) + (-32768).to_bytes(2, "little", signed=True)
        self.assertEqual(voices._pcm16(samples), want)
        with mock.patch.dict(sys.modules, {"numpy": None}):
            self.assertEqual(voices._pcm16(samples), want)


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

    def test_a_played_event_keeps_its_timing_numbers_and_drops_the_rest(self):
        status, got, _ = helpers.api("POST", "/api/mary/voices/log", {
            "event": "played", "id": "gemini:Sulafat", "tap_to_sound_ms": 412, "cached": True, "gaps": 1,
            "gap_ms": "230", "greet_ms": 900, "mic_ms": 150, "evil": "drop me", "gemini_key": KEY})
        self.assertEqual((status, got), (200, {"ok": True}))
        line = json.loads(self.log_text().splitlines()[-1])
        line.pop("ts")
        self.assertEqual(line, {"event": "played", "id": "gemini:Sulafat", "cached": True, "tap_to_sound_ms": 412,
                                "gaps": 1, "gap_ms": 230, "greet_ms": 900, "mic_ms": 150})
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
    def test_voices_window_is_maximized_like_mary(self):  # Andy, 2026-11-04: both can be minimized
        opts = desktop.window_options(True, True)
        self.assertEqual(opts["title"], "Mary voices")
        self.assertEqual(opts["path"], "/mary/voices.html")
        self.assertEqual(opts["kwargs"], desktop.window_options(True)["kwargs"])
        self.assertEqual(desktop.window_options(True)["path"], "/mary.html")  # --mary is unchanged
        self.assertEqual(desktop.window_options(False)["path"], "")


if __name__ == "__main__":
    unittest.main()
