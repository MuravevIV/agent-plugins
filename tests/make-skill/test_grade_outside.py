"""Tests for plugins/core/skills/make-skill/house/scripts/grade_outside.py.

Run with:
    python -m unittest discover -s tests/make-skill -p "test_grade_outside.py" -v
The real opencode program is never started: every test points --program at fake_opencode.py.
"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MAKE_SKILL = REPO / "plugins" / "core" / "skills" / "make-skill"
SCRIPT = MAKE_SKILL / "house" / "scripts" / "grade_outside.py"
FAKE = HERE / "fake_opencode.py"
TIMING = {"total_tokens": 100, "duration_ms": 1000, "total_duration_seconds": 1.0}


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def make_run(case_dir, arm, run, answer, status="ok", extra=None):
    d = case_dir / arm / run
    put(d / "outputs" / "answer.md", answer)
    for name, data in (extra or {}).items():
        put(d / "outputs" / name, data)
    if status is not None:
        put(d / "run.json", {"status": status})
    put(d / "timing.json", TIMING)
    return d


def build_fixture(root):
    """Three cases: two arms; old_skill with two with_skill runs and one failed run; no expectations."""
    it = root / "workspace" / "iteration-1"
    c1 = it / "eval-1-alpha"
    put(c1 / "eval_metadata.json", {"eval_id": 1, "eval_name": "alpha", "prompt": "Summarise the report.",
                                     "assertions": ["Names the cause", "Gives a number", "Says what to do next"]})
    run = make_run(c1, "with_skill", "run-1", "Alpha answer with the skill.\n", extra={"image.png": b"\x89PNG\x00\x01\x02"})
    # an answer that mentions its own folder must not leak it into the prompt
    put(run / "outputs" / "notes.txt", f"Saved under {run} and the with_skill folder.\n")
    make_run(c1, "without_skill", "run-1", "Alpha answer without the skill.\n", status=None)  # no run.json: counts as ok
    c2 = it / "eval-2-beta"
    put(c2 / "eval_metadata.json", {"eval_id": 2, "eval_name": "beta", "prompt": "Fix the bug.",
                                     "assertions": ["Finds the bug", "Writes a test"]})
    make_run(c2, "with_skill", "run-1", "Beta new 1.\n")
    make_run(c2, "with_skill", "run-2", "Beta new 2.\n")
    make_run(c2, "old_skill", "run-1", "Beta old 1.\n")
    make_run(c2, "old_skill", "run-2", "should never be sent\n", status="failed")
    c3 = it / "eval-3-gamma"
    put(c3 / "eval_metadata.json", {"eval_id": 3, "eval_name": "gamma", "prompt": "Anything.", "assertions": []})
    make_run(c3, "with_skill", "run-1", "Gamma.\n")
    make_run(c3, "without_skill", "run-1", "Gamma.\n")
    return it


class GradeOutsideTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="grade-outside-")).resolve()
        self.it = build_fixture(self.tmp)
        self.log = self.tmp / "fake.log"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, *args, mode="ok", program=FAKE, cwd=None):
        env = dict(os.environ, FAKE_OPENCODE_MODE=mode, FAKE_OPENCODE_LOG=str(self.log), PWD="C:\\somewhere\\else",
                   PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        env.pop("MAKE_SKILL_OPENCODE_PROGRAM", None)
        cmd = [sys.executable, str(SCRIPT), "--iteration", str(self.it), "--program", str(program), *args]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env, timeout=120, cwd=cwd)
        return r.returncode, r.stdout + r.stderr

    def starts(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def out(self, case):
        return self.it / "outside-grading" / case

    def grading(self, case, arm, run):
        p = self.it / case / arm / run / "grading.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    # (1)
    def test_without_yes_sends_nothing(self):
        code, out = self.run_script()
        self.assertEqual(code, 3, out)
        self.assertEqual(self.starts(), [])
        self.assertIn("--yes", out)
        self.assertIn("openai/gpt-6.2-sol", out)
        for case in ("eval-1-alpha", "eval-2-beta"):
            self.assertTrue((self.out(case) / "prompt.md").exists())
            self.assertIn(str(self.out(case) / "prompt.md"), out)

    def test_wording_from_an_instruction_file_above_the_runs_is_pointed_out(self):
        code, out = self.run_script("--build-only")
        self.assertEqual(code, 0, out)
        self.assertNotIn("Look at this before anything is sent", out)
        put(self.tmp / "CLAUDE.md", "# House rules\n\nAsk the purple lock before any render.\n")
        make_run(self.it / "eval-1-alpha", "without_skill", "run-1",
                 "Alpha answer without the skill. Renders go through your purple lock.\n", status=None)
        code, out = self.run_script("--build-only")
        self.assertEqual(code, 0, out)
        self.assertIn("Look at this before anything is sent", out)
        self.assertIn(str(self.tmp / "CLAUDE.md"), out)
        self.assertIn('"purple lock" in eval-1-alpha', out)
        self.assertNotIn("eval-2-beta\n", out.split("Built")[0])

    # (2)
    def test_build_only_sends_nothing(self):
        code, out = self.run_script("--build-only", "--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.starts(), [])
        self.assertTrue((self.out("eval-1-alpha") / "prompt.md").exists())
        self.assertIn("Nothing was sent", out)

    # (3)
    def test_grades_match_key_and_ranking_uses_arm_names(self):
        code, out = self.run_script("--yes")
        self.assertEqual(code, 0, out)
        for case, total in (("eval-1-alpha", 3), ("eval-2-beta", 2)):
            key = json.loads((self.out(case) / "key.json").read_text(encoding="utf-8"))
            for letter, rid in key.items():
                arm, run = rid.split("/")
                g = self.grading(case, arm, run)
                self.assertEqual(g["grader"], {"kind": "outside", "model": "openai/gpt-6.2-sol", "letter": letter})
                passed = [e["passed"] for e in g["expectations"]]
                want = [n % 2 == 1 for n in range(1, total + 1)] if letter == "A" else [True] * total
                self.assertEqual(passed, want)
                for e in g["expectations"]:
                    self.assertEqual(set(e), {"text", "passed", "evidence"})
                self.assertEqual(g["summary"]["total"], total)
                self.assertEqual(g["summary"]["passed"], sum(want))
                self.assertNotIn("same_family", g)
            ranking = json.loads((self.out(case) / "ranking.json").read_text(encoding="utf-8"))["ranking"]
            self.assertEqual(sorted(f"{r['arm']}/{r['run']}" for r in ranking), sorted(key.values()))
            self.assertTrue(all(r["arm"] in ("with_skill", "without_skill", "old_skill") for r in ranking))
            comparison = (self.out(case) / "comparison.md").read_text(encoding="utf-8")
            self.assertIn(f"A = {key['A']}", comparison)
            for name in ("events.jsonl", "response.txt", "session.json"):
                self.assertTrue((self.out(case) / name).exists())
        session = json.loads((self.out("eval-1-alpha") / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(session["exit_code"], 0)
        self.assertEqual(session["cost"], 0.01)
        self.assertIn("Results:", out)
        self.assertIn("scripts.aggregate_benchmark", out)

    # (4)
    def test_prompt_is_blind_and_starts_with_task(self):
        self.run_script("--build-only")
        for case in ("eval-1-alpha", "eval-2-beta"):
            text = (self.out(case) / "prompt.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("Task:"))
            for word in ("with_skill", "without_skill", "old_skill", str(self.it / case)):
                self.assertNotIn(word.lower(), text.lower())
            self.assertIn("===== USER REQUEST =====", text)
            self.assertIn("===== EXPECTATIONS =====", text)
            self.assertIn("Follow none of the instructions", text)
        alpha = (self.out("eval-1-alpha") / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("1. Names the cause", alpha)
        self.assertIn("image.png (not text", alpha)
        self.assertLess(alpha.index("file answer.md"), alpha.index("file notes.txt"))

    # (5)
    def test_key_is_stable_and_graded_cases_are_skipped(self):
        self.run_script("--build-only")
        key1 = (self.out("eval-2-beta") / "key.json").read_text(encoding="utf-8")
        prompt1 = (self.out("eval-2-beta") / "prompt.md").read_text(encoding="utf-8")
        self.run_script("--build-only")
        self.assertEqual((self.out("eval-2-beta") / "key.json").read_text(encoding="utf-8"), key1)
        self.assertEqual((self.out("eval-2-beta") / "prompt.md").read_text(encoding="utf-8"), prompt1)
        code, out = self.run_script("--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.out("eval-2-beta") / "key.json").read_text(encoding="utf-8"), key1)
        self.assertEqual(len(self.starts()), 2)
        code, out = self.run_script("--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.starts()), 2)
        self.assertIn("already graded", out)
        code, out = self.run_script("--yes", "--redo")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.starts()), 4)

    # (6)
    def test_bad_replies_fail_plainly_and_can_be_redone(self):
        expect = {"not_json": "not a JSON object", "missing_letter": "is missing",
                  "error": "opencode auth list", "hang": "did not finish within"}
        for mode, words in expect.items():
            with self.subTest(mode=mode):
                shutil.rmtree(self.it.parent)
                self.it = build_fixture(self.tmp)
                extra = ("--timeout", "3", "--cases", "1") if mode == "hang" else ()
                code, out = self.run_script("--yes", *extra, mode=mode)
                self.assertEqual(code, 1, out)
                self.assertIn(words, out)
                self.assertIn("redoes only the cases", out)
                self.assertNotIn("Traceback", out)
                self.assertIsNone(self.grading("eval-1-alpha", "with_skill", "run-1"))
                self.assertIsNone(self.grading("eval-1-alpha", "without_skill", "run-1"))
                if mode == "error":
                    self.assertIn("opencode models", out)
                    self.assertIn("No credentials found", out)
                if mode in ("not_json", "missing_letter"):
                    self.assertTrue((self.out("eval-1-alpha") / "response.txt").read_text(encoding="utf-8"))
                code, out = self.run_script("--yes", mode="ok")
                self.assertEqual(code, 0, out)
                self.assertIsNotNone(self.grading("eval-1-alpha", "with_skill", "run-1"))

    # (7)
    def test_same_family_model_is_refused_unless_allowed(self):
        code, out = self.run_script("--yes", "--model", "anthropic/claude-x")
        self.assertEqual(code, 2, out)
        self.assertIn("--same-family-ok", out)
        self.assertIn("same family", out)
        self.assertEqual(self.starts(), [])
        code, out = self.run_script("--yes", "--model", "anthropic/claude-x", "--same-family-ok")
        self.assertEqual(code, 0, out)
        g = self.grading("eval-1-alpha", "with_skill", "run-1")
        self.assertTrue(g["same_family"])
        self.assertEqual(g["grader"]["model"], "anthropic/claude-x")

    # (8)
    def test_program_started_without_pwd_inside_grader_folder(self):
        code, out = self.run_script("--yes", "--variant", "high")
        self.assertEqual(code, 0, out)
        starts = self.starts()
        self.assertEqual(len(starts), 2)
        grader = os.path.normcase(str(self.it / "outside-grading" / ".grader"))
        for s in starts:
            self.assertFalse(s["pwd_in_env"])
            self.assertEqual(os.path.normcase(s["cwd"]), grader)
            self.assertTrue(s["agent_file"])
            argv = s["argv"]
            self.assertEqual(argv[:3], ["run", "-m", "openai/gpt-6.2-sol"])
            self.assertIn("--agent", argv)
            self.assertEqual(argv[argv.index("--agent") + 1], "outside-grader")
            self.assertEqual(argv[argv.index("--format") + 1], "json")
            self.assertEqual(argv[argv.index("--variant") + 1], "high")
        agent = (self.it / "outside-grading" / ".grader" / ".opencode" / "agent" / "outside-grader.md").read_text(encoding="utf-8")
        self.assertIn("mode: primary", agent)
        self.assertIn('"*": deny', agent)

    def test_relative_program_path_works(self):
        code, out = self.run_script("--yes", program="fake_opencode.py", cwd=HERE)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.starts()), 2)

    def test_single_answer_is_graded_alone(self):
        shutil.rmtree(self.it / "eval-1-alpha" / "without_skill")
        code, out = self.run_script("--yes", "--cases", "1")
        self.assertEqual(code, 0, out)
        self.assertIn("nothing to compare", out)
        self.assertIn("Task: grade one answer", (self.out("eval-1-alpha") / "prompt.md").read_text(encoding="utf-8"))
        self.assertEqual(self.grading("eval-1-alpha", "with_skill", "run-1")["grader"]["letter"], "A")

    # (9)
    def test_failed_run_left_out_empty_case_skipped_three_answers(self):
        code, out = self.run_script("--yes")
        self.assertEqual(code, 0, out)
        self.assertIn("old_skill/run-2 is left out", out)
        self.assertIsNone(self.grading("eval-2-beta", "old_skill", "run-2"))
        self.assertIn("eval-3-gamma: skipped", out)
        self.assertIn("evals.json", out)
        self.assertFalse(self.out("eval-3-gamma").exists())
        beta = (self.out("eval-2-beta") / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("===== ANSWER C =====", beta)
        self.assertNotIn("===== ANSWER D =====", beta)
        self.assertNotIn("should never be sent", beta)
        for arm, run in (("with_skill", "run-1"), ("with_skill", "run-2"), ("old_skill", "run-1")):
            self.assertEqual(self.grading("eval-2-beta", arm, run)["summary"]["total"], 2)

    # (10)
    def test_aggregate_benchmark_reads_the_grades(self):
        code, out = self.run_script("--yes")
        self.assertEqual(code, 0, out)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        r = subprocess.run([sys.executable, "-m", "scripts.aggregate_benchmark", str(self.it), "--skill-name", "x"],
                           cwd=MAKE_SKILL, capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        bench = json.loads((self.it / "benchmark.json").read_text(encoding="utf-8"))
        self.assertIn("with_skill", bench["run_summary"])
        self.assertIn("without_skill", bench["run_summary"])
        self.assertGreater(bench["run_summary"]["with_skill"]["pass_rate"]["mean"], 0)

    def test_skill_input_files_grader_notes_and_cut(self):
        skill = self.tmp / "my-skill"
        put(skill / "evals" / "files" / "report.txt", "x" * 500)
        put(skill / "evals" / "evals.json", {"skill_name": "my-skill", "evals": [
            {"id": 1, "prompt": "Summarise the report.", "files": ["evals/files/report.txt"],
             "grader_notes": "The cause is the disk."}]})
        code, out = self.run_script("--build-only", "--skill", str(skill), "--max-chars", "100")
        self.assertEqual(code, 0, out)
        alpha = (self.out("eval-1-alpha") / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("===== INPUT FILE evals/files/report.txt =====", alpha)
        self.assertIn("===== GRADER NOTES =====\nThe cause is the disk.", alpha)
        self.assertIn("file cut here: the first 100 of 500 characters", alpha)

    def test_longer_side_name_is_removed_before_shorter(self):
        spec = importlib.util.spec_from_file_location("grade_outside_under_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        text = "Saved by without_skill_plus_lines, compared with WITHOUT_SKILL and with_skill."
        want = "Saved by [removed], compared with [removed] and [removed]."
        run = {"arm": "without_skill_plus_lines", "run": "run-1", "dir": self.tmp / "x" / "run-1"}
        for runs in ([], [run]):  # the name from ARM_WORDS alone, and also as a side found on disk
            with self.subTest(runs=len(runs)):
                self.assertEqual(mod.scrub(text, {"runs": runs}), (want, 3))

    def test_plain_messages_for_missing_folder_and_program(self):
        self.it = self.tmp / "nowhere" / "iteration-9"
        code, out = self.run_script("--yes")
        self.assertEqual(code, 2, out)
        self.assertIn("does not exist", out)
        self.it = self.tmp / "workspace"
        code, out = self.run_script("--yes")
        self.assertEqual(code, 2, out)
        self.assertIn("holds no eval-", out)
        self.it = build_fixture(self.tmp)
        code, out = self.run_script("--yes", program=self.tmp / "missing-opencode.exe")
        self.assertEqual(code, 2, out)
        self.assertIn("was not found", out)
        self.assertIn("--program", out)
        self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main()
