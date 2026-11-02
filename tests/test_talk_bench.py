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
        res = tempfile.TemporaryDirectory()
        self.addCleanup(res.cleanup)
        self.results = Path(res.name) / "out"
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
            code = tb.main(["--talks", self.folder, "--delay", "0", "--results", str(self.results), *argv])
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


def lean_missing():
    """The real fallback: mary.LEAN points at a file that is not there, so the lean brain is not installed."""
    tmp = tempfile.TemporaryDirectory()
    gone = Path(tmp.name) / "no-lean.md"
    patch = mock.patch.object(mary, "LEAN", gone)

    class Gone:
        def __enter__(self):
            patch.start()

        def __exit__(self, *exc):
            patch.stop()
            tmp.cleanup()
            return False

    return Gone()


def lean_sentence():
    """One distinctive line from the real lean brain's Both block."""
    return mary._lean_blocks()["both"].splitlines()[1]


class BrainTests(BenchCase):
    def test_use_brain_restores(self):
        had = hasattr(mary, "brain_setting")
        old = getattr(mary, "brain_setting", None)
        with tb.use_brain("lean"):
            self.assertEqual(mary.brain_setting(), "lean")
        self.assertIs(getattr(mary, "brain_setting", None), old)
        with self.assertRaises(ValueError):
            with tb.use_brain("lean"):
                raise ValueError("x")
        self.assertIs(getattr(mary, "brain_setting", None), old)
        self.assertEqual(hasattr(mary, "brain_setting"), had)
        marker = lambda: "full"  # noqa: E731
        with mock.patch.object(mary, "brain_setting", marker):
            with tb.use_brain("lean"):
                self.assertEqual(mary.brain_setting(), "lean")
            self.assertIs(mary.brain_setting, marker)
            with self.assertRaises(ValueError):
                with tb.use_brain("lean"):
                    raise ValueError("x")
            self.assertIs(mary.brain_setting, marker)

    def test_use_brain_when_attribute_absent(self):
        with mock.patch.object(mary, "brain_setting", create=True):
            del mary.brain_setting
            self.assertFalse(hasattr(mary, "brain_setting"))
            with tb.use_brain("lean"):
                self.assertEqual(mary.brain_setting(), "lean")
            self.assertFalse(hasattr(mary, "brain_setting"))
            with self.assertRaises(ValueError):
                with tb.use_brain("lean"):
                    raise ValueError("x")
            self.assertFalse(hasattr(mary, "brain_setting"))
            mary.brain_setting = None  # so the patch can restore cleanly

    def test_lean_not_installed_is_detected(self):
        with lean_missing():
            self.assertFalse(tb.lean_installed())

    def test_lean_flags_stop_before_spending(self):
        fake = self.fake()
        with lean_missing():
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
        for mode in ("normal", "live"):
            fake = self.fake()
            runs = self.first_run(modes=(mode,), brains=("full", "lean"))
            tb.execute_talks(runs, KEY, "talk-m", "judge-m", 0, no_judge=True)
            self.assertEqual([r["status"] for r in runs], ["finished", "finished"], mode)
            self.assertNotEqual(system_of(fake.talk[0]), system_of(fake.talk[10]), mode)
        code, out = self.main("--brain", "both", "--mode", "normal", "--no-judge")
        self.assertEqual(code, 0, out)

    def test_real_lean_brain_is_detected_and_changes_both_prompts(self):
        self.assertTrue(tb.lean_installed())
        for who in ("mary", "sam"):
            normal, live = {}, {}
            for brain in ("full", "lean"):
                seen = []

                def stub(body, api_key, model="", **extra):
                    seen.append(body)
                    yield "ok"

                with mock.patch.object(mary, "_gemini_stream", stub), tb.use_brain(brain):
                    mary.reply("hello", tb._probe_memory(), "probe-key", "", companion=who)
                    live[brain] = tb.bb.live_system_text(tb._probe_memory(), who)
                normal[brain] = system_of(seen[0])
            self.assertNotEqual(normal["full"], normal["lean"], who)
            self.assertNotEqual(live["full"], live["lean"], who)
            self.assertLess(len(normal["lean"]), len(normal["full"]), who)
            self.assertLess(len(live["lean"]), len(live["full"]), who)


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
        self.assertIn("4 of 4 talks finished", out)
        self.assertIn("Current brain: average score 4.0 out of 5", out)
        self.assertIn("Report: ", out)
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
        self.assertIn("2 of 2 talks finished", out)


def rec(brain="full", mode="normal", replies=None, status="finished", judge=True, **over):
    """A saved-talk record built by hand."""
    lines = turns()
    if replies is None:
        replies = (["Good night, Andrew. That is wonderful, Andrew."] * 10) if brain == "full" else ["Fine, then."] * 10
    out = {"id": "t1", "title": "Andy comes back", "companion": "mary", "resident": "Andrew", "also_called": [],
           "mode": mode, "brain": brain, "status": status, "turns": lines, "replies": replies,
           "counts": tb.count_talk(replies, "Andrew"), "judge": None, "judge_note": "", "error": "", "notes": [],
           "not_run_why": "", "retried": False}
    if judge and status == "finished":
        out["judge"] = {"keep_talking": 2 if brain == "full" else 4, "why": "Wore thin.",
                        "talking_down": {"found": brain == "full", "why": "Too sweet."},
                        "lecturing": {"found": False, "why": ""}, "repeating": {"found": False, "why": ""}}
    out.update(over)
    return out


def data_of(*records):
    return {"date": "2026-11-02", "model": "gemini-x", "judge_model": "gemini-y", "live_model": "", "commit": "abc",
            "talks": list(records)}


CODE_WORDS = ["normal", "real_live", "keep_talking", "None", "t1", "lean", "status", "not_run"]


class ReportTests(BenchCase):
    def assertPlain(self, text):
        for word in CODE_WORDS:
            self.assertNotRegex(text, r"(?<![\w-])" + word + r"(?![\w-])", word)
        self.assertNotRegex(text, r"\bfull\b")

    def test_two_brains(self):
        text = tb.render_report(data_of(rec("full"), rec("lean"), rec("full", "live"), rec("lean", "live")))
        for want in ("# Whole talks, 2026-11-02", "Mary on the model gemini-x. The judge was gemini-y. 1 talk,",
                     "## How the brains compare: Normal talk", "## How the brains compare: Live stand-in",
                     "| | Current brain | Lean brain |", "| Times she used their name | 20 | 0 |",
                     "| Replies with their name in them | 10 of 10 | 0 of 10 |", "| Praise | 10 | 0 |",
                     "## Andy comes back (Mary and Andrew)", "### Normal talk", "#### Current brain", "#### Lean brain",
                     "**Andrew:** Line number 0.", "**Mary:** Fine, then.", "Judge: 2 out of 5. Wore thin. Talking down: Too sweet.",
                     "Judge: 4 out of 5. Wore thin.", "Said more than once: \"Good night, Andrew.\" (10 times, Current brain)",
                     "Praise words: wonderful 10 (Current brain)", tb.LIVE_NOTE):
            self.assertIn(want, text)
        self.assertEqual(text.count(tb.LIVE_NOTE), 1)
        self.assertNotIn("Didn't finish", text)
        self.assertPlain(text)

    def test_one_brain_has_no_lean(self):
        text = tb.render_report(data_of(rec("full", retried=True)))
        self.assertNotIn("Lean brain", text)
        self.assertIn("| | Current brain |", text)
        self.assertIn("This talk had to be run twice.", text)
        self.assertNotIn("Current brain)", text)

    def test_odd_talks(self):
        replies = ["Hello   there\n friend.", "", "Ok."]
        cut = rec("full", replies=replies, status="error", error="Gemini's daily limit ran out partway")
        notjudged = rec("full", mode="live", judge=False, judge_note="not judged: the judge's daily limit ran out")
        never = rec("full", mode="live", status="not_run", replies=[], not_run_why="left out by --max 3", id="t2",
                    title="Another")
        text = tb.render_report(data_of(cut, notjudged, never))
        self.assertIn("**Mary:** Hello there friend.", text)
        self.assertIn("**Mary:** (said nothing)", text)
        self.assertIn("(The talk stopped here.)", text)
        self.assertIn("Not judged: the judge's daily limit ran out", text)
        self.assertIn("## Didn't finish", text)
        self.assertIn("- Andy comes back, Normal talk, Current brain. It stopped after 3 of 10 lines. Gemini's daily limit ran out partway.", text)
        self.assertIn("It was left out because you asked for a limited number of talks.", text)
        self.assertEqual(text.count("**Andrew:**"), 4 + 10)  # the cut talk shows the line it stopped on
        self.assertPlain(text)

    def test_pipe_never_reaches_a_table(self):
        text = tb.render_report(data_of(rec("full", replies=["a | b | wonderful"] * 10)))
        for line in text.splitlines():
            if line.startswith("|"):
                self.assertNotIn("wonderful", line)
                self.assertEqual(line.count("|"), 3)

    def test_unknown_resident_name(self):
        text = tb.render_report(data_of(rec("full", resident="")))
        self.assertIn("(Mary and the resident)", text)
        self.assertIn("**The resident:** Line number 0.", text)


class SavingTests(BenchCase):
    def files(self):
        return sorted(p.name for p in self.results.glob("*")) if self.results.is_dir() else []

    def test_names_and_second_run(self):
        self.fake()
        code, out = self.main("--mode", "normal")
        self.assertEqual(code, 0, out)
        day = tb.datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(self.files(), [f"talks-{day}.json", f"talks-{day}.md"])
        first = (self.results / f"talks-{day}.md").read_text(encoding="utf-8")
        self.main("--mode", "normal")
        self.assertEqual(len(self.files()), 4)
        self.assertIn(f"talks-{day}-2.md", self.files())
        self.assertEqual((self.results / f"talks-{day}.md").read_text(encoding="utf-8"), first)
        code, out = self.main("--mode", "normal")
        self.assertIn(f"Report: {self.results / f'talks-{day}-3.md'}", out)

    def test_json_shape_no_key_no_case(self):
        self.fake()
        self.main("--mode", "normal")
        js = next(self.results.glob("*.json"))
        raw = js.read_text(encoding="utf-8")
        self.assertNotIn(KEY, raw)
        data = json.loads(raw)
        self.assertEqual(set(data), {"date", "model", "judge_model", "live_model", "commit", "talks"})
        self.assertEqual(set(data["talks"][0]), set(tb.RECORD_KEYS))
        self.assertNotIn("case", data["talks"][0])
        self.assertIsInstance(data["commit"], str)
        self.assertNotIn(KEY, next(self.results.glob("*.md")).read_text(encoding="utf-8"))

    def test_key_in_a_reply_is_scrubbed(self):
        self.fake(hook=lambda f, b, m: f"My key is {KEY}.")
        self.main("--mode", "normal", "--no-judge")
        for p in self.results.glob("*"):
            self.assertNotIn(KEY, p.read_text(encoding="utf-8"))

    def test_no_save_and_no_spend(self):
        self.fake()
        self.main("--no-save")
        self.assertEqual(self.files(), [])
        self.main("--list", key="")
        self.assertEqual(self.files(), [])

    def test_nothing_lands_in_bench_results(self):
        before = sorted(p.name for p in tb.bb.RESULTS_DIR.glob("talks-*")) if tb.bb.RESULTS_DIR.is_dir() else []
        self.fake()
        self.main("--mode", "normal")
        after = sorted(p.name for p in tb.bb.RESULTS_DIR.glob("talks-*")) if tb.bb.RESULTS_DIR.is_dir() else []
        self.assertEqual(before, after)

    def test_write_failure_is_a_line_not_a_crash(self):
        self.fake()
        with mock.patch.object(tb, "save_talks", side_effect=OSError("disk full")):
            code, out = self.main("--mode", "normal")
        self.assertEqual(code, 0)
        self.assertIn("Could not save the report: disk full", out)

    def test_md_equals_render_of_json(self):
        self.fake()
        self.main()
        js = next(self.results.glob("*.json"))
        md = js.with_suffix(".md")
        self.assertEqual(tb.render_report(json.loads(js.read_text(encoding="utf-8"))), md.read_text(encoding="utf-8"))


class ResumeTests(BenchCase):
    def first_day(self, *argv):
        self.fake()
        code, out = self.main("--mode", "normal", *argv)
        self.assertEqual(code, 0, out)
        return next(self.results.glob("*.json"))

    def second(self, ext):
        day = tb.datetime.now().strftime("%Y-%m-%d")
        return self.results / f"talks-{day}-2.{ext}"

    def edit(self, path, change):
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_keeps_finished_and_reruns_the_rest(self):
        js = self.first_day()
        def spoil(d):
            d["talks"][1].update(status="error", error="x")
            d["talks"][1]["replies"] = d["talks"][1]["replies"][:3]
        self.edit(js, spoil)
        old = js.read_bytes()
        fake = self.fake()
        code, out = self.main("--mode", "normal", "--resume", str(js))
        self.assertEqual(code, 0, out)
        self.assertIn(f"Kept 1 finished talks from {js}.", out)
        self.assertIn("Gemini requests", out)
        self.assertEqual(len(fake.talk), 10)  # only the one talk that was left
        self.assertEqual(js.read_bytes(), old)
        new = json.loads(self.second("json").read_text(encoding="utf-8"))
        self.assertEqual([(t["id"], t["status"]) for t in new["talks"]], [("t1", "finished"), ("t2", "finished")])

    def test_changed_script_is_dropped_with_a_line(self):
        js = self.first_day()
        self.edit(js, lambda d: d["talks"][0].update(turns=["Different."] * 10))
        fake = self.fake()
        code, out = self.main("--mode", "normal", "--resume", str(js))
        self.assertIn("Not kept: t1, because its lines changed", out)
        self.assertIn("Kept 1 finished talks", out)
        self.assertEqual(len(fake.talk), 10)

    def test_gone_talk_dropped_and_kept_not_judged_stays(self):
        js = self.first_day("--no-judge")
        self.edit(js, lambda d: d["talks"].append(dict(d["talks"][0], id="vanished")))
        self.fake()
        code, out = self.main("--mode", "normal", "--resume", str(js))
        self.assertEqual(code, 0, out)
        self.assertIn("Kept 2 finished talks", out)
        new = json.loads(self.second("json").read_text(encoding="utf-8"))
        self.assertEqual([t["id"] for t in new["talks"]], ["t1", "t2"])
        self.assertTrue(all(t["judge"] is None for t in new["talks"]))

    def test_nothing_left_needs_no_key(self):
        js = self.first_day()
        fake = self.fake()
        code, out = self.main("--mode", "normal", "--resume", str(js), key="")
        self.assertEqual(code, 0, out)
        self.assertIn("no key was needed", out)
        self.assertEqual((fake.talk, fake.judged), ([], []))
        self.assertEqual(len(list(self.results.glob("*.md"))), 2)

    def test_list_shrinks(self):
        js = self.first_day()
        self.edit(js, lambda d: d["talks"][1].update(status="not_run"))
        code, out = self.main("--mode", "normal", "--resume", str(js), "--list", key="")
        self.assertIn("1 talks", out)
        self.assertIn("Kept 1 finished", out)

    def test_max_counts_only_what_is_left(self):
        js = self.first_day()
        self.edit(js, lambda d: d["talks"][1].update(status="not_run"))
        fake = self.fake()
        code, out = self.main("--mode", "normal", "--resume", str(js), "--max", "1")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(fake.talk), 10)

    def test_model_mismatch_stops(self):
        js = self.first_day()
        self.edit(js, lambda d: d["talks"][0].update(status="error") or d.update(model="other-model"))
        fake = self.fake()
        code, out = self.main("--mode", "normal", "--resume", str(js))
        self.assertEqual(code, 2)
        self.assertIn("other-model", out)
        self.assertEqual((fake.talk, fake.judged), ([], []))

    def test_missing_and_bad_files(self):
        self.fake()
        code, out = self.main("--resume", str(self.results / "nope.json"))
        self.assertEqual(code, 2)
        self.assertIn("Can't read the saved run", out)
        bad = self.results
        bad.mkdir(parents=True, exist_ok=True)
        (bad / "bad.json").write_text("{nonsense", encoding="utf-8")
        (bad / "odd.json").write_text("[1]", encoding="utf-8")
        for name in ("bad.json", "odd.json"):
            code, out = self.main("--resume", str(bad / name))
            self.assertEqual(code, 2, name)
            self.assertNotIn("Traceback", out)

    def test_lean_added_beside_a_saved_full_run(self):
        js = self.first_day()
        self.with_fake_lean()
        fake = self.fake()
        code, out = self.main("--mode", "normal", "--brain", "lean", "--resume", str(js))
        self.assertEqual(code, 0, out)
        self.assertEqual(len(fake.talk), 20)
        md = self.second("md").read_text(encoding="utf-8")
        self.assertIn("| | Current brain | Lean brain |", md)
        self.assertIn("Lean brain: average score", out)
        self.assertIn("Current brain: average score", out)


class DecisionD4(BenchCase):
    def test_d4_a_lean_run_never_silently_runs_full(self):
        fake = self.fake()
        with lean_missing():
            code, out = self.main("--brain", "lean")
        self.assertEqual(code, 2)
        self.assertIn("lean brain not installed", out)
        self.assertEqual((fake.talk, fake.judged), ([], []))
        self.assertEqual(self.results.exists(), False)
        mark = lean_sentence()
        code, out = self.main("--brain", "lean", "--mode", "normal", "--no-judge")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(fake.talk), 20)
        self.assertTrue(all(mark in system_of(b) for b in fake.talk))
        fake.talk.clear()
        code, out = self.main("--brain", "full", "--mode", "normal", "--no-judge")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(fake.talk), 10 * 2)
        self.assertFalse(any(mark in system_of(b) for b in fake.talk))


def leaner_missing():
    """mary.LEANER points at a file that is not there, so the leaner brain is not installed."""
    tmp = tempfile.TemporaryDirectory()
    patch = mock.patch.object(mary, "LEANER", Path(tmp.name) / "no-leaner.md")

    class Gone:
        def __enter__(self):
            patch.start()

        def __exit__(self, *exc):
            patch.stop()
            tmp.cleanup()
            return False

    return Gone()


class LeanerBrainTests(BenchCase):
    def parse(self, text):
        return tb.parse_args(["--brain", text]).brain

    def test_brain_parsing(self):
        self.assertEqual(self.parse("full"), ("full",))
        self.assertEqual(self.parse("lean"), ("lean",))
        self.assertEqual(self.parse("leaner"), ("leaner",))
        self.assertEqual(self.parse("leaner,lean"), ("lean", "leaner"))
        self.assertEqual(self.parse("both"), ("full", "lean"))
        self.assertEqual(tb.parse_args([]).brain, ("full",))
        for bad in ("fuller", "lean,nope", "both,leaner", ""):
            with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(io.StringIO()):
                self.parse(bad)
            self.assertEqual(caught.exception.code, 2, bad)

    def test_bad_brain_spends_nothing(self):
        fake = self.fake()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.main("--brain", "nope")
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual((fake.talk, fake.judged), ([], []))

    def test_plan_order_is_fixed(self):
        runs = tb.plan_talks(self.talks, brains=("leaner", "full", "lean"))
        want = [(m, t, b) for m in ("normal", "live") for t in ("t1", "t2") for b in ("full", "lean", "leaner")]
        self.assertEqual([(r["mode"], r["id"], r["brain"]) for r in runs], want)

    def test_real_leaner_is_installed_and_differs(self):
        self.assertTrue(tb.bb.brain_installed("leaner"))
        self.assertEqual(tb.bb.missing_brains(("lean", "leaner")), [])

    def test_leaner_missing_stops_before_spending(self):
        fake = self.fake()
        with leaner_missing():
            self.assertFalse(tb.bb.brain_installed("leaner"))
            for brain in ("leaner", "lean,leaner"):
                code, out = self.main("--brain", brain)
                self.assertEqual(code, 2, brain)
                self.assertIn("leaner brain not installed", out)
            self.assertEqual((fake.talk, fake.judged), ([], []))
            code, out = self.main("--brain", "leaner", "--list", key="")
            self.assertEqual(code, 0)
            self.assertIn("leaner brain not installed", out)

    def test_lean_and_leaner_run_in_order(self):
        fake = self.fake()
        code, out = self.main("--brain", "lean,leaner", "--mode", "normal", "--no-judge", "--only", "t1")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(fake.talk), 20)
        self.assertNotIn("Their interests come first", system_of(fake.talk[0]))
        self.assertIn("Their interests come first", system_of(fake.talk[10]))

    def test_report_for_lean_and_leaner(self):
        text = tb.render_report(data_of(rec("lean"), rec("leaner"), rec("lean", "live"), rec("leaner", "live")))
        self.assertIn("| | Lean brain | Leaner brain |", text)
        self.assertIn("each under both brains: Lean brain and Leaner brain.", text)
        self.assertIn("#### Leaner brain", text)
        self.assertNotIn("Current brain", text)

    def test_report_for_three_brains_and_two_brains_unchanged(self):
        text = tb.render_report(data_of(rec("full"), rec("lean"), rec("leaner")))
        self.assertIn("| | Current brain | Lean brain | Leaner brain |", text)
        self.assertIn("each under all three brains: Current brain, Lean brain and Leaner brain.", text)
        two = tb.render_report(data_of(rec("full"), rec("lean")))
        self.assertIn("each under both brains: Current brain and Lean brain.", two)
        self.assertNotIn("Leaner", two)


if __name__ == "__main__":
    unittest.main()
