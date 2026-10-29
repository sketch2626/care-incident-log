from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""Skill contract (docs/skills-design.md section 8): runs on every folder in skills/ and on the test fixtures.
A good skill passes all 10 checks; each bad fixture is refused for its own reason. No real data, no network."""
import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

import mary
import skills_core

ROOT = Path(__file__).resolve().parent.parent
SHIPPED = ROOT / "skills"
FIXTURES = Path(__file__).resolve().parent / "skill_fixtures"
BAD = {"bad_import": "imports urllib", "bad_schema": "outside the Gemini subset", "no_handler": "no handler for spin",
       "raises": "ZeroDivisionError", "sleeps": "Timeout"}
FAST_TIMEOUT = 0.15

# Loads a screen.js with a stand-in MarySkills and prints the names it registered (check 10).
NODE_CHECK = r"""
const fs = require('fs'), vm = require('vm');
const names = [];
const any = new Proxy(function () {}, {get: (t, k) => (k === Symbol.toPrimitive ? () => '' : any),
                                      apply: () => any, construct: () => any});
const box = {MarySkills: {register: (name) => { names.push(name); }}, document: any, console,
             setTimeout, clearTimeout};
box.window = box;
vm.runInNewContext(fs.readFileSync(process.argv[process.argv.length - 1], 'utf8'), box, {timeout: 1000});
process.stdout.write(JSON.stringify(names));
"""


def skill_folders(base):
    """Every skill folder under base (none yet in skills/)."""
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


def phrase_blocked(phrase):
    """True when an offline phrase is an emergency, yes or no line (check 9)."""
    return bool(mary.is_emergency(phrase) or mary.is_yes(phrase) or mary.is_decline(phrase))


def minimal_args(schema):
    """The smallest valid arguments for a schema: required fields only, the first choice, the lowest number."""
    kind = schema.get("type", "object")
    if kind == "object":
        props = schema.get("properties", {})
        return {key: minimal_args(props[key]) for key in schema.get("required", [])}
    if "enum" in schema:
        return schema["enum"][0]
    if kind == "string":
        return "a" if schema.get("maxLength", 1) >= 1 else ""
    if kind in ("integer", "number"):
        value = schema.get("minimum", 0)
        value = min(value, schema["maximum"]) if "maximum" in schema else value
        return int(value) if kind == "integer" else value
    return False if kind == "boolean" else []


def refuse_fetch(skill_name, url, **kwargs):
    """ctx.fetch for the smoke test: the internet is never there."""
    raise skills_core.SkillFetchError("offline")


class Scratch:
    """A temp folder with copies of skill folders, a temp sqlite file and in-memory settings."""

    def __init__(self, folders):
        self.dir = Path(tempfile.mkdtemp(prefix="skills-contract-"))
        self.skills = self.dir / "skill_code"
        self.skills.mkdir()
        for folder in folders:
            shutil.copytree(folder, self.skills / folder.name, ignore=shutil.ignore_patterns("__pycache__"))
        self.settings = {}

    def host(self, **kwargs):
        db = self.dir / "skills.db"
        host = skills_core.SkillHost(self.skills, self.dir, lambda: sqlite3.connect(db), lambda: dict(self.settings),
                                     self.settings.update, **kwargs)
        host.load(is_blocked=phrase_blocked)
        return host

    def last_error(self, name):
        log = self.dir / "skills.log"
        lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        errors = [line["error"] for line in lines if line.get("event") == "failure" and line.get("skill") == name]
        return errors[-1] if errors else "?"

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def contract_problems(folder, fast=False):
    """Contract checks 1-9 on one skill folder (10 is the Node check below). Short problems; empty = it passes."""
    try:
        manifest = skills_core.adapt(skills_core.read_manifest(folder))
    except skills_core.SkillLoadError as err:
        return [f"check 1: {err}"]
    problems = [f"checks 1-4: {p}" for p in skills_core.manifest_problems(manifest, folder.name)]
    if problems:
        return problems
    if (folder / "skill.py").is_file():
        problems += [f"check 6: {p}" for p in skills_core.source_problems(folder / "skill.py")]
    for action in manifest["actions"]:
        problems += [f"check 9: {p!r} clashes with emergency or yes/no words"
                     for p in action.get("offline_phrases", []) if phrase_blocked(p)]
    if manifest.get("screen") and not (folder / "screen.js").is_file():
        problems.append("check 10: screen is set but there's no screen.js")
    if problems:
        return problems
    limits = {"timeout": FAST_TIMEOUT} if fast else {}
    name = manifest["name"]
    scratch = Scratch([folder])
    try:
        hosts = [("offline", scratch.host(online=lambda: False, **limits)),
                 ("with no internet", scratch.host(fetcher=refuse_fetch, **limits))]
        if name not in hosts[0][1].skills:
            return [f"check 5: {hosts[0][1].load_errors.get(name)}"]
        for label, host in hosts:
            for action in manifest["actions"]:
                fn = f"{name}__{action['name']}"
                out = host.call(fn, minimal_args(action.get("inputSchema", {"type": "object"})))
                error = out["response"].get("error")
                if error == "not_working":
                    problems.append(f"check 7: {fn} {label} answered not_working ({scratch.last_error(name)})")
                elif error in ("bad_input", "unknown_tool", "off"):
                    problems.append(f"check 7: {fn} {label} answered {error}")
                if len(json.dumps(out["response"])) > skills_core.RESULT_MAX:
                    problems.append(f"check 7: {fn} answer is over 4 KB")
                for effect in out["effects"]:
                    if effect.get("kind") not in skills_core.CORE_EFFECT_KINDS and effect.get("skill") != name:
                        problems.append(f"check 8: {fn} sent an effect for someone else")
            if manifest.get("sees"):
                skill = host.skills[name]
                try:
                    seen = skill.module.view(skill.state)
                except Exception as err:  # noqa: BLE001
                    seen = err
                if not isinstance(seen, str) or len(seen) >= skills_core.VIEW_MAX:
                    problems.append(f"check 7: view() {label} must return text under 600 characters")
    finally:
        scratch.close()
    return sorted(set(problems))


def node_problems(node, folder, name):
    """Check 10: screen.js parses and calls MarySkills.register with its own name."""
    js = str(folder / "screen.js")
    if subprocess.run([node, "--check", js], capture_output=True, timeout=30).returncode:
        return ["check 10: screen.js doesn't parse"]
    run = subprocess.run([node, "-e", NODE_CHECK, js], capture_output=True, text=True, timeout=30)
    if run.returncode:
        return ["check 10: screen.js fails when it loads"]
    if name not in json.loads(run.stdout or "[]"):
        return ["check 10: screen.js doesn't call MarySkills.register with its own name"]
    return []


class ShippedSkillsTest(unittest.TestCase):
    """Every folder in skills/ (none yet, so these pass with zero)."""

    def test_each_skill_passes_the_contract(self):
        for folder in skill_folders(SHIPPED):
            with self.subTest(skill=folder.name):
                self.assertEqual(contract_problems(folder), [])

    def test_skills_fit_together(self):
        """Check 2 (unique function names), check 4 (total instruction budget), check 9 (no shared phrases)."""
        manifests = [skills_core.read_manifest(f) for f in skill_folders(SHIPPED)]
        names = [f"{m['name']}__{a['name']}" for m in manifests for a in m.get("actions", [])]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(len(n) <= 64 for n in names))
        total = sum(len(m.get("instructions", "")) for m in manifests)
        self.assertLessEqual(total, skills_core.TOTAL_INSTRUCTIONS_MAX)
        phrases = [skills_core._plain(p) for m in manifests for a in m.get("actions", [])
                   for p in a.get("offline_phrases", [])]
        self.assertEqual(len(phrases), len(set(phrases)))


class FixtureSkillsTest(unittest.TestCase):
    """The test fixtures: one good skill, and bad ones each refused for its own reason."""

    def test_good_fixture_passes(self):
        self.assertEqual(contract_problems(FIXTURES / "coin_flip"), [])

    def test_bad_fixtures_refused_for_their_reason(self):
        for name, reason in BAD.items():
            with self.subTest(fixture=name):
                problems = contract_problems(FIXTURES / name, fast=True)
                self.assertTrue(any(reason in p for p in problems), problems)

    def test_loader_refuses_what_it_can_see_at_start(self):
        scratch = Scratch(skill_folders(FIXTURES))
        self.addCleanup(scratch.close)
        host = scratch.host()
        self.assertEqual(sorted(host.skills), ["coin_flip", "raises", "sleeps"])
        self.assertIn("imports urllib", host.load_errors["bad_import"])
        self.assertIn("outside the Gemini subset", host.load_errors["bad_schema"])
        self.assertIn("no handler for spin", host.load_errors["no_handler"])

    def test_screen_js_with_node(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node not found: contract check 10 (screen.js parses and registers) was skipped")
        for folder in skill_folders(SHIPPED) + [FIXTURES / "coin_flip"]:
            manifest = skills_core.read_manifest(folder)
            if manifest.get("screen"):
                with self.subTest(skill=folder.name):
                    self.assertEqual(node_problems(node, folder, manifest["name"]), [])


if __name__ == "__main__":
    unittest.main()
