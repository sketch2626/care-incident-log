from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)
import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import mary
from tools import talk_bench as tb


def turns(n=10):
    return [f"Line number {i}." for i in range(n)]


def talk(**over):
    base = {"id": "t1", "title": "A talk", "companion": "mary", "turns": turns()}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


class LoadTests(unittest.TestCase):
    def folder(self, *talks, raw=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for i, t in enumerate(talks):
            Path(tmp.name, f"t{i}.json").write_text(json.dumps(t), encoding="utf-8")
        if raw is not None:
            Path(tmp.name, "raw.json").write_text(raw, encoding="utf-8")
        return tmp.name

    def refused(self, folder, word):
        with self.assertRaises(tb.bb.BenchError) as cm:
            tb.load_talks(folder)
        self.assertIn(word, str(cm.exception))

    def test_real_talks(self):
        talks = tb.load_talks()
        self.assertEqual(sum(t["companion"] == "mary" for t in talks), 8)
        self.assertEqual(sum(t["companion"] == "sam" for t in talks), 4)
        self.assertEqual(len({t["id"] for t in talks}), len(talks))
        for t in talks:
            self.assertTrue(10 <= len(t["turns"]) <= 15, t["id"])
            self.assertTrue(t["title"], t["id"])
            self.assertIsInstance(t["also_called"], list)
            for line in t["turns"]:
                self.assertFalse(mary.is_emergency(line), f"{t['id']}: {line}")

    def test_good_folder_keeps_title_and_names(self):
        got = tb.load_talks(self.folder(talk(also_called=["Drew"])))
        self.assertEqual((got[0]["title"], got[0]["also_called"]), ("A talk", ["Drew"]))

    def test_refusals(self):
        self.refused(self.folder(), "no talk files")
        self.refused(self.folder(raw="{not json"), "raw.json")
        self.refused(self.folder(talk(companion="both")), "companion")
        self.refused(self.folder(talk(companion=None)), "companion")
        self.refused(self.folder(talk(mode="normal")), "mode")
        self.refused(self.folder(talk(turns=turns(9))), "10 to 15")
        self.refused(self.folder(talk(turns=turns(16))), "10 to 15")
        self.refused(self.folder(talk(title=None)), "title")
        self.refused(self.folder(talk(), talk()), "t1")


class CountTests(unittest.TestCase):
    def test_andys_examples(self):
        c = tb.count_talk(["Good night, Andy. Good night, Andy.", "I'm here."], "Andy")
        self.assertEqual((c["name_uses"], c["name_replies"]), (2, 1))
        self.assertEqual(c["repeats"], [{"sentence": "Good night, Andy.", "times": 2}])
        self.assertEqual((c["repeat_total"], c["stock"], c["stock_total"]), (1, {"i'm here": 1}, 1))

    def test_made_up_and_name(self):
        c = tb.count_talk(["Oh, hello, Andrew. It's good to see you again. I was just thinking about the card we just "
                           "made"], "Andrew")
        self.assertEqual(c["name_uses"], 1)
        self.assertEqual(c["made_up"], {"i was just thinking": 1})
        self.assertEqual(c["made_up_total"], 1)

    def test_nearly_same_sentence_repeats(self):
        c = tb.count_talk(["Like I said, Sarah is still right there in your book",
                           "Like I said, Sarah is still right there in the book"])
        self.assertEqual(c["repeat_total"], 1)
        self.assertEqual(c["repeats"][0]["times"], 2)

    def test_short_sentences_not_repeats(self):
        self.assertEqual(tb.count_talk(["Yes sir.", "Yes sir."])["repeats"], [])

    def test_name_rules(self):
        c = tb.count_talk(["Andy's right. Andy, yes.", "Sandy came by.", "Drew is here."], "Andy", ["Drew"])
        self.assertEqual((c["name_uses"], c["name_replies"]), (3, 2))
        self.assertEqual(tb.count_talk(["Andy."])["name_uses"], 0)
        self.assertEqual(tb.count_talk(["Andy."], "Andy")["name_uses"], 1)

    def pets(self, text):
        return tb.count_talk([text])["pet_total"]

    def test_pet_false_positives(self):
        for text in ["I like honey on a biscuit.", "Watch your blood sugar.", "Oh dear, that's a lot.",
                     "Oh dear.", "Dear Lord, help us.", "I love that show.", "That's an honest answer.",
                     "She's a sweetheart of a nurse."]:
            self.assertEqual(self.pets(text), 0, text)

    def test_pet_true_positives(self):
        for text in ["Oh, honey, I'm sorry.", "Well honey I know.", "Take care, darlin'.", "Take care, darlin.",
                     "You rest, my dear.", "Sweetie, listen.", "Thank you, dear.", "Hey hon, sit down.",
                     "Goodnight, love.", "I'll miss you, my love.", "Now young man, that's enough."]:
            self.assertEqual(self.pets(text), 1, text)

    def test_pet_names_listed(self):
        c = tb.count_talk(["Oh, honey, yes. Honey, no."])
        self.assertEqual((c["pet_names"], c["pet_total"]), ({"honey": 2}, 2))

    def test_curly_apostrophes(self):
        self.assertEqual(tb.count_talk(["I’m here for you."])["stock"], {"i'm here for you": 1})
        self.assertEqual(tb.count_talk(["Take care, darlin’."])["pet_total"], 1)

    def test_stock_counts_once(self):
        c = tb.count_talk(["I'm here for you.", "Here for you.", "I'm hereby done.", "I'm here, and I hear you."])
        self.assertEqual(c["stock"], {"i'm here for you": 1, "here for you": 1, "i'm here": 1, "i hear you": 1})
        self.assertEqual(c["stock_total"], 4)

    def test_praise(self):
        c = tb.count_talk(["That's wonderful! Great job. Well done, and so proud."])
        self.assertEqual(c["praise"], {"wonderful": 1, "great job": 1, "well done": 1, "so proud": 1})
        self.assertEqual(c["praise_total"], 4)

    def test_openers(self):
        c = tb.count_talk(["Andy, that sounds hard to me.", "That sounds hard, truly.", "Well, then.", "Yes.", "Oh my."],
                          "Andy")
        self.assertEqual(c["openers"], [{"opener": "that sounds hard", "times": 2}])
        self.assertEqual(c["opener_total"], 1)

    def test_blanks_and_numbers(self):
        c = tb.count_talk(["", "  ", "What is it? Are you sure?", "One two three four.", "Really?"])
        self.assertEqual((c["replies"], c["blank"]), (5, 2))
        self.assertEqual((c["questions_avg"], c["questions_max"], c["ended_on_question"]), (1.0, 2, 2))
        self.assertEqual((c["words_avg"], c["words_max"]), (4, 6))

    def test_empty(self):
        c = tb.count_talk([])
        self.assertEqual((c["replies"], c["questions_avg"], c["words_avg"], c["name_uses"]), (0, 0.0, 0, 0))


KEY = "SECRET-KEY-XYZ-123"
VERDICT = {"keep_talking": 4, "why": "Good.", "talking_down": {"found": False, "why": ""},
           "lecturing": {"found": False, "why": ""}, "repeating": {"found": True, "why": "Same opener."}}


def system_of(body):
    return ((body.get("systemInstruction") or {}).get("parts") or [{}])[0].get("text", "")


class JudgeGone:
    """A hook whose judge call raises QuotaGone; talk calls are left alone."""

    def __call__(self, fake, body, model):
        return None

    def judge(self, fake, body, model):
        raise tb.bb.QuotaGone("judge-m")


class Fake:
    """A stand-in for mary._gemini_stream: no network. The judge's call is told by its system text."""

    def __init__(self, judge=None, hook=None):
        self.talk, self.judged = [], []
        self.judge_answers = list(judge) if judge is not None else [json.dumps(VERDICT)]
        self.hook = hook  # hook(fake, body, model) on each talk request: may raise, or return the reply text

    def __call__(self, body, key, model="", **extra):
        if "You read one whole talk" in system_of(body):
            self.judged.append((body, model))
            if getattr(self.hook, "judge", None):
                self.hook.judge(self, body, model)
            yield self.judge_answers.pop(0) if len(self.judge_answers) > 1 else self.judge_answers[0]
            return
        self.talk.append(body)
        said = self.hook(self, body, model) if self.hook else None
        yield f"Reply {len(self.talk)} here." if said is None else said


class BenchCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name, who in (("t1", "mary"), ("t2", "sam")):
            Path(tmp.name, f"{name}.json").write_text(json.dumps(talk(id=name, companion=who)), encoding="utf-8")
        self.folder = tmp.name
        self.talks = tb.load_talks(self.folder)
        patch = mock.patch.object(tb.bb, "pause", lambda s: None)
        patch.start()
        self.addCleanup(patch.stop)

    def fake(self, **kw):
        fake = Fake(**kw)
        patch = mock.patch.object(mary, "_gemini_stream", fake)
        patch.start()
        self.addCleanup(patch.stop)
        return fake

    def with_fake_lean(self):
        real = mary.load_instructions

        def load(*a, **k):
            if getattr(mary, "brain_setting", None) and mary.brain_setting() == "lean":
                return "Be brief and plain."
            return real(*a, **k)

        patch = mock.patch.object(mary, "load_instructions", load)
        patch.start()
        self.addCleanup(patch.stop)

    def first_run(self, modes=("normal",), **kw):
        return tb.plan_talks(self.talks, only="t1", modes=modes, **kw)

    def run_plan(self, modes=("normal",), brains=("full",), **kw):
        runs = tb.plan_talks(self.talks, modes=modes, brains=brains)
        return runs, tb.execute_talks(runs, KEY, "talk-m", "judge-m", 0, **kw)

    def main(self, *argv, key=KEY):
        env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "GEMINI_MODEL")}
        if key:
            env["GEMINI_API_KEY"] = key
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out):
            code = tb.main(["--talks", self.folder, "--delay", "0", *argv])
        return code, out.getvalue()


class PlanTests(BenchCase):
    def test_order(self):
        runs = tb.plan_talks(self.talks, brains=("lean", "full"))
        want = [(m, t, b) for m in ("normal", "live") for t in ("t1", "t2") for b in ("full", "lean")]
        self.assertEqual([(r["mode"], r["id"], r["brain"]) for r in runs], want)
        self.assertTrue(all(r["counts"] is None and r["judge"] is None for r in runs))

    def test_filters(self):
        self.assertEqual({r["id"] for r in tb.plan_talks(self.talks, only="t2")}, {"t2"})
        self.assertEqual({r["id"] for r in tb.plan_talks(self.talks, companion="mary")}, {"t1"})
        self.assertEqual(tb.plan_talks(self.talks, only="zzz"), [])

    def test_max(self):
        self.fake()
        runs, _ = self.run_plan(modes=("normal", "live"), max_runs=3, no_judge=True)
        self.assertEqual([r["status"] for r in runs], ["finished"] * 3 + ["not_run"])
        self.assertIn("--max 3", runs[3]["not_run_why"])

    def test_list_shows_plan_and_spends_nothing(self):
        fake = self.fake()
        code, out = self.main("--list", "--max", "3", key="")
        self.assertEqual(code, 0)
        self.assertIn("t1 (mary, 10 turns)", out)
        self.assertIn("left out by --max 3", out)
        self.assertIn("Gemini requests", out)
        self.assertEqual((fake.talk, fake.judged), ([], []))


class TalkTests(BenchCase):
    def test_later_turn_carries_her_earlier_replies(self):
        for mode in ("normal", "live"):
            fake = self.fake()
            runs = self.first_run(modes=(mode,))
            tb.execute_talks(runs, KEY, "talk-m", "judge-m", 0, no_judge=True)
            self.assertEqual(runs[0]["status"], "finished", (mode, runs[0]["error"]))
            self.assertEqual(len(runs[0]["replies"]), 10)
            self.assertIn("Reply 1 here.", json.dumps(fake.talk[4]), mode)
            self.assertEqual(runs[0]["counts"]["replies"], 10)

    def blank_adapter(self, blanks):
        """A talker that answers "" on the given turn numbers (Mary's own code turns a blank Gemini answer into an
        error, but a turn she handles herself, like "go to sleep", is blank)."""
        def adapter(run, memory, key, model, gemini):
            for n, _ in enumerate(run["turns"], 1):
                run["replies"].append("" if blanks is None or n in blanks else f"Reply {n}.")
        return adapter

    def test_blank_turn_is_data(self):
        self.fake()
        runs = self.first_run()
        with mock.patch.dict(tb.OTHER_MODELS, {"x-": self.blank_adapter({3})}):
            tb.execute_talks(runs, KEY, "x-model", "judge-m", 0)
        self.assertEqual(runs[0]["status"], "finished", runs[0]["error"])
        self.assertEqual(runs[0]["counts"]["blank"], 1)
        self.assertEqual(runs[0]["judge"]["keep_talking"], 4)

    def test_all_blank_is_an_error(self):
        fake = self.fake()
        runs = self.first_run()
        with mock.patch.dict(tb.OTHER_MODELS, {"x-": self.blank_adapter(None)}):
            tb.execute_talks(runs, KEY, "x-model", "judge-m", 0)
        self.assertEqual(fake.judged, [])
        self.assertEqual((runs[0]["status"], runs[0]["error"]), ("error", tb.bb.EMPTY_ANSWER))
        self.assertEqual(runs[0]["counts"]["blank"], 10)

    def test_failed_turn_keeps_partial(self):
        def boom(f, body, m):
            if len(f.talk) >= 5:
                raise urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b""))
        self.fake(hook=boom)
        runs = self.first_run()
        tb.execute_talks(runs, KEY, "talk-m", "judge-m", 0)
        run = runs[0]
        self.assertEqual(run["status"], "error")
        self.assertEqual((len(run["replies"]), run["counts"]["replies"]), (4, 4))
        self.assertIsNone(run["judge"])

    def test_timeout_retries_whole_talk_once(self):
        def slow(f, body, m):
            if len(f.talk) == 5:
                raise urllib.error.URLError("timed out")
        fake = self.fake(hook=slow)
        runs = self.first_run()
        tb.execute_talks(runs, KEY, "talk-m", "judge-m", 0)
        run = runs[0]
        self.assertEqual(run["status"], "finished", run["error"])
        self.assertTrue(run["retried"])
        self.assertEqual(len(run["replies"]), 10)
        self.assertEqual(len(fake.talk), 15)
        self.assertTrue(run["notes"])

    def test_quota_in_a_talk_stops_the_rest(self):
        def gone(f, body, m):
            if len(f.talk) == 14:
                raise tb.bb.QuotaGone("talk-m")
        self.fake(hook=gone)
        runs, info = self.run_plan(modes=("normal", "live"))
        self.assertEqual([r["status"] for r in runs], ["finished", "error", "not_run", "not_run"])
        self.assertEqual(info["quota_model"], "talk-m")
        self.assertEqual((len(runs[1]["replies"]), runs[1]["counts"]["replies"]), (3, 3))
        self.assertEqual(runs[1]["not_run_why"], "")
        self.assertIn("daily limit partway", " ".join(runs[1]["notes"]))
        self.assertEqual(runs[2]["not_run_why"], tb.bb.QUOTA_STOP)
        self.assertIsNotNone(runs[0]["judge"])

    def test_quota_in_the_judge_keeps_every_talk(self):
        fake = self.fake(hook=JudgeGone())
        runs, info = self.run_plan(modes=("normal", "live"))
        self.assertEqual([r["status"] for r in runs], ["finished"] * 4)
        self.assertTrue(all(len(r["replies"]) == 10 and r["judge"] is None and "not judged" in r["judge_note"]
                            for r in runs))
        self.assertTrue(info["judge_stopped"])
        self.assertEqual(info["quota_model"], "")
        self.assertEqual(len(fake.judged), 1)

    def test_key_refused_stops_all(self):
        def refuse(f, body, m):
            if len(f.talk) == 3:
                raise tb.bb.KeyRefused()
        self.fake(hook=refuse)
        runs, info = self.run_plan(modes=("normal", "live"))
        self.assertTrue(info["key_refused"])
        self.assertEqual([r["status"] for r in runs], ["error", "not_run", "not_run", "not_run"])


class BrainTests(BenchCase):
    def test_use_brain_restores(self):
        self.assertFalse(hasattr(mary, "brain_setting"))
        with tb.use_brain("lean"):
            self.assertEqual(mary.brain_setting(), "lean")
        self.assertFalse(hasattr(mary, "brain_setting"))
        with self.assertRaises(ValueError):
            with tb.use_brain("lean"):
                raise ValueError("x")
        self.assertFalse(hasattr(mary, "brain_setting"))
        old = lambda: "full"  # noqa: E731
        mary.brain_setting = old
        try:
            with tb.use_brain("lean"):
                self.assertEqual(mary.brain_setting(), "lean")
            self.assertIs(mary.brain_setting, old)
        finally:
            del mary.brain_setting

    def test_lean_not_installed_today(self):
        self.assertFalse(tb.lean_installed())
        self.assertFalse(hasattr(mary, "brain_setting"))

    def test_lean_flags_stop_before_spending(self):
        fake = self.fake()
        for brain in ("lean", "both"):
            code, out = self.main("--brain", brain)
            self.assertEqual(code, 2, brain)
            self.assertIn("lean brain not installed", out)
            self.assertIn("--brain full", out)
        self.assertEqual((fake.talk, fake.judged), ([], []))
        code, out = self.main("--brain", "lean", "--list", key="")
        self.assertEqual(code, 0)
        self.assertIn("lean brain not installed", out)
        self.assertIn("t1 (mary, 10 turns)", out)
        self.assertIn("Gemini requests", out)

    def test_fake_lean_is_detected_and_bodies_differ(self):
        self.with_fake_lean()
        self.assertTrue(tb.lean_installed())
        self.assertFalse(hasattr(mary, "brain_setting"))
        for mode in ("normal", "live"):
            fake = self.fake()
            runs = self.first_run(modes=(mode,), brains=("full", "lean"))
            tb.execute_talks(runs, KEY, "talk-m", "judge-m", 0, no_judge=True)
            self.assertEqual([r["status"] for r in runs], ["finished", "finished"], mode)
            self.assertNotEqual(system_of(fake.talk[0]), system_of(fake.talk[10]), mode)
        self.assertFalse(hasattr(mary, "brain_setting"))
        code, out = self.main("--brain", "both", "--mode", "normal", "--no-judge")
        self.assertEqual(code, 0, out)


class JudgeTests(BenchCase):
    def test_judge_is_blind(self):
        self.with_fake_lean()
        for brain, mode in (("full", "normal"), ("lean", "live")):
            fake = self.fake()
            run = self.first_run(modes=(mode,), brains=(brain,))
            tb.execute_talks(run, KEY, "talk-m", "judge-m", 0)
            self.assertEqual(len(fake.judged), 1)
            body = json.dumps(fake.judged[0][0]).lower()
            for word in ("lean", "full", "normal", "live", "brain", "mode"):
                self.assertNotIn(word, body)
            data = json.loads(fake.judged[0][0]["contents"][0]["parts"][0]["text"].split("\n", 1)[1])
            self.assertEqual(set(data), {"companion", "name_on_file", "facts_on_file", "earlier_talk", "transcript"})
            self.assertEqual(len(data["transcript"]), 10)
            self.assertEqual(fake.judged[0][0]["generationConfig"]["temperature"], 0)
            self.assertEqual(run[0]["judge"]["keep_talking"], 4)

    def test_bad_answer_gets_one_stricter_retry(self):
        fake = self.fake(judge=["no idea", json.dumps(VERDICT)])
        run = self.first_run()
        tb.execute_talks(run, KEY, "talk-m", "judge-m", 0)
        self.assertEqual(len(fake.judged), 2)
        self.assertNotIn("could not be read", system_of(fake.judged[0][0]))
        self.assertIn("could not be read", system_of(fake.judged[1][0]))
        self.assertEqual(run[0]["judge"]["keep_talking"], 4)

    def test_two_bad_answers_leave_talk_finished_not_judged(self):
        fake = self.fake(judge=["still no idea " + KEY])
        run = self.first_run()
        tb.execute_talks(run, KEY, "talk-m", "judge-m", 0)
        self.assertEqual(len(fake.judged), 2)
        self.assertEqual(run[0]["status"], "finished")
        self.assertIsNone(run[0]["judge"])
        self.assertIn("not judged", run[0]["judge_note"])

    def test_no_judge_means_no_call(self):
        fake = self.fake()
        tb.execute_talks(self.first_run(), KEY, "talk-m", "judge-m", 0, no_judge=True)
        self.assertEqual(fake.judged, [])

    def test_parse_judge(self):
        good = json.dumps(VERDICT)
        self.assertEqual(tb.parse_judge("Here you go:\n```json\n" + good + "\n```\nDone.")["keep_talking"], 4)
        self.assertEqual(tb.parse_judge(good.replace('"keep_talking": 4', '"keep_talking": "5"'))["keep_talking"], 5)
        self.assertTrue(tb.parse_judge(good.replace("true", '"True"'))["repeating"]["found"])
        for bad in ("", "nothing", "{broken", "[1]", good.replace("4", "6", 1), good.replace("4", "0", 1),
                    good.replace('"keep_talking": 4', '"keep_talking": true'),
                    good.replace('"keep_talking": 4', '"keep_talking": 4.5'),
                    good.replace('"keep_talking": 4', '"keep_talking": "high"'),
                    good.replace("true", '"maybe"'),
                    json.dumps({"keep_talking": 3, "why": "x"})):
            self.assertIsNone(tb.parse_judge(bad), bad)
        long = json.loads(good)
        long["why"] = "w" * 500
        self.assertLessEqual(len(tb.parse_judge(json.dumps(long))["why"]), 170)


class CommandLineTests(BenchCase):
    def test_a_good_run(self):
        self.fake()
        code, out = self.main()
        self.assertEqual(code, 0, out)
        self.assertIn("t1 normal full finished keep_talking=4", out)
        self.assertIn("t2 live full finished keep_talking=4", out)
        self.assertNotIn(KEY, out)

    def test_no_key_spends_nothing(self):
        fake = self.fake()
        code, out = self.main(key="")
        self.assertEqual(code, 2)
        self.assertIn("No Gemini key", out)
        self.assertEqual((fake.talk, fake.judged), ([], []))

    def test_claude_without_adapter(self):
        fake = self.fake()
        code, out = self.main("--model", "claude-x")
        self.assertEqual(code, 2)
        self.assertIn("No Claude adapter yet", out)
        self.assertEqual((fake.talk, fake.judged), ([], []))

    def test_other_models_adapter_is_used(self):
        self.fake()
        seen = []

        def adapter(run, memory, key, model, gemini):
            seen.append(model)
            run["replies"].append("Hello there.")

        with mock.patch.dict(tb.OTHER_MODELS, {"claude": adapter}):
            self.assertIs(tb.talker("normal", "claude-x"), adapter)
            self.assertIs(tb.talker("normal", "gemini-x"), tb.bb.TALK["normal"])
            code, out = self.main("--model", "claude-x", "--mode", "normal", "--no-judge")
        self.assertEqual((code, len(seen)), (0, 2), out)

    def test_refused_key_does_not_leak(self):
        def refuse(f, body, m):
            raise tb.bb.KeyRefused()
        self.fake(hook=refuse)
        code, out = self.main()
        self.assertEqual(code, 2)
        self.assertIn("refused the key", out)
        self.assertNotIn(KEY, out)

    def test_real_live(self):
        calls = []

        def real_live(run, memory, key, model, gemini):
            calls.append(run["id"])
            run["replies"].extend(["Hi."] * len(run["turns"]))

        fake = self.fake()
        with mock.patch.dict(tb.bb.TALK, {"real_live": real_live}):
            code, out = self.main("--real-live", "--mode", "normal")
            self.assertEqual((code, calls), (2, []))
            self.assertIn("can't go with --mode", out)
            code, out = self.main("--real-live")
        self.assertEqual((code, calls), (0, ["t1", "t2"]), out)
        self.assertEqual((len(fake.judged), fake.talk), (2, []))
        self.assertIn("t1 real_live full finished", out)


if __name__ == "__main__":
    unittest.main()
