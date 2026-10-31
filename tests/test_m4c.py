from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M4c: the character note in Normal and Live, the pet-name and racist rules, the emergency said once, the name asked
once ever, and Live/Normal passing what was heard to skills. Fake Gemini and fake network only."""
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import mary
import memory_core
import server
import skills_core
import voices
from tests.test_mary import FakeGemini, KEY
from tests.test_tool_groups import GAME_WORDS, Rounds, fc
from tests.test_tool_groups import call as tool_call
from tests.test_voices import Net, Resp

REAL = Path(__file__).resolve().parent.parent / "skills"
FELL = "I fell and I can't get up"
NAME_ASK = "What would you like to be called, by the way?"


def new_memory(**kw):
    mem = mary.Memory(Path(tempfile.mkdtemp(prefix="m4c-", dir=helpers.TMP)) / "memory.json")
    for k, v in kw.items():
        setattr(mem, k, v)
    return mem


class LiveBase(unittest.TestCase):
    def live_prompt(self, memory, companion="mary", rate=None):
        net = Net(Resp({"name": "auth_tokens/abc"}))
        p = mock.patch.object(voices, "_open", net)
        p.start()
        self.addCleanup(p.stop)
        voices.live_token("live:Achird", KEY, companion, "", server.DATA, memory=memory, rate=rate)
        return net.body()["bidiGenerateContentSetup"]["systemInstruction"]["parts"][0]["text"]


class CharacterNote(LiveBase):
    def test_note_shape(self):
        note = mary.CHARACTER_NOTE
        self.assertNotIn("[", note)
        self.assertNotIn("Mary", note)
        self.assertNotIn("Sam", note)
        for word in ("honey", "sugar", "good for you", "Look at that", "Bless your heart", "I don't see people that way"):
            self.assertIn(word, note)

    def test_live_ends_with_note(self):
        self.assertTrue(voices.LIVE_TOOLS_NOTE.endswith(mary.CHARACTER_NOTE))
        for companion in ("mary", "him"):
            self.assertTrue(self.live_prompt(new_memory(), companion).endswith(mary.CHARACTER_NOTE), companion)

    def test_tryout_has_it(self):
        net = Net(Resp({"name": "auth_tokens/abc"}))
        with mock.patch.object(voices, "_open", net):
            voices.live_token("live:Achird", KEY, "mary", "", server.DATA)
        text = net.body()["bidiGenerateContentSetup"]["systemInstruction"]["parts"][0]["text"]
        self.assertIn(mary.CHARACTER_NOTE, text)

    def test_pace_hint_comes_after(self):
        text = self.live_prompt(new_memory(), rate=0.7)
        self.assertIn(mary.CHARACTER_NOTE, text)
        self.assertFalse(text.endswith(mary.CHARACTER_NOTE))


class NormalOrder(unittest.TestCase):
    def test_after_skills_before_turn_notes(self):
        skills = SimpleNamespace(instruction_text=lambda screen=None: "SKILLS TEXT HERE", gemini_tools=lambda: [])
        mem = new_memory()
        kind = mary.is_emergency(FELL)
        self.assertTrue(kind)
        text = mary._body(FELL, mem, kind, skills=skills)["systemInstruction"]["parts"][0]["text"]
        self.assertIn(mary.CHARACTER_NOTE, text)
        self.assertLess(text.index("already told them this out loud"), len(text))
        self.assertLess(text.index(mary.CHARACTER_NOTE), text.index("already told them this out loud"))
        text = mary._body("he hit me", mem, "", skills=skills)["systemInstruction"]["parts"][0]["text"]
        self.assertLess(text.index("SKILLS TEXT HERE"), text.index(mary.CHARACTER_NOTE))
        self.assertLess(text.index(mary.CHARACTER_NOTE), text.index(mary.HARM_NOTE))


class Instructions(LiveBase):
    def test_each_voice(self):
        for tags in (True, False):
            mary_text = mary.system_text(new_memory(), "mary", tags=tags)
            self.assertIn("unless they ask", mary_text)
            self.assertNotIn('ease into "honey"', mary_text)
            sam_text = mary.system_text(new_memory(), "him", tags=tags)
            self.assertIn("ask first", sam_text)
            self.assertIn("buddy", sam_text)
            for text in (mary_text, sam_text):
                self.assertIn("I don't see people that way", text)
                self.assertIn("does not apply here", text)

    def test_live_prompts_hold_note(self):
        for companion in ("mary", "him"):
            self.assertIn(mary.CHARACTER_NOTE, self.live_prompt(new_memory(), companion))


class EmergencyOnce(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGemini()
        self._real = mary._gemini_stream
        mary._gemini_stream = self.fake
        self.addCleanup(setattr, mary, "_gemini_stream", self._real)
        self.mem = new_memory()

    def say(self, text, *chunks):
        self.fake.chunks = list(chunks)
        return mary.reply(text, self.mem, KEY)

    def fell(self, *chunks):
        kind = mary.is_emergency(FELL)
        app = mary.EMERGENCY_TEXT[kind]
        r = self.say(FELL, *chunks)
        self.assertEqual(r["text"].count(app), 1, r["text"])
        self.assertTrue(r["text"].startswith(app))
        return r, app, r["text"][len(app):]

    def test_steps_once(self):
        r, app, rest = self.fell("[mood: alert] Please press your call light right now. I'm right here.")
        self.assertIn("I'm right here.", rest)
        self.assertEqual(r["text"].count("call light"), app.count("call light"))

    def test_all_repeats_gives_stay_text(self):
        r, app, rest = self.fell("Press your call light and call 911.")
        self.assertIn(mary.STAY_TEXT, rest)
        self.assertEqual(r["error"], "")

    def test_split_across_chunks(self):
        r, app, rest = self.fell("Press your call", " light now. I'm with you.")
        self.assertIn("I'm with you.", rest)
        self.assertNotIn("Press your", rest)

    def test_spelled_numbers(self):
        r, app, rest = self.fell("Call nine one one.")
        self.assertNotIn("nine one one", rest)
        self.assertIn(mary.STAY_TEXT, rest)
        r, app, rest = self.fell("Call or text nine, eight, eight. I'm here.")
        self.assertNotIn("nine, eight, eight", rest)
        self.assertIn("I'm here.", rest)

    def test_veteran_line_stays(self):
        kind = mary.is_emergency("I want to kill myself")
        self.assertEqual(kind, "self_harm")
        line = "Since you're a veteran, you can call nine, eight, eight and press one, or text eight three eight, two five five."
        r = self.say("I want to kill myself", line)
        self.assertIn("veteran", r["text"])
        self.assertIn("nine, eight, eight", r["text"])

    def test_need_a_nurse_stays(self):
        r, app, rest = self.fell("That sounds serious, and you need a nurse.")
        self.assertIn("you need a nurse", rest)

    def test_remember_tag_saves_and_is_silent(self):
        r, app, rest = self.fell("[mood: alert] I'm here. [remember: Likes tea.]")
        self.assertEqual(r["remembered"], ["Likes tea."])
        self.assertNotIn("remember", r["text"])
        self.assertNotIn("Likes tea", r["text"])

    def test_app_line_plays_when_gemini_fails(self):
        self.fake.fail = True
        r = self.say(FELL)
        self.assertIn(mary.EMERGENCY_TEXT[mary.is_emergency(FELL)], r["text"])
        self.assertNotIn(mary.STAY_TEXT, r["text"])

    def test_non_emergency_not_filtered(self):
        r = self.say("My soup is cold.", "Press your call light if you need help.")
        self.assertIn("call light", r["text"])

    def test_without_steps_direct(self):
        self.assertEqual(mary._without_steps("Press your call light and call 911. I'm here."), "I'm here.")
        out = mary._without_steps("[mood: alert] Call 911. Stay calm.")
        self.assertTrue(out.startswith("[mood: alert]"))
        self.assertIn("Stay calm.", out)
        self.assertNotIn("911", out)
        vet = "If you're a veteran, press one."
        self.assertEqual(mary._without_steps(vet), vet)
        self.assertEqual(mary._without_steps("You need a nurse."), "You need a nurse.")
        self.assertEqual(mary._without_steps("Tell the nurse."), "")


class NameOnce(LiveBase):
    def setUp(self):
        helpers.reset_db()
        (server.DATA / "mary" / "memory.json").unlink(missing_ok=True)
        with closing(server.connect_memories()) as conn:
            conn.execute("DELETE FROM memories")
            conn.commit()

    def test_known_name(self):
        mem = new_memory(name="Dorothy")
        for tags in (True, False):
            text = mary.system_text(mem, "mary", tags=tags)
            self.assertIn(mary.NAME_KNOWN_NOTE, text)
            self.assertNotIn("You don't know their name yet", text)
        self.assertIn(mary.NAME_KNOWN_NOTE, self.live_prompt(mem))
        self.assertNotIn("You don't know their name yet", self.live_prompt(mem))

    def test_no_name_asks(self):
        for tags in (True, False):
            text = mary.system_text(new_memory(), "mary", tags=tags)
            self.assertIn("in this talk or any other", text)
            self.assertNotIn(mary.NAME_KNOWN_NOTE, text)

    def test_asked_once_survives_reload(self):
        mem = new_memory()
        mem.add_turn("model", NAME_ASK)
        self.assertTrue(mem.name_asked)
        mem.save()
        again = mary.Memory(mem.path) if hasattr(mem, "path") else None
        if again is not None:
            self.assertTrue(again.name_asked)
        text = mary.system_text(mem, "mary")
        self.assertIn(mary.NAME_ASKED_NOTE, text)
        self.assertNotIn("You don't know their name yet", text)
        self.assertIn("[name:", text)
        live = mary.system_text(mem, "mary", tags=False)
        self.assertIn(mary.NAME_ASKED_NOTE, live)
        self.assertNotIn("[name:", live)

    def test_add_turn_leaves_flag_alone(self):
        mem = new_memory()
        for text in ("What's your dog's name?", "What was her name?"):
            mem.add_turn("model", text)
        mem.add_turn("user", NAME_ASK)
        self.assertFalse(mem.name_asked)
        known = new_memory(name="Al")
        known.add_turn("model", NAME_ASK)
        self.assertFalse(known.name_asked)

    def test_reply_and_live_said_set_it(self):
        fake = FakeGemini()
        fake.chunks = [NAME_ASK]
        with mock.patch.object(mary, "_gemini_stream", fake):
            mem = new_memory()
            mary.reply("hello", mem, KEY)
        self.assertTrue(mem.name_asked)
        status, _, _ = helpers.api("POST", "/api/mary/live/said", {"text": NAME_ASK})
        self.assertEqual(status, 200)
        self.assertTrue(server.mary_memory().name_asked)

    def test_forgotten_wins(self):
        text = mary.system_text(new_memory(name_forgotten=True, name_asked=True), "mary")
        self.assertIn(mary.NAME_FORGOTTEN_SYSTEM, text)
        self.assertNotIn(mary.NAME_ASKED_NOTE, text)
        self.assertNotIn(mary.NAME_KNOWN_NOTE, text)

    def test_saved_goes_by(self):
        store = memory_core.MemoryStore(server.connect_memories)
        mem = new_memory()
        mem.store = store
        for fact in ("His son goes by Mike", "Okay with being called honey"):
            store.add(fact)
        self.assertNotIn(mary.NAME_KNOWN_NOTE, mary.system_text(mem, "mary"))
        store.add("Likes to be called Sugar")
        text = mary.system_text(mem, "mary")
        self.assertIn(mary.NAME_KNOWN_NOTE, text)
        self.assertNotIn("You don't know their name yet", text)

    def test_stand_in_without_flag(self):
        stand = SimpleNamespace(name="", facts=[], recent=[])
        self.assertIn("in this talk or any other", mary.system_text(stand, "mary"))


class HeardReachesSkills(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        folder = Path(tempfile.mkdtemp(prefix="m4c-skills-", dir=helpers.TMP)) / "skills"
        shutil.copytree(REAL / "word_search", folder / "word_search", ignore=shutil.ignore_patterns("__pycache__"))
        p = mock.patch.object(server, "SKILLS_DIR", folder)
        p.start()
        self.addCleanup(p.stop)
        server.set_skill_host_for_tests(None)
        self.addCleanup(server.set_skill_host_for_tests, None)

    def post(self, name, args=None, **kw):
        body = {"name": name, "args": args if args is not None else {}}
        body.update(kw)
        status, got, _ = helpers.api("POST", "/api/mary/skills/call", body)
        self.assertEqual(status, 200, got)
        return got

    def found(self, out):
        return next((e["data"]["word"] for e in out["effects"] if e["kind"] == "found"), None)

    def puzzle(self):
        return server.skill_host().skills["word_search"].state["puzzle"]

    def test_check_uses_heard(self):
        self.post("word_search__start", {"topic": "fishing"})
        word = self.puzzle()["placed"][0]["word"]
        out = self.post("word_search__check", {}, heard=f"I found the word {word.lower()}")
        self.assertEqual(self.found(out), word)

    def test_use_skill_check_uses_heard(self):
        self.post("open_skill", {"name": "word_search"})
        self.post("use_skill", {"action": "start", "details": GAME_WORDS})
        word = self.puzzle()["placed"][0]["word"]
        out = self.post("use_skill", {"action": "check"}, heard=f"I found the word {word.lower()}")
        self.assertEqual(self.found(out), word)

    def test_odd_heard_is_safe(self):
        self.post("word_search__start", {"topic": "fishing"})
        self.post("word_search__check", {}, heard="x" * 3000)
        self.post("word_search__check", {}, heard=5)
        self.post("word_search__check", {}, heard=["a"])

    def test_emergency_heard_runs_nothing(self):
        host = server.skill_host()
        with mock.patch.object(host, "call") as spy:
            out = self.post("word_search__check", {}, heard=FELL)
        spy.assert_not_called()
        self.assertTrue(out["emergency"])
        self.assertEqual(out["effects"], [])

    def test_normal_passes_heard(self):
        folder = Path(tempfile.mkdtemp(prefix="m4c-normal-", dir=helpers.TMP)) / "skills"
        shutil.copytree(REAL / "word_search", folder / "word_search", ignore=shutil.ignore_patterns("__pycache__"))
        db = folder.parent / "s.db"
        settings = {}
        host = skills_core.SkillHost(folder, folder.parent, lambda: sqlite3.connect(db), lambda: dict(settings),
                                     settings.update)
        host.load(is_blocked=mary.skill_blocked)
        fake = Rounds([tool_call(fc("open_skill", {"name": "word_search"}, "sig"))], ["Okay."])
        said = "I found the word cat"
        with mock.patch.object(mary, "_gemini_stream", fake), \
                mock.patch.object(host, "call", wraps=host.call) as spy:
            mary.reply(said, new_memory(), KEY, skills=host)
        self.assertTrue(spy.called)
        self.assertTrue(all(c.kwargs.get("heard") == said for c in spy.call_args_list))


if __name__ == "__main__":
    unittest.main()
