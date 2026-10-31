from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""Live mode proof (M13): the setup Mary's Live session adds, a simulated Google toolCall round trip
(mirrors handleLiveToolCall in web/mary/skills.js), turning skills off and on by voice, and helper locks."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server

REAL = Path(__file__).resolve().parent.parent / "skills"


def live_round_trip(calls):
    """Same as handleLiveToolCall: one POST per functionCall, then a toolResponse."""
    out = []
    for fc in calls:
        _, res, _ = helpers.api("POST", "/api/mary/skills/call", {"name": fc["name"], "args": fc.get("args") or {}})
        out.append({"id": fc["id"], "name": fc["name"],
                    "response": (res and res.get("response")) or {"error": "no_answer"}})
    return {"functionResponses": out}


class LiveSkills(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        folder = Path(tempfile.mkdtemp(prefix="live-skills-", dir=helpers.TMP)) / "skills"
        shutil.copytree(REAL / "voice_comfort", folder / "voice_comfort",
                        ignore=shutil.ignore_patterns("__pycache__"))
        p = mock.patch.object(server, "SKILLS_DIR", folder)
        p.start()
        self.addCleanup(p.stop)
        server.set_skill_host_for_tests(None)
        self.addCleanup(server.set_skill_host_for_tests, None)

    def _listed(self):
        skills = helpers.api("GET", "/api/mary/skills")[1]["skills"]
        return next(s for s in skills if s["name"] == "voice_comfort")

    def _set(self, on):
        return helpers.api("POST", "/api/mary/skills/call",
                           {"name": "set_skill", "args": {"name": "voice_comfort", "on": on}})[1]

    def test_setup_has_tools_and_text(self):
        setup = server.mary_live_skill_setup()
        names = {d["name"] for t in setup["tools"] for d in t.get("functionDeclarations", [])}
        self.assertIn("open_skill", names)  # M13b
        self.assertIn("use_skill", names)  # M13b
        self.assertIn("set_skill", names)
        self.assertIsInstance(setup["instruction"], str)
        self.assertIn("louder: ", setup["instruction"])  # M13b: an "always" action

    def test_use_skill_through_the_route(self):  # M13b
        self.addCleanup(server.skill_host().set_aside, None)
        got = helpers.api("POST", "/api/mary/skills/call", {"name": "use_skill", "args": {"action": "louder"},
                                                            "aside": "voice_comfort"})[1]
        self.assertNotIn("error", got["response"])
        self.assertEqual(server.skill_host().aside, "voice_comfort")

    def test_round_trip_louder_saves_volume(self):
        helpers.api("PUT", "/api/settings", {"voice_volume": "0.5"})
        msg = {"toolCall": {"functionCalls": [{"id": "c1", "name": "voice_comfort__louder", "args": {}}]}}
        resp = live_round_trip(msg["toolCall"]["functionCalls"])
        json.dumps(resp)
        item = resp["functionResponses"][0]
        self.assertEqual((item["id"], item["name"]), ("c1", "voice_comfort__louder"))
        self.assertNotIn("error", item["response"])
        saved = float(helpers.api("GET", "/api/settings")[1]["voice_volume"])
        self.assertGreater(saved, 0.5)
        self.assertLessEqual(saved, 1.0)

    def test_off_by_voice_and_on_again(self):
        self._set(False)
        self.assertFalse(self._listed()["on"])
        self._set(True)
        self.assertTrue(self._listed()["on"])

    def test_locked_skill_answers_locked(self):
        helpers.api("PUT", "/api/mary/skills/voice_comfort/lock", {"state": "on"})
        res = self._set(False)
        self.assertEqual((res.get("response") or res).get("error"), "locked")
        self.assertTrue(self._listed()["on"])

    def test_my_info_lock_route(self):
        helpers.api("PUT", "/api/mary/skills/voice_comfort/lock", {"state": "off"})
        s = self._listed()
        self.assertEqual((s["locked"], s["on"]), ("off", False))
        helpers.api("PUT", "/api/mary/skills/voice_comfort/lock", {"state": None})
        self.assertIsNone(self._listed()["locked"])


if __name__ == "__main__":
    unittest.main()
