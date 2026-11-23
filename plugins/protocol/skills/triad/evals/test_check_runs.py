"""Self-test for check_runs.py. Standard library only.

Builds small made-up iteration folders and a made-up evals.json in a temporary folder,
runs check_runs.py as a separate process and checks the files it writes.

    python -m unittest test_check_runs.py      or      python test_check_runs.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_runs.py"

PASSING_TEST = "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n"
FAILING_TEST = "import unittest\n\nclass T(unittest.TestCase):\n    def test_bad(self):\n        self.assertTrue(False)\n"


def init(model):
    return {"type": "system", "subtype": "init", "model": model}


def calls(*tool_uses, parent=None):
    """One assistant event holding tool calls given as (id, name, input)."""
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"content": [{"type": "tool_use", "id": i, "name": n, "input": inp} for i, n, inp in tool_uses]
                        + [{"type": "text", "text": "working"}]}}


def agent(tid, prompt, model=None, subagent_type=None, description=None, name="Agent", parent=None):
    given = {"prompt": prompt}
    for key, value in (("model", model), ("subagent_type", subagent_type), ("description", description)):
        if value is not None:
            given[key] = value
    return calls((tid, name, given), parent=parent)


def shell(tid, command, parent=None, name="Bash"):
    return calls((tid, name, {"command": command}), parent=parent)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="test_check_runs-"))
        self.skill = self.tmp / "skill"
        self.iteration = self.tmp / "workspace" / "iteration-1"
        self.iteration.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_evals(self, cases):
        path = self.skill / "evals" / "evals.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"skill_name": "triad", "evals": cases}), encoding="utf-8")

    def make_run(self, case_id, side, events=None, outputs=None, run_json=None, grading=None,
                 raw_lines=(), run="run-1"):
        case_dir = self.iteration / f"eval-{case_id}-case"
        case_dir.mkdir(exist_ok=True)
        (case_dir / "eval_metadata.json").write_text(
            json.dumps({"eval_id": case_id, "eval_name": "case", "prompt": "p", "assertions": []}), encoding="utf-8")
        run_dir = case_dir / side / run
        run_dir.mkdir(parents=True)
        if events is not None:
            lines = [json.dumps(e) for e in events] + list(raw_lines)
            (run_dir / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (run_dir / "run.json").write_text(json.dumps(run_json if run_json is not None else
                                                     {"status": "ok", "arm": side, "model": "claude-fable-5-2"}),
                                          encoding="utf-8")
        for rel, text in (outputs or {}).items():
            p = run_dir / "outputs" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        if grading is not None:
            (run_dir / "grading.json").write_text(json.dumps(grading, indent=2), encoding="utf-8")
        return run_dir

    def run_script(self, *args, iteration=None):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        return subprocess.run([sys.executable, str(SCRIPT), "--iteration", str(iteration or self.iteration),
                               "--skill", str(self.skill), *args],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=600)

    def rows(self, run_dir):
        data = json.loads((run_dir / "script_checks.json").read_text(encoding="utf-8"))
        self.assertEqual(data["made_by"], "check_runs.py")
        return {r["text"]: r for r in data["checks"]}

    def assertRan(self, done):
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("Traceback", done.stderr)


FILE_CHECKS = [
    {"check": "no_handoff", "text": "no handoff"},
    {"check": "file_exists", "file": "exists.md", "text": "exists"},
    {"check": "file_absent", "files": ["left.md", "other.md"], "text": "absent"},
    {"check": "file_contains", "file": "made.md", "value": "8091", "text": "contains"},
    {"check": "file_lacks", "file": "made.md", "value": "8080", "text": "lacks, file there"},
    {"check": "file_lacks", "file": "second.md", "value": "8080", "text": "lacks, second file"},
    {"check": "answer_contains", "value": "Backup", "text": "answer"},
    {"check": "no_brackets", "file": "list.md", "text": "brackets"},
    {"check": "nothing_sent", "text": "sent"},
    {"check": "read_under", "value": "src", "text": "read src"},
    {"check": "command_passes", "command": ["python", "-m", "unittest", "discover", "-s", "tests"],
     "text": "tests pass"},
    {"check": "made_up_check", "text": "unknown"},
]


class FileAndShellChecks(Base):
    def setUp(self):
        super().setUp()
        self.write_evals([{"id": 1, "prompt": "p", "script_checks": FILE_CHECKS}])
        self.good = self.make_run(1, "with_skill", events=[
            init("claude-fable-5-2"),
            shell("t1", "python -m pytest -q"),
            # A subagent's own Agent call is not a hand-off by the main session.
            agent("t2", "look around", model="opus", parent="toolu_outer"),
            calls(("t3", "Read", {"file_path": "C:\\work\\src\\app\\config.py"}), parent="toolu_outer"),
            shell("t4", "python outside_grader.py --dry-run"),
        ], raw_lines=["this line is not JSON {", "[1, 2]"], outputs={
            "exists.md": "here",
            "made.md": "The wiki is on port 8091.",
            "second.md": "no port here",
            "answer.md": "I changed the backup note too.\n",
            "list.md": "- [ ] first item\n- [x] second item\n1. [X] third item\nplain line\n",
            "tests/test_ok.py": PASSING_TEST,
        })
        self.bad = self.make_run(1, "without_skill", events=[
            init("claude-fable-5-2"),
            agent("t1", "do it", model="sonnet"),
            shell("t2", "opencode run -m openai/gpt-6.2-sol < brief.md", parent="t1"),
            calls(("t3", "Write", {"file_path": "src/new.py", "content": "x"}),
                  ("t4", "Edit", {"file_path": "src/app.py", "old_string": "a", "new_string": "b"})),
        ], outputs={
            "made.md": "The wiki is on port 8080.",
            "other.md": "changed",
            "answer.md": "Done.\n",
            "list.md": "- [ ] fine item\nSee (this) note\n",
            "tests/test_bad.py": FAILING_TEST,
        })
        self.done = self.run_script()

    def test_every_check_passes_on_the_good_run(self):
        self.assertRan(self.done)
        rows = self.rows(self.good)
        self.assertEqual(len(rows), len(FILE_CHECKS))
        for text, row in rows.items():
            self.assertIsInstance(row["evidence"], str)
            if text != "unknown":
                self.assertTrue(row["passed"], f"{text}: {row['evidence']}")
        self.assertIn("eval-1-case / with_skill / run-1: 11 of 12 passed", self.done.stdout)

    def test_every_check_fails_on_the_bad_run(self):
        self.assertRan(self.done)
        rows = self.rows(self.bad)
        for text, row in rows.items():
            self.assertFalse(row["passed"], f"{text} passed: {row['evidence']}")
        self.assertIn("1 time", rows["no handoff"]["evidence"])
        self.assertIn("sonnet", rows["no handoff"]["evidence"])
        self.assertIn("other.md", rows["absent"]["evidence"])
        self.assertIn("did not create or change", rows["lacks, second file"]["evidence"])
        self.assertIn("did not create or change", rows["exists"]["evidence"])
        self.assertIn("Line 2", rows["brackets"]["evidence"])
        self.assertIn("opencode run", rows["sent"]["evidence"])
        self.assertIn("exited with code 1", rows["tests pass"]["evidence"])
        self.assertIn("FAILED", rows["tests pass"]["evidence"])
        self.assertIn("eval-1-case / without_skill / run-1: 0 of 12 passed", self.done.stdout)
        self.assertIn("    failed: answer:", self.done.stdout)

    def test_unknown_check_name_is_a_failed_row(self):
        self.assertRan(self.done)
        row = self.rows(self.good)["unknown"]
        self.assertFalse(row["passed"])
        self.assertIn("made_up_check", row["evidence"])
        self.assertIn("not known to check_runs.py", row["evidence"])

    def test_without_merge_and_without_show_handoffs_nothing_else_is_written(self):
        self.assertRan(self.done)
        for run_dir in (self.good, self.bad):
            self.assertFalse((run_dir / "grading.json").exists())
            self.assertFalse((run_dir / "outputs" / "handoffs.md").exists())
        self.assertEqual([p.name for p in self.tmp.glob("**/__pycache__")], [])

    def test_running_again_gives_the_same_file(self):
        first = (self.good / "script_checks.json").read_bytes()
        self.assertRan(self.run_script())
        self.assertEqual((self.good / "script_checks.json").read_bytes(), first)


class NothingSentVariants(Base):
    def test_each_way_of_sending_fails_and_a_dry_run_passes(self):
        self.write_evals([{"id": 3, "prompt": "p", "script_checks": [{"check": "nothing_sent", "text": "sent"}]}])
        commands = {
            "run-1": ("curl https://api.openai.com/v1/responses", False),
            "run-2": ("python tools/outside_grader.py --yes brief.md", False),
            "run-3": ("python grade_outside.py --files a.md --yes", False),
            "run-4": ("python tools/outside_grader.py --dry-run brief.md", True),
            "run-5": ("which opencode; opencode --version; opencode auth list", True),
            "run-6": ('"C:/tools/opencode.exe" run -m openai/gpt-6.2-sol "Task: grade"', False),
        }
        for run, (command, _) in commands.items():
            self.make_run(3, "with_skill", run=run, events=[shell("t1", command, name="PowerShell")],
                          outputs={"answer.md": "x"})
        self.assertRan(self.run_script())
        for run, (command, expected) in commands.items():
            row = self.rows(self.iteration / "eval-3-case" / "with_skill" / run)["sent"]
            self.assertEqual(row["passed"], expected, f"{command}: {row['evidence']}")
            if not expected:
                self.assertIn(command[:20], row["evidence"])

    def test_a_refused_command_sent_nothing(self):
        self.write_evals([{"id": 3, "prompt": "p", "script_checks": [{"check": "nothing_sent", "text": "sent"}]}])
        result = {"type": "result", "subtype": "success",
                  "permission_denials": [{"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {}}]}
        run_dir = self.make_run(3, "with_skill", outputs={"answer.md": "x"},
                                events=[shell("t1", "opencode run -m openai/gpt-6.2-sol < brief.md"), result])
        self.assertRan(self.run_script())
        row = self.rows(run_dir)["sent"]
        self.assertTrue(row["passed"], row["evidence"])
        self.assertIn("refused", row["evidence"])


HANDOFF_CHECKS = [
    {"check": "handoffs_name_model", "text": "names model"},
    {"check": "ran_tests_after_handoff", "text": "tests after"},
]
BRIEF = "Summarize reports/a.md.\n\nKeep it under 80 words. Example:\n```\nshort paragraph\n```\nStop and report back if the task differs from this description."


class HandOffChecks(Base):
    def setUp(self):
        super().setUp()
        self.write_evals([{"id": 2, "prompt": "p", "show_handoffs": True, "script_checks": HANDOFF_CHECKS}])
        self.good = self.make_run(2, "with_skill", events=[
            init("claude-fable-5-2"),
            agent("t1", BRIEF, model="sonnet", subagent_type="general-purpose", description="Summarize a"),
            # Inside the subagent: neither a hand-off nor a test run of the main session.
            agent("t9", "inner brief", model="fable", parent="t1"),
            agent("t2", "Second brief", model="haiku", name="Task"),
            shell("t3", "python -m pytest", parent="t2"),
            shell("t4", "python -m unittest discover -s tests"),
        ], outputs={"answer.md": "x"})
        # Model of the main session from the init event, since run.json has none; one hand-off names no model.
        self.no_model = self.make_run(2, "without_skill", run_json={"status": "ok"}, events=[
            init("claude-sonnet-5-5"),
            shell("t1", "python -m pytest"),
            agent("t2", "Build it", model="opus"),
            agent("t3", "Check it", name="Task"),
            shell("t4", "python -m unittest", parent="t3"),
        ], outputs={"answer.md": "x"})
        self.own_model = self.make_run(2, "old_skill", events=[
            agent("t1", "Build it", model="claude-fable-5-2"),
        ], outputs={"answer.md": "x"})
        self.none = self.make_run(2, "without_skill_plus_lines", events=[
            init("claude-fable-5-2"),
            agent("t9", "inner only", model="haiku", parent="toolu_somewhere"),
            shell("t1", "python -m unittest"),
        ], outputs={"answer.md": "x"})
        self.done = self.run_script()

    def test_good_run_passes_and_inner_calls_are_not_hand_offs(self):
        self.assertRan(self.done)
        rows = self.rows(self.good)
        self.assertTrue(rows["names model"]["passed"], rows["names model"]["evidence"])
        self.assertIn("sonnet (general-purpose)", rows["names model"]["evidence"])
        self.assertNotIn("fable (", rows["names model"]["evidence"])
        self.assertTrue(rows["tests after"]["passed"], rows["tests after"]["evidence"])

    def test_unnamed_model_and_tests_only_inside_subagent_fail(self):
        self.assertRan(self.done)
        rows = self.rows(self.no_model)
        self.assertFalse(rows["names model"]["passed"])
        self.assertIn("name no model", rows["names model"]["evidence"])
        self.assertIn("none named", rows["names model"]["evidence"])
        self.assertFalse(rows["tests after"]["passed"])

    def test_own_model_fails_using_run_json_model(self):
        self.assertRan(self.done)
        row = self.rows(self.own_model)["names model"]
        self.assertFalse(row["passed"])
        self.assertIn("fable", row["evidence"])

    def test_no_hand_off_fails_both(self):
        self.assertRan(self.done)
        rows = self.rows(self.none)
        self.assertFalse(rows["names model"]["passed"])
        self.assertEqual(rows["names model"]["evidence"], "no subagent was used")
        self.assertFalse(rows["tests after"]["passed"])

    def test_handoffs_md_with_hand_offs(self):
        self.assertRan(self.done)
        text = (self.good / "outputs" / "handoffs.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("This file was made by a script from the record of the run. "
                                        "It lists each piece of work the main session handed to a subagent.\n"))
        self.assertIn("## Hand-off 1", text)
        self.assertIn("## Hand-off 2", text)
        self.assertNotIn("## Hand-off 3", text)
        self.assertNotIn("inner brief", text)
        self.assertIn("Model named: sonnet", text)
        self.assertIn("Subagent type: general-purpose", text)
        self.assertIn("Short description: Summarize a", text)
        self.assertIn("Model named: haiku", text)
        self.assertIn("Subagent type: not given", text)
        self.assertIn("Short description: not given", text)
        self.assertIn("Brief:\n\n````\n" + BRIEF + "\n````", text)
        self.assertIn("Brief:\n\n```\nSecond brief\n```\n", text)

    def test_handoffs_md_without_hand_offs(self):
        self.assertRan(self.done)
        text = (self.none / "outputs" / "handoffs.md").read_text(encoding="utf-8")
        self.assertEqual(text, "This file was made by a script from the record of the run. It lists each piece of "
                               "work the main session handed to a subagent.\n\n"
                               "No work was handed to a subagent in this run.\n")
        text = (self.no_model / "outputs" / "handoffs.md").read_text(encoding="utf-8")
        self.assertIn("Model named: none named", text)


class Merge(Base):
    def setUp(self):
        super().setUp()
        self.write_evals([
            {"id": 1, "prompt": "p", "script_checks": [
                {"check": "file_exists", "file": "a.md", "text": "a exists"},
                {"check": "file_contains", "file": "a.md", "value": "x", "text": "a has x"}]},
            {"id": 2, "prompt": "p", "expectations": ["something"]},
        ])
        self.grading = {
            "expectations": [
                {"text": "an old script row", "passed": True, "evidence": "old", "checked_by": "script"},
                {"text": "grader item", "passed": False, "evidence": "the grader said no"},
            ],
            "summary": {"passed": 1, "failed": 1, "total": 2, "pass_rate": 0.5},
            "grader": {"kind": "model", "model": "openai/gpt-6.2-sol"},
            "notes": "kept as is",
        }
        self.graded = self.make_run(1, "with_skill", events=[], outputs={"a.md": "x", "answer.md": "y"},
                                    grading=self.grading)
        self.ungraded = self.make_run(1, "without_skill", events=[], outputs={"a.md": "nothing", "answer.md": "y"})
        self.no_checks = self.make_run(2, "with_skill", events=[], outputs={"answer.md": "y"})

    def test_merge_into_existing_grading(self):
        self.assertRan(self.run_script("--merge"))
        data = json.loads((self.graded / "grading.json").read_text(encoding="utf-8"))
        self.assertEqual([r["text"] for r in data["expectations"]], ["a exists", "a has x", "grader item"])
        self.assertEqual([r.get("checked_by") for r in data["expectations"]], ["script", "script", None])
        self.assertEqual(data["expectations"][2], self.grading["expectations"][1])
        self.assertEqual(data["grader"], self.grading["grader"])
        self.assertEqual(data["notes"], "kept as is")
        self.assertEqual(data["summary"], {"passed": 2, "failed": 1, "total": 3, "pass_rate": 0.6667})
        self.assertEqual(list(data), list(self.grading))

    def test_merge_creates_grading_only_when_there_are_checks(self):
        self.assertRan(self.run_script("--merge"))
        data = json.loads((self.ungraded / "grading.json").read_text(encoding="utf-8"))
        self.assertEqual(data["grader"], {"kind": "script"})
        self.assertEqual([r["passed"] for r in data["expectations"]], [True, False])
        self.assertEqual(data["summary"], {"passed": 1, "failed": 1, "total": 2, "pass_rate": 0.5})
        self.assertFalse((self.no_checks / "grading.json").exists())
        self.assertTrue((self.no_checks / "script_checks.json").exists())

    def test_merge_twice_gives_the_same_files(self):
        self.assertRan(self.run_script("--merge"))
        first = {p: (p / "grading.json").read_bytes() for p in (self.graded, self.ungraded)}
        self.assertRan(self.run_script("--merge"))
        for p, data in first.items():
            self.assertEqual((p / "grading.json").read_bytes(), data)

    def test_cases_option_limits_the_runs(self):
        self.assertRan(self.run_script("--cases", "2"))
        self.assertTrue((self.no_checks / "script_checks.json").exists())
        self.assertFalse((self.graded / "script_checks.json").exists())


class Stops(Base):
    def assertStopped(self, done, words):
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertNotIn("Traceback", done.stdout + done.stderr)
        self.assertIn(words, done.stderr)

    def test_missing_iteration_folder(self):
        self.write_evals([{"id": 1, "prompt": "p"}])
        self.assertStopped(self.run_script(iteration=self.tmp / "no-such-folder"), "does not exist")

    def test_missing_evals_json(self):
        self.make_run(1, "with_skill", events=[])
        self.assertStopped(self.run_script(), "There is no test cases file")

    def test_broken_evals_json(self):
        self.make_run(1, "with_skill", events=[])
        path = self.skill / "evals" / "evals.json"
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertStopped(self.run_script(), "could not be read as JSON")

    def test_no_run_folders(self):
        self.write_evals([{"id": 1, "prompt": "p"}])
        self.assertStopped(self.run_script(), "No run folders were found")


if __name__ == "__main__":
    unittest.main()
