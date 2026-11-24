"""Tests for tools/pack_skill.py.

Run with:
  PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests/tools

Each test builds a tiny repository (two marketplace files, one plugin, one skill) in a temporary folder and
calls the script's main() with --repo pointing there. The real repository is never touched.
"""
import contextlib, importlib.util, io, json, sys, tempfile, unittest
from datetime import date
from pathlib import Path

try:
    import tomllib  # part of Python from 3.11 on
except ImportError:
    tomllib = None
NEEDS_TOMLLIB = unittest.skipIf(tomllib is None, "writing a Codex config file needs Python 3.11 or later")

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "pack_skill.py"
spec = importlib.util.spec_from_file_location("pack_skill_under_test", SCRIPT)
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)

CLAUDE_MARKET = """{
  "name": "agent-plugins",
  "owner": { "name": "Test Owner" },
  "metadata": { "description": "Test marketplace" },
  "plugins": [
    {
      "name": "core",
      "source": "./plugins/core",
      "description": "Core skills"
    }
  ]
}
"""
CODEX_MARKET = """{
  "name": "agent-plugins",
  "interface": { "displayName": "Agent Plugins" },
  "plugins": [
    {
      "name": "core",
      "source": { "source": "local", "path": "./plugins/core" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Productivity"
    }
  ]
}
"""
PLUGIN = """{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "core",
  "version": "0.1.0",
  "description": "Core skills",
  "author": { "name": "Test Owner" }
}
"""
CLAUDE_PLUGIN = """{
  "name": "core",
  "version": "0.1.0",
  "description": "Core skills",
  "author": { "name": "Test Owner" }
}
"""
PLACEHOLDER_BLOCK = "## <date>\n\n- **Decision:** <keep | shrink | drop | untested (the user chose to skip the test)>\n"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def result_file(name, decision):
    return f"# Test result: {name}\n\n## 2026-11-01\n\n- **Decision:** {decision}\n- **Not covered:** a lot\n"


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


class PackSkillTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        write(self.repo / ".claude-plugin" / "marketplace.json", CLAUDE_MARKET)
        write(self.repo / ".agents" / "plugins" / "marketplace.json", CODEX_MARKET)
        write(self.repo / "plugins" / "core" / "plugin.json", PLUGIN)
        write(self.repo / "plugins" / "core" / ".claude-plugin" / "plugin.json", CLAUDE_PLUGIN)
        skill = self.repo / "plugins" / "core" / "skills" / "first-skill"
        write(skill / "SKILL.md", "---\nname: first-skill\ndescription: The first skill.\n---\n\nBody\n")
        write(skill / "TEST-RESULT.md", result_file("first-skill", "keep"))

    def tearDown(self):
        self._tmp.cleanup()

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pack.main([*args, "--repo", str(self.repo)])
        return code, out.getvalue()

    def make_skill(self, name="new-skill", decision=None, result=None):
        src = self.root / "work" / name
        write(src / "SKILL.md", f"---\nname: {name}\ndescription: >\n  A skill made\n  for tests.\n---\n\nVersion one\n")
        write(src / "scripts" / "helper.py", "print('hi')\n")
        write(src / "evals" / "evals.json", '{"evals": []}\n')
        if result is not None:
            write(src / "TEST-RESULT.md", result)
        elif decision:
            write(src / "TEST-RESULT.md", result_file(name, decision))
        return src

    def target(self, name="new-skill", plugin="core"):
        return self.repo / "plugins" / plugin / "skills" / name

    def load(self, rel):
        return json.loads((self.repo / rel).read_text(encoding="utf-8"))

    # ---- new-plugin ----

    def test_new_plugin_writes_four_entries_that_check_accepts(self):
        code, out = self.run_main("new-plugin", "extra-tools", "--description", "Extra tools")
        self.assertEqual(code, 0, out)
        folder = self.repo / "plugins" / "extra-tools"
        meta = json.loads((folder / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(list(meta), ["$schema", "name", "version", "description", "author"])
        self.assertEqual((meta["version"], meta["author"]), ("0.1.0", {"name": "Test Owner"}))
        cmeta = json.loads((folder / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(cmeta, {k: meta[k] for k in ("name", "version", "description", "author")})
        self.assertTrue((folder / "skills" / ".gitkeep").is_file())
        claude = self.load(".claude-plugin/marketplace.json")["plugins"]
        self.assertIn({"name": "extra-tools", "source": "./plugins/extra-tools", "description": "Extra tools"}, claude)
        codex = {e["name"]: e for e in self.load(".agents/plugins/marketplace.json")["plugins"]}
        self.assertEqual(codex["extra-tools"]["source"], {"source": "local", "path": "./plugins/extra-tools"})
        self.assertEqual(codex["extra-tools"]["category"], "Productivity")
        self.assertEqual(codex["extra-tools"]["policy"], codex["core"]["policy"])
        code, out = self.run_main("check")
        self.assertEqual(code, 0, out)
        self.assertIn("everything is in step", out)

    def test_new_plugin_refuses_existing_folder_and_bad_name(self):
        before = snapshot(self.repo)
        self.assertEqual(self.run_main("new-plugin", "core", "--description", "x")[0], 2)
        self.assertEqual(self.run_main("new-plugin", "Bad_Name", "--description", "x")[0], 2)
        self.assertEqual(snapshot(self.repo), before)

    # ---- add ----

    def test_add_keep_files_it_and_keeps_the_original(self):
        src = self.make_skill(decision="keep")
        code, out = self.run_main("add", str(src), "--plugin", "core")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.target() / "SKILL.md").is_file())
        self.assertTrue((self.target() / "evals" / "evals.json").is_file())
        self.assertTrue((self.target() / "TEST-RESULT.md").is_file())
        self.assertTrue((src / "SKILL.md").is_file())
        self.assertIn("still there", out)
        self.assertIn("core / new-skill: keep", out)
        self.assertNotIn("Problem:", out)

    def test_check_accepts_an_entry_that_points_at_a_plugin_kept_elsewhere(self):
        market = self.load(".claude-plugin/marketplace.json")
        market["plugins"].append({"name": "outside", "description": "Somebody else's plugin",
                                  "source": {"source": "npm", "package": "outside-agents"}})
        write(self.repo / ".claude-plugin" / "marketplace.json", json.dumps(market, indent=2) + "\n")
        code, out = self.run_main("check")
        self.assertEqual(code, 0, out)
        self.assertIn("outside: kept elsewhere (npm outside-agents)", out)
        self.assertNotIn("Problem:", out)
        code, out = self.run_main("check", "--fix")
        self.assertEqual(code, 0, out)
        self.assertEqual([p["name"] for p in self.load(".agents/plugins/marketplace.json")["plugins"]], ["core"],
                         "a pointer is not copied into the other marketplace file")

        project = self.root / "some-project"
        project.mkdir()
        code, out = self.run_main("enable", "outside", "--project", str(project))
        self.assertEqual(code, 0, out)
        self.assertIn("switched on for Claude Code only", out)
        settings = json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertIs(settings["enabledPlugins"]["outside@agent-plugins"], True)
        self.assertFalse((project / ".codex").exists())
        self.assertFalse((project / ".github").exists())

        market["plugins"].append({"name": "ghost", "source": "./plugins/ghost", "description": "No folder"})
        write(self.repo / ".claude-plugin" / "marketplace.json", json.dumps(market, indent=2) + "\n")
        code, out = self.run_main("check")
        self.assertNotEqual(code, 0, out)
        self.assertIn('lists a plugin "ghost" that has no folder', out)

    def test_older_python_without_tomllib_still_files_and_says_so_for_codex(self):
        kept = pack.tomllib
        pack.tomllib = None  # as on Python 3.9 and 3.10
        try:
            src = self.make_skill(decision="keep")
            code, out = self.run_main("add", str(src), "--plugin", "core")
            self.assertEqual(code, 0, out)
            code, out = self.run_main("add", str(src), "--plugin", "core", "--replace")
            self.assertEqual(code, 0, out)
            project = self.root / "old-python-project"
            project.mkdir()
            code, out = self.run_main("enable", "core", "--project", str(project))
            self.assertIn("needs Python 3.11 or later", out)
            self.assertIn("switch the plugin on by hand", out)
            self.assertFalse((project / ".codex" / "config.toml").exists())
            self.assertTrue((project / ".claude" / "settings.json").is_file(), "the other apps are still done")
        finally:
            pack.tomllib = kept

    def test_add_points_out_paths_and_the_home_project_in_the_text(self):
        src = self.root / "home-proj" / ".claude" / "skills" / "new-skill"
        write(src / "SKILL.md", "---\nname: new-skill\ndescription: A skill made for tests.\n---\n\n"
              "The repository is at D:/SomeRepo. See http://localhost:8090/x and https://example.com/a.\n"
              "This is how home-proj does it.\n")
        write(src / "references" / "more.md", "Logs are under C:\\Users\\Someone\\logs.\n")
        write(src / "evals" / "notes.md", "Runs go to C:/make-skill-runs/x\n")
        write(src / "TEST-RESULT.md", result_file("new-skill", "keep") + "\nRecords in C:/somewhere/else\n")
        code, out = self.run_main("add", str(src), "--plugin", "core")
        self.assertEqual(code, 0, out)
        self.assertIn("thing(s) that belong to one machine or one project", out)
        self.assertIn("SKILL.md: the path D:/SomeRepo", out)
        self.assertIn("references/more.md: the path C:\\Users\\Someone\\logs", out)
        self.assertIn("SKILL.md: the name home-proj, the project folder this skill was taken from", out)
        for clean in ("localhost", "example.com", "make-skill-runs", "somewhere"):
            self.assertNotIn(clean, out.split("thing(s) that belong")[1].split("Nothing was stopped")[0])
        self.assertTrue((self.target() / "SKILL.md").is_file(), "the note stops nothing")

        plain = self.make_skill(name="plain-skill", decision="keep")
        code, out = self.run_main("add", str(plain), "--plugin", "core")
        self.assertEqual(code, 0, out)
        self.assertNotIn("belong to one machine", out)

    def test_add_without_result_stops_and_changes_nothing(self):
        for result in (None, f"# Test result: new-skill\n\n{PLACEHOLDER_BLOCK}"):
            with self.subTest(result=result):
                src = self.make_skill(result=result)
                before, before_src = snapshot(self.repo), snapshot(src)
                code, out = self.run_main("add", str(src), "--plugin", "core")
                self.assertEqual(code, 3, out)
                self.assertIn("never been tested", out)
                self.assertIn("run_tests.py --skill", out)
                self.assertIn("testing.md", out)
                self.assertIn("--untested", out)
                self.assertEqual(snapshot(self.repo), before)
                self.assertEqual(snapshot(src), before_src)

    def test_add_untested_writes_block_on_top_and_files(self):
        src = self.make_skill(result=f"# Test result: new-skill\n\n{PLACEHOLDER_BLOCK}")
        before_src = snapshot(src)
        code, out = self.run_main("add", str(src), "--plugin", "core", "--untested")
        self.assertEqual(code, 0, out)
        self.assertIn("marked as untested", out)
        self.assertIn("The folder you gave was not changed", out)
        self.assertEqual(snapshot(src), before_src)
        text = (self.target() / "TEST-RESULT.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(f"# Test result: new-skill\n\n## {date.today().isoformat()}\n\n"
                                        "- **Decision:** untested (the user chose to skip the test)\n"), text)
        self.assertIn("- **What was tested:** nothing\n", text)
        self.assertIn("- **Not covered:** everything; nobody knows yet whether this skill helps\n", text)
        self.assertEqual(text.count("# Test result:"), 1)
        self.assertGreater(text.index("<keep | shrink"), text.index("untested (the user"))
        self.assertIn("core / new-skill: untested", out)

    def test_add_untested_creates_the_file_in_the_copy_only(self):
        src = self.make_skill()
        self.assertEqual(self.run_main("add", str(src), "--plugin", "core", "--untested")[0], 0)
        self.assertTrue((self.target() / "TEST-RESULT.md").read_text(encoding="utf-8").startswith("# Test result: new-skill\n"))
        self.assertFalse((src / "TEST-RESULT.md").exists())

    def test_add_drop_needs_anyway(self):
        src = self.make_skill(decision="drop")
        before = snapshot(self.repo)
        code, out = self.run_main("add", str(src), "--plugin", "core")
        self.assertEqual(code, 3, out)
        self.assertIn('decided "drop"', out)
        self.assertIn("--anyway", out)
        self.assertEqual(snapshot(self.repo), before)
        code, out = self.run_main("add", str(src), "--plugin", "core", "--anyway")
        self.assertEqual(code, 0, out)
        self.assertIn('decided "drop"', out)
        self.assertTrue((self.target() / "SKILL.md").is_file())

    def test_add_existing_target_needs_replace(self):
        src = self.make_skill(decision="keep")
        self.assertEqual(self.run_main("add", str(src), "--plugin", "core")[0], 0)
        write(src / "SKILL.md", "---\nname: new-skill\ndescription: Second version.\n---\n\nVersion two\n")
        (src / "scripts" / "helper.py").unlink()
        before = snapshot(self.repo)
        code, out = self.run_main("add", str(src), "--plugin", "core")
        self.assertEqual(code, 3, out)
        self.assertIn("--replace", out)
        self.assertEqual(snapshot(self.repo), before)
        code, out = self.run_main("add", str(src), "--plugin", "core", "--replace")
        self.assertEqual(code, 0, out)
        self.assertIn("Version two", (self.target() / "SKILL.md").read_text(encoding="utf-8"))
        self.assertFalse((self.target() / "scripts" / "helper.py").exists())
        self.assertEqual([p.name for p in self.target().parent.iterdir()], ["first-skill", "new-skill"])

    def test_add_leaves_out_caches_and_workspaces(self):
        src = self.make_skill(decision="keep")
        write(src / "__pycache__" / "helper.cpython-312.pyc", "x")
        write(src / "scripts" / "__pycache__" / "x.pyc", "x")
        write(src / "stray.pyc", "x")
        write(src / "new-skill-workspace" / "iteration-1" / "a.txt", "x")
        write(src / ".git" / "HEAD", "x")
        self.assertEqual(self.run_main("add", str(src), "--plugin", "core")[0], 0)
        copied = set(snapshot(self.target()))
        self.assertEqual(copied, {"SKILL.md", "TEST-RESULT.md", "evals/evals.json", "scripts/helper.py"})

    def test_add_to_missing_plugin_names_new_plugin(self):
        src = self.make_skill(decision="keep")
        code, out = self.run_main("add", str(src), "--plugin", "nothing-here")
        self.assertEqual(code, 2, out)
        self.assertIn("new-plugin nothing-here", out)

    # ---- check ----

    def test_check_finds_and_fix_repairs_keeping_codex_policy(self):
        cj = self.repo / "plugins" / "core" / ".claude-plugin" / "plugin.json"
        write(cj, CLAUDE_PLUGIN.replace("0.1.0", "0.2.0"))
        write(self.repo / ".claude-plugin" / "marketplace.json", CLAUDE_MARKET.replace(
            '{\n      "name": "core",\n      "source": "./plugins/core",\n      "description": "Core skills"\n    }', ""))
        codex = CODEX_MARKET.replace('"AVAILABLE"', '"INSTALLED_BY_DEFAULT"').replace('"./plugins/core"', '"./plugins/old"')
        write(self.repo / ".agents" / "plugins" / "marketplace.json", codex)
        code, out = self.run_main("check")
        self.assertEqual(code, 1, out)
        self.assertIn('version "0.2.0"', out)
        self.assertIn(".claude-plugin/marketplace.json does not list the plugin core", out)
        self.assertIn("./plugins/old", out)
        self.assertIn("check --fix", out)
        code, out = self.run_main("check", "--fix")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(cj.read_text(encoding="utf-8"))["version"], "0.1.0")
        self.assertIn({"name": "core", "source": "./plugins/core", "description": "Core skills"},
                      self.load(".claude-plugin/marketplace.json")["plugins"])
        entry = self.load(".agents/plugins/marketplace.json")["plugins"][0]
        self.assertEqual(entry["policy"]["installation"], "INSTALLED_BY_DEFAULT")
        self.assertEqual(entry["source"]["path"], "./plugins/core")
        self.assertEqual(entry["category"], "Productivity")
        raw = (self.repo / ".agents" / "plugins" / "marketplace.json").read_bytes()
        self.assertTrue(raw.endswith(b"}\n") and b"\r" not in raw)
        self.assertEqual(self.run_main("check")[0], 0)

    def test_check_reports_entry_without_folder_and_fix_keeps_it(self):
        write(self.repo / ".agents" / "plugins" / "marketplace.json", CODEX_MARKET.replace(
            '"plugins": [', '"plugins": [\n    { "name": "gone", "source": { "source": "local", "path": "./plugins/gone" } },'))
        code, out = self.run_main("check", "--fix")
        self.assertEqual(code, 1, out)
        self.assertIn('lists a plugin "gone" that has no folder', out)
        self.assertIn('"gone"', (self.repo / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))

    def test_check_reports_skill_with_wrong_name(self):
        write(self.target("other-skill") / "SKILL.md", "---\nname: not-this\ndescription: x\n---\n")
        code, out = self.run_main("check")
        self.assertEqual(code, 1, out)
        self.assertIn("its folder is called other-skill", out)
        self.assertIn("core / other-skill: no test result", out)

    def test_check_fix_in_step_changes_no_bytes(self):
        before = snapshot(self.repo)
        code, out = self.run_main("check", "--fix")
        self.assertEqual(code, 0, out)
        self.assertIn("core / first-skill: keep", out)
        self.assertEqual(snapshot(self.repo), before)

    # ---- skills the user loads by name (the protocol plugin) ----

    def test_protocol_plugin_takes_only_skills_no_app_opens_on_its_own(self):
        self.assertEqual(self.run_main("new-plugin", "protocol", "--description", "Protocols")[0], 0)
        hidden = "description: By name.\ndisable-model-invocation: true\n---\n\nBody\n"
        wrong = self.make_skill(name="protocol-new", decision="keep")
        write(wrong / "SKILL.md", "---\nname: protocol-new\n" + hidden)
        write(wrong / "agents" / "openai.yaml", "policy:\n  allow_implicit_invocation: false\n")
        before = snapshot(self.repo)
        code, out = self.run_main("add", str(wrong), "--plugin", "protocol")
        self.assertEqual(code, 2, out)
        self.assertIn("the skill is named protocol-new", out)
        self.assertIn("protocol:protocol-new with the word twice", out)
        self.assertIn("for example new:", out)
        self.assertNotIn("disable-model-invocation", out)
        self.assertEqual(snapshot(self.repo), before)
        src = self.make_skill(decision="keep")
        code, out = self.run_main("add", str(src), "--plugin", "protocol")
        self.assertEqual(code, 2, out)
        self.assertIn("disable-model-invocation: true", out)
        self.assertIn("openai.yaml is missing", out)
        self.assertNotIn("the skill is named", out)
        self.assertIn("Then run the same command again", out)
        self.assertEqual(snapshot(self.repo), before)
        write(src / "SKILL.md", "---\nname: new-skill\n" + hidden)
        write(src / "agents" / "openai.yaml", "# note\npolicy:\n  allow_implicit_invocation: false\n")
        code, out = self.run_main("add", str(src), "--plugin", "protocol")
        self.assertEqual(code, 0, out)
        self.assertIn("protocol / new-skill: keep", out)
        write(self.target(plugin="protocol") / "agents" / "openai.yaml", "policy:\n  allow_implicit_invocation: true\n")
        code, out = self.run_main("check")
        self.assertEqual(code, 1, out)
        self.assertIn("openai.yaml does not switch it off", out)
        self.assertNotIn("disable-model-invocation", out)

    # ---- enable ----

    def project_files(self, project):
        return (project / ".claude" / "settings.json", project / ".github" / "copilot" / "settings.json",
                project / ".codex" / "config.toml")

    @NEEDS_TOMLLIB
    def test_enable_writes_three_files_keeps_keys_and_repeats_cleanly(self):
        project = self.root / "project"
        claude, copilot, codex = self.project_files(project)
        write(claude, '{"permissions": {"allow": ["Bash(ls)"]}, "enabledPlugins": {"other@else": true}}\n')
        write(codex, 'model = "o3"\n')
        code, out = self.run_main("enable", "core", "--project", str(project))
        self.assertEqual(code, 0, out)
        data = json.loads(claude.read_text(encoding="utf-8"))
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        self.assertEqual(data["enabledPlugins"], {"other@else": True, "core@agent-plugins": True})
        self.assertEqual(data["extraKnownMarketplaces"]["agent-plugins"],
                         {"source": {"source": "directory", "path": self.repo.resolve().as_posix()}})
        self.assertEqual(json.loads(copilot.read_text(encoding="utf-8")), {"enabledPlugins": {"core@agent-plugins": True}})
        text = codex.read_text(encoding="utf-8")
        self.assertEqual(text, 'model = "o3"\n\n[plugins."core@agent-plugins"]\nenabled = true\n')
        self.assertEqual(tomllib.loads(text)["plugins"]["core@agent-plugins"], {"enabled": True})
        self.assertIn("copilot plugin marketplace add", out)
        self.assertIn("codex plugin marketplace add", out)
        self.assertIn("have not been tried on this PC yet", out)
        before = snapshot(project)
        code, out = self.run_main("enable", "core", "--project", str(project))
        self.assertEqual(code, 0, out)
        self.assertEqual(snapshot(project), before)

    @NEEDS_TOMLLIB
    def test_enable_leaves_broken_json_alone(self):
        project = self.root / "project"
        claude, copilot, codex = self.project_files(project)
        write(copilot, '{"enabledPlugins": {')
        code, out = self.run_main("enable", "core", "--project", str(project))
        self.assertEqual(code, 1, out)
        self.assertEqual(copilot.read_text(encoding="utf-8"), '{"enabledPlugins": {')
        self.assertIn("left unchanged", out)
        self.assertTrue(claude.is_file() and codex.is_file())

    @NEEDS_TOMLLIB
    def test_enable_leaves_codex_switched_off_alone(self):
        project = self.root / "project"
        codex = self.project_files(project)[2]
        original = '[plugins."core@agent-plugins"]\nenabled = false\n'
        write(codex, original)
        code, out = self.run_main("enable", "core", "--project", str(project), "--apps", "codex")
        self.assertEqual(code, 1, out)
        self.assertEqual(codex.read_text(encoding="utf-8"), original)
        self.assertIn("change line 2 (enabled = false) to enabled = true", out)
        self.assertFalse((project / ".claude").exists())

    def test_enable_needs_plugin_and_project(self):
        self.assertEqual(self.run_main("enable", "nothing-here", "--project", str(self.root))[0], 2)
        self.assertEqual(self.run_main("enable", "core", "--project", str(self.root / "missing"))[0], 2)


if __name__ == "__main__":
    unittest.main()
