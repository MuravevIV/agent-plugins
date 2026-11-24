"""Tests for plugins/core/skills/make-skill/house/scripts/run_tests.py.

Run with:
  set PYTHONDONTWRITEBYTECODE=1 & set PYTHONUTF8=1
  python -m unittest discover -s C:\\projects\\agent-plugins\\tests\\make-skill -v

The real claude program is never started; fake_claude.py stands in for it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MAKE_SKILL = REPO / "plugins" / "core" / "skills" / "make-skill"
RUNNER = MAKE_SKILL / "house" / "scripts" / "run_tests.py"
FAKE = HERE / "fake_claude.py"
NAME = "tiny-skill"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_skill(folder, marker="CURRENT COPY"):
    write(folder / "SKILL.md", f"---\nname: {NAME}\ndescription: A tiny skill for tests.\n---\n\n{marker}\n")
    write(folder / "scripts" / "helper.py", "print('hi')\n")
    write(folder / "__pycache__" / "junk.pyc", "x")
    write(folder / "notes-workspace" / "old.txt", "x")
    write(folder / "evals" / "files" / "a.md", "input file\n")
    write(folder / "evals" / "evals.json", json.dumps({"skill_name": NAME, "evals": [
        {"id": 1, "name": "First case", "prompt": "Summarise evals/files/a.md",
         "expected_output": "a summary", "files": ["evals/files/a.md"], "expectations": ["mentions the input"]},
        {"id": 2, "prompt": "Write a short poem about rivers and lakes please",
         "expected_output": "a poem", "expectations": ["is a poem"]},
    ]}))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class RunTestsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="make-skill-test-"))
        self.skill = self.tmp / "skills" / NAME
        make_skill(self.skill)
        self.ws = self.tmp / "ws"
        self.log = self.tmp / "starts.log"
        self.it = self.ws / "iteration-1"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items()
               if not k.upper().startswith("FAKE_CLAUDE_") and k.upper() != "MAKE_SKILL_CLAUDE_PROGRAM"}
        # a made-up home folder next to the workspace, so the real user's own instruction file plays no part
        home = str(self.tmp / "home")
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", FAKE_CLAUDE_LOG=str(self.log),
                   USERPROFILE=home, HOME=home)
        env.update(extra)
        return env

    def run_runner(self, *args, **env):
        proc = subprocess.run([sys.executable, str(RUNNER), "--skill", str(self.skill), "--program", str(FAKE),
                               "--workspace", str(self.ws), *args], env=self.env(**env),
                              capture_output=True, text=True, encoding="utf-8", timeout=180)
        proc.all = proc.stdout + proc.stderr
        return proc

    def starts(self):
        return len(self.log.read_text(encoding="utf-8").splitlines()) if self.log.exists() else 0

    def case_dir(self, case_id):
        found = sorted(self.it.glob(f"eval-{case_id}-*"))
        self.assertEqual(len(found), 1, f"one folder for case {case_id} expected, found {found}")
        return found[0]

    def test_normal_run(self):
        p = self.run_runner()
        self.assertEqual(p.returncode, 0, p.all)
        self.assertEqual(self.starts(), 4)
        self.assertEqual(self.case_dir(1).name, "eval-1-first-case")
        self.assertEqual(self.case_dir(2).name, "eval-2-write-a-short-poem-about-rivers-and")
        for case_id in (1, 2):
            meta = read_json(self.case_dir(case_id) / "eval_metadata.json")
            self.assertEqual(meta["eval_id"], case_id)
            self.assertEqual(len(meta["assertions"]), 1)
            for arm in ("with_skill", "without_skill"):
                run = self.case_dir(case_id) / arm / "run-1"
                rec = read_json(run / "run.json")
                self.assertEqual(rec["status"], "ok", rec)
                self.assertEqual(rec["arm"], arm)
                self.assertEqual(rec["model"], "claude-fake-1")
                self.assertIn("--setting-sources", rec["command"])
                self.assertEqual(rec["skill_listed"], arm == "with_skill")
                self.assertEqual(rec["skill_used"], arm == "with_skill")
                timing = read_json(run / "timing.json")
                self.assertEqual(timing["total_tokens"], 100)
                self.assertEqual(timing["duration_ms"], 1234)
                self.assertEqual(read_json(run / "eval_metadata.json"), meta)
                self.assertTrue((run / "events.jsonl").is_file())
                self.assertTrue((run / "transcript.md").is_file())
                self.assertIn("The answer to:", (run / "outputs" / "answer.md").read_text(encoding="utf-8"))
                made = (run / "outputs" / "made-by-run.txt").read_text(encoding="utf-8")
                self.assertIn("prompt: " + meta["prompt"], made)
                self.assertFalse((run / "outputs" / ".claude").exists())
                self.assertFalse((run / "outputs" / "evals").exists(), "unchanged input files are not outputs")
                self.assertFalse((run / "work").exists(), "work folder is removed after a good run")
                self.assertEqual(list(run.glob("**/*.tmp")), [])
                if arm == "with_skill":
                    self.assertIn(f"{NAME}/SKILL.md", made)
                    self.assertIn(f"{NAME}/scripts/helper.py", made)
                    for leaked in ("evals", "__pycache__", "workspace"):
                        self.assertNotIn(leaked, made.split("installed:")[1])
                else:
                    self.assertTrue(rec["clean_comparison"])
                    self.assertNotIn("SKILL.md", made)
        self.assertIn("aggregate_benchmark", p.stdout)
        self.assertNotIn("never opened it", p.stdout)

    def test_load_by_name_puts_the_skill_name_in_front_of_the_prompt(self):
        p = self.run_runner("--cases", "1", "--load-by-name", FAKE_CLAUDE_NO_SKILL_CALL="1")
        self.assertEqual(p.returncode, 0, p.all)
        prompt = read_json(self.case_dir(1) / "eval_metadata.json")["prompt"]
        with_run, without_run = (self.case_dir(1) / arm / "run-1" for arm in ("with_skill", "without_skill"))
        self.assertIn(f"prompt: /{NAME} {prompt}", (with_run / "outputs" / "made-by-run.txt").read_text(encoding="utf-8"))
        self.assertIn("prompt: " + prompt, (without_run / "outputs" / "made-by-run.txt").read_text(encoding="utf-8"))
        self.assertTrue(read_json(with_run / "run.json")["loaded_by_name"])
        self.assertNotIn("loaded_by_name", read_json(without_run / "run.json"))
        self.assertNotIn("never opened it", p.stdout, "a skill loaded by name is not reported as never opened")

    def test_only_with_skill_leaves_out_the_other_side(self):
        p = self.run_runner("--cases", "1", "--only-with-skill")
        self.assertEqual(p.returncode, 0, p.all)
        self.assertEqual(self.starts(), 1)
        self.assertTrue((self.case_dir(1) / "with_skill" / "run-1" / "run.json").is_file())
        self.assertFalse((self.case_dir(1) / "without_skill").exists())

    def test_start_again_skips_finished_and_redo_reruns(self):
        self.assertEqual(self.run_runner().returncode, 0)
        self.assertEqual(self.starts(), 4)
        p = self.run_runner()
        self.assertEqual(p.returncode, 0, p.all)
        self.assertEqual(self.starts(), 4, "finished runs must not start the program again")
        self.assertIn("ok (earlier)", p.stdout)
        p = self.run_runner("--redo", "--cases", "1")
        self.assertEqual(p.returncode, 0, p.all)
        self.assertEqual(self.starts(), 6)

    def test_not_signed_in_stops_everything(self):
        p = self.run_runner("--parallel", "1", FAKE_CLAUDE_MODE="not_signed_in")
        self.assertEqual(p.returncode, 2, p.all)
        self.assertIn("auth login", p.all)
        self.assertIn("not signed in", p.all)
        self.assertEqual(self.starts(), 1, "no run may start after the first one found the program signed out")
        self.assertIn("not started", p.stdout)

    def test_dry_run_creates_nothing(self):
        p = self.run_runner("--dry-run")
        self.assertEqual(p.returncode, 0, p.all)
        self.assertFalse(self.ws.exists())
        self.assertEqual(self.starts(), 0)
        self.assertIn("--setting-sources project", p.stdout)
        self.assertIn("with_skill", p.stdout)
        self.assertIn("without_skill", p.stdout)

    def test_workspace_under_the_users_own_instruction_file_is_not_started(self):
        # the made-up home folder is the one that holds the workspace, and it has the user's own instruction file
        (self.tmp / ".claude").mkdir()
        (self.tmp / ".claude" / "CLAUDE.md").write_text("Always answer in French.\n", encoding="utf-8")
        home = dict(USERPROFILE=str(self.tmp), HOME=str(self.tmp))
        p = self.run_runner("--cases", "1", **home)
        self.assertEqual(p.returncode, 2, p.all)
        self.assertIn("inside your home folder", p.all)
        self.assertIn("Nothing was started", p.all)
        self.assertIn("--keep-user-setup", p.all)
        self.assertFalse(self.ws.exists())
        self.assertEqual(self.starts(), 0)
        p = self.run_runner("--cases", "1", "--keep-user-setup", **home)
        self.assertEqual(p.returncode, 0, p.all)
        self.assertIn("sits under a folder with its own instruction file", p.all)

    def test_home_folder_reached_through_a_link_is_still_recognised(self):
        # the home folder is given as a link; the workspace lies in it and resolves to the real folder
        real = self.tmp / "real-home"
        (real / ".claude").mkdir(parents=True)
        (real / ".claude" / "CLAUDE.md").write_text("Always answer in French.\n", encoding="utf-8")
        link = self.tmp / "home-link"
        try:
            os.symlink(real, link, target_is_directory=True)
        except (OSError, NotImplementedError) as e:
            # Windows asks for a special right to make a symbolic link; a junction needs none.
            made = os.name == "nt" and subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(real)],
                                                      capture_output=True).returncode == 0
            if not made:
                self.skipTest(f"this system does not let the test make a link to a folder: {e}")
        self.assertNotEqual(str(link.resolve()), str(link), "the link has to lead somewhere else")
        proc = subprocess.run([sys.executable, str(RUNNER), "--skill", str(self.skill), "--program", str(FAKE),
                               "--workspace", str(link / "ws"), "--cases", "1"],
                              env=self.env(USERPROFILE=str(link), HOME=str(link)),
                              capture_output=True, text=True, encoding="utf-8", timeout=180)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("inside your home folder", proc.stdout + proc.stderr)
        self.assertEqual(self.starts(), 0)

    def test_timeout_fails_plainly_and_is_done_again(self):
        p = self.run_runner("--cases", "1", "--timeout", "2", FAKE_CLAUDE_MODE="hang")
        self.assertEqual(p.returncode, 1, p.all)
        for arm in ("with_skill", "without_skill"):
            run = self.case_dir(1) / arm / "run-1"
            rec = read_json(run / "run.json")
            self.assertEqual(rec["status"], "failed")
            self.assertIn("longer than the limit of 2", rec["reason"])
            self.assertTrue((run / "work").exists(), "work folder is kept after a failed run")
        self.assertNotIn("Traceback", p.all)
        self.assertEqual(self.starts(), 2)
        self.assertEqual(self.run_runner("--cases", "1", "--timeout", "2", FAKE_CLAUDE_MODE="hang").returncode, 1)
        self.assertEqual(self.starts(), 4, "failed runs are done again")

    def test_error_fails_plainly_and_is_done_again(self):
        p = self.run_runner("--cases", "2", FAKE_CLAUDE_MODE="error")
        self.assertEqual(p.returncode, 1, p.all)
        rec = read_json(self.case_dir(2) / "with_skill" / "run-1" / "run.json")
        self.assertEqual(rec["status"], "failed")
        self.assertIn("Something broke inside the fake app", rec["reason"])
        self.assertIn("will be done again", p.stdout)
        self.assertNotIn("Traceback", p.all)
        self.assertEqual(self.run_runner("--cases", "2").returncode, 0)
        self.assertEqual(self.starts(), 4)

    def test_anthropic_tools_read_the_layout(self):
        self.assertEqual(self.run_runner().returncode, 0)
        grading = {"expectations": [{"text": "x", "passed": True, "evidence": "y"}],
                   "summary": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0}}
        for run in self.it.glob("eval-*/*/run-*"):
            write(run / "grading.json", json.dumps(grading))
        agg = subprocess.run([sys.executable, "-m", "scripts.aggregate_benchmark", str(self.it),
                              "--skill-name", NAME], cwd=MAKE_SKILL, env=self.env(),
                             capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(agg.returncode, 0, agg.stdout + agg.stderr)
        self.assertNotIn("Warning", agg.stdout)
        bench = read_json(self.it / "benchmark.json")
        self.assertEqual({r["configuration"] for r in bench["runs"]}, {"with_skill", "without_skill"})
        self.assertEqual(len(bench["runs"]), 4)
        self.assertEqual(sorted(bench["metadata"]["evals_run"]), [1, 2])
        self.assertTrue(all(r["result"]["tokens"] == 100 for r in bench["runs"]))
        html = self.tmp / "review.html"
        rev = subprocess.run([sys.executable, str(MAKE_SKILL / "eval-viewer" / "generate_review.py"), str(self.it),
                              "--skill-name", NAME, "--static", str(html)], env=self.env(),
                             capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(rev.returncode, 0, rev.stdout + rev.stderr)
        page = html.read_text(encoding="utf-8")
        for case in ("eval-1-first-case", "eval-2-write-a-short-poem-about-rivers-and"):
            for arm in ("with_skill", "without_skill"):
                self.assertIn(f"{case}-{arm}-run-1", page)
        self.assertIn("made-by-run.txt", page)

    def test_compare_with_installs_the_older_copy(self):
        old = self.tmp / "old" / NAME
        make_skill(old, marker="OLD COPY")
        p = self.run_runner("--compare-with", str(old), "--cases", "1", "--keep-work")
        self.assertEqual(p.returncode, 0, p.all)
        case = self.case_dir(1)
        self.assertFalse((case / "without_skill").exists())
        old_md = case / "old_skill" / "run-1" / "work" / ".claude" / "skills" / NAME / "SKILL.md"
        new_md = case / "with_skill" / "run-1" / "work" / ".claude" / "skills" / NAME / "SKILL.md"
        self.assertIn("OLD COPY", old_md.read_text(encoding="utf-8"))
        self.assertIn("CURRENT COPY", new_md.read_text(encoding="utf-8"))
        self.assertFalse((old_md.parent / "evals").exists())
        rec = read_json(case / "old_skill" / "run-1" / "run.json")
        self.assertEqual((rec["status"], rec["arm"], rec["skill_listed"]), ("ok", "old_skill", True))

    def test_unclean_comparison_and_denied_tools_are_reported(self):
        p = self.run_runner("--cases", "1", FAKE_CLAUDE_EXTRA_SKILLS=NAME, FAKE_CLAUDE_DENY="Bash")
        self.assertEqual(p.returncode, 0, p.all)
        rec = read_json(self.case_dir(1) / "without_skill" / "run-1" / "run.json")
        self.assertEqual(rec["status"], "ok")
        self.assertFalse(rec["clean_comparison"])
        self.assertEqual(rec["permission_denials"], ["Bash"])
        self.assertIn("comparison is not clean", p.stdout)
        self.assertIn('--allow-tools "Bash"', p.stdout)

    def test_skill_not_seen_fails_the_run(self):
        p = self.run_runner("--cases", "1", FAKE_CLAUDE_HIDE_SKILLS="1")
        self.assertEqual(p.returncode, 1, p.all)
        rec = read_json(self.case_dir(1) / "with_skill" / "run-1" / "run.json")
        self.assertEqual(rec["status"], "failed")
        self.assertIn("did not see the skill", rec["reason"])
        self.assertEqual(read_json(self.case_dir(1) / "without_skill" / "run-1" / "run.json")["status"], "ok")

    def test_skill_listed_but_not_opened_is_counted(self):
        p = self.run_runner("--cases", "1", FAKE_CLAUDE_NO_SKILL_CALL="1")
        self.assertEqual(p.returncode, 0, p.all)
        rec = read_json(self.case_dir(1) / "with_skill" / "run-1" / "run.json")
        self.assertEqual((rec["status"], rec["skill_listed"], rec["skill_used"]), ("ok", True, False))
        self.assertIn("In 1 of 1 finished run(s) with the skill installed", p.stdout)
        self.assertIn("never opened it", p.stdout)

    def lines_file(self, text="Always answer in one sentence.\n"):
        path = self.tmp / "lines.md"
        write(path, text)
        return path

    def test_instruction_lines_add_a_third_side(self):
        lines = self.lines_file()
        p = self.run_runner("--cases", "1", "--instruction-lines", str(lines), "--keep-work")
        self.assertEqual(p.returncode, 0, p.all)
        self.assertEqual(self.starts(), 3)
        case = self.case_dir(1)
        self.assertEqual(sorted(d.name for d in case.iterdir() if d.is_dir()),
                         ["with_skill", "without_skill", "without_skill_plus_lines"])
        run = case / "without_skill_plus_lines" / "run-1"
        rec = read_json(run / "run.json")
        self.assertEqual((rec["status"], rec["arm"], rec["skill_listed"]), ("ok", "without_skill_plus_lines", False))
        self.assertEqual(rec["instruction_lines_file"], str(lines.resolve()))
        self.assertTrue(rec["clean_comparison"])
        self.assertEqual((run / "work" / "CLAUDE.md").read_text(encoding="utf-8"), "Always answer in one sentence.\n")
        self.assertFalse((run / "work" / ".claude").exists(), "no skill on this side")
        made = (run / "outputs" / "made-by-run.txt").read_text(encoding="utf-8")
        self.assertIn("claude_md: Always answer in one sentence.", made, "the app found CLAUDE.md when it started")
        self.assertFalse((run / "outputs" / "CLAUDE.md").exists(), "an unchanged CLAUDE.md is not an output")
        self.assertFalse((run / "outputs" / "evals").exists())
        for arm in ("with_skill", "without_skill"):
            self.assertFalse((case / arm / "run-1" / "work" / "CLAUDE.md").exists(), f"{arm} gets no CLAUDE.md")
            self.assertNotIn("instruction_lines_file", read_json(case / arm / "run-1" / "run.json"))
        row = next(l for l in p.stdout.splitlines() if l.split()[1:2] == ["without_skill_plus_lines"])
        self.assertEqual(row.split()[-2:], ["no", "-"], "skill used shows - for a side without the skill")

    def test_instruction_lines_with_compare_with(self):
        old = self.tmp / "old" / NAME
        make_skill(old, marker="OLD COPY")
        p = self.run_runner("--compare-with", str(old), "--cases", "2", "--instruction-lines", str(self.lines_file()))
        self.assertEqual(p.returncode, 0, p.all)
        self.assertEqual(sorted(d.name for d in self.case_dir(2).iterdir() if d.is_dir()),
                         ["old_skill", "with_skill", "without_skill_plus_lines"])

    def test_skill_listed_in_both_sides_without_it_is_counted(self):
        p = self.run_runner("--cases", "1", "--instruction-lines", str(self.lines_file()),
                            FAKE_CLAUDE_EXTRA_SKILLS=NAME)
        self.assertEqual(p.returncode, 0, p.all)
        rec = read_json(self.case_dir(1) / "without_skill_plus_lines" / "run-1" / "run.json")
        self.assertFalse(rec["clean_comparison"])
        self.assertIn("In 2 run(s) without the skill", p.stdout)

    def test_instruction_lines_file_missing_empty_or_not_text_stops(self):
        bad = self.tmp / "latin1.md"
        bad.write_bytes(b"caf\xe9\n")
        for path, words in ((self.tmp / "nope.md", "There is no file at"),
                            (self.lines_file(" \n\n\t\n"), "empty or holds only blank lines"),
                            (bad, "could not be read as UTF-8 text")):
            with self.subTest(path=path.name):
                p = self.run_runner("--instruction-lines", str(path))
                self.assertEqual(p.returncode, 2, p.all)
                self.assertIn(words, p.stderr)
                self.assertIn("--instruction-lines", p.stderr)
                self.assertNotIn("Traceback", p.all)
                self.assertFalse(self.ws.exists())
                self.assertEqual(self.starts(), 0)

    def test_case_file_named_claude_md_clashes_with_instruction_lines(self):
        write(self.skill / "Claude.md", "the case's own file\n")
        cases = read_json(self.skill / "evals" / "evals.json")
        cases["evals"][1]["files"] = ["Claude.md"]
        write(self.skill / "evals" / "evals.json", json.dumps(cases))
        p = self.run_runner("--instruction-lines", str(self.lines_file()))
        self.assertEqual(p.returncode, 2, p.all)
        self.assertIn('Case 2 lists the file "Claude.md"', p.stderr)
        self.assertIn("overwrite", p.stderr)
        self.assertIn("Rename that file", p.stderr)
        self.assertNotIn("Traceback", p.all)
        self.assertEqual(self.starts(), 0)
        self.assertFalse(self.ws.exists())
        self.assertEqual(self.run_runner("--instruction-lines", str(self.lines_file()), "--cases", "1").returncode, 0,
                         "a case that is not selected does not stop the start")
        self.assertEqual(self.run_runner("--cases", "2").returncode, 0, "without the option the file is fine")

    def test_dry_run_shows_the_instruction_lines(self):
        lines = self.lines_file()
        p = self.run_runner("--dry-run", "--instruction-lines", str(lines))
        self.assertEqual(p.returncode, 0, p.all)
        self.assertFalse(self.ws.exists())
        self.assertEqual(self.starts(), 0)
        self.assertIn(f"  lines:   {lines.resolve()} written to CLAUDE.md", p.stdout)
        self.assertEqual(p.stdout.count("written to CLAUDE.md"), 2, "one line per case, on the third side only")
        self.assertIn("case 1, without_skill_plus_lines, run 1", p.stdout)

    def test_start_again_skips_finished_third_side(self):
        lines = str(self.lines_file())
        self.assertEqual(self.run_runner("--cases", "1").returncode, 0)
        self.assertEqual(self.starts(), 2)
        p = self.run_runner("--cases", "1", "--instruction-lines", lines)
        self.assertEqual(p.returncode, 0, p.all)
        self.assertEqual(self.starts(), 3, "only the new side runs")
        p = self.run_runner("--cases", "1", "--instruction-lines", lines)
        self.assertEqual(p.returncode, 0, p.all)
        self.assertEqual(self.starts(), 3, "the finished third side is skipped")
        row = next(l for l in p.stdout.splitlines() if l.split()[1:2] == ["without_skill_plus_lines"])
        self.assertIn("ok (earlier)", row)

    def set_case_one(self, **fields):
        cases = read_json(self.skill / "evals" / "evals.json")
        cases["evals"][0].update(fields)
        write(self.skill / "evals" / "evals.json", json.dumps(cases))

    def test_setup_script_prepares_the_run_folder_and_a_failing_one_stops_only_that_run(self):
        write(self.skill / "evals" / "prepare.py",
              "import os, sys\nfrom pathlib import Path\n"
              "arm = os.environ['MAKE_SKILL_ARM']\n"
              "Path('prepared.txt').write_text(arm + ' ' + os.environ['MAKE_SKILL_CASE'], encoding='utf-8')\n"
              "print('prepared for ' + arm)\n"
              "sys.exit(3 if arm == 'without_skill' else 0)\n")
        self.set_case_one(setup="evals/prepare.py")
        p = self.run_runner("--cases", "1", "--keep-work")
        self.assertEqual(self.starts(), 1, "the app is started only where the preparation worked")
        good = self.case_dir(1) / "with_skill" / "run-1"
        self.assertEqual(read_json(good / "run.json")["status"], "ok")
        self.assertEqual((good / "work" / "prepared.txt").read_text(encoding="utf-8"), "with_skill 1")
        self.assertIn("prepared for with_skill", (good / "setup.txt").read_text(encoding="utf-8"))
        self.assertFalse((good / "outputs" / "prepared.txt").exists(), "what the preparation made is not an output")
        bad = read_json(self.case_dir(1) / "without_skill" / "run-1" / "run.json")
        self.assertEqual(bad["status"], "failed")
        for words in ("preparation script", "exit code 3", "the app was not started", "setup.txt"):
            self.assertIn(words, bad["reason"])

        self.set_case_one(setup="evals/nowhere.py")
        p = self.run_runner("--cases", "1")
        self.assertEqual(p.returncode, 2, p.all)
        self.assertIn("which is not a file inside the skill folder", p.all)
        self.assertEqual(self.starts(), 1, "nothing more was started")

    def test_files_root_is_left_off_in_the_run_folder(self):
        write(self.skill / "evals" / "files" / "sub" / "b.md", "second input\n")
        self.set_case_one(files_root="evals/files", files=["evals/files/a.md", "evals/files/sub/b.md"])
        p = self.run_runner("--cases", "1", "--keep-work")
        self.assertEqual(p.returncode, 0, p.all)
        for arm in ("with_skill", "without_skill"):
            work = self.case_dir(1) / arm / "run-1" / "work"
            self.assertEqual((work / "a.md").read_text(encoding="utf-8"), "input file\n")
            self.assertEqual((work / "sub" / "b.md").read_text(encoding="utf-8"), "second input\n")
            self.assertFalse((work / "evals").exists(), "the files_root part of the path is left off")

    def test_files_root_wrong_or_file_outside_it_stops(self):
        for fields, words in (({"files_root": "evals/nowhere"}, "which is not a folder inside the skill folder"),
                              ({"files_root": "../x"}, "which is not a folder inside the skill folder"),
                              ({"files_root": "scripts"}, 'which is not inside its "files_root"')):
            with self.subTest(fields=fields):
                self.set_case_one(**fields)
                p = self.run_runner()
                self.assertEqual(p.returncode, 2, p.all)
                self.assertIn(words, p.stderr)
                self.assertIn('remove "files_root"', p.stderr)
                self.assertNotIn("Traceback", p.all)
                self.assertFalse(self.ws.exists())

    def test_files_root_counts_for_the_claude_md_clash(self):
        write(self.skill / "evals" / "files" / "CLAUDE.md", "the case's own file\n")
        self.set_case_one(files_root="evals/files", files=["evals/files/CLAUDE.md"])
        p = self.run_runner("--instruction-lines", str(self.lines_file()))
        self.assertEqual(p.returncode, 2, p.all)
        self.assertIn("overwrite", p.stderr)

    def test_missing_cases_file_says_what_to_do(self):
        p = self.run_runner("--cases-file", str(self.tmp / "nope.json"))
        self.assertEqual(p.returncode, 2)
        self.assertIn("No test cases file at", p.stderr)
        self.assertIn('"evals"', p.stderr)
        self.assertIn("--cases-file", p.stderr)
        self.assertNotIn("Traceback", p.all)
        self.assertFalse(self.ws.exists())

    def test_workspace_under_an_instruction_file_is_pointed_out(self):
        # the PC that runs this test may have an instruction file further up, so only this folder's file is looked for
        p = self.run_runner("--dry-run")
        self.assertNotIn(str(self.tmp / "CLAUDE.md"), p.stdout)
        write(self.tmp / "CLAUDE.md", "Rules of the project around the workspace.\n")
        p = self.run_runner("--dry-run")
        self.assertEqual(p.returncode, 0, p.all)
        self.assertIn("its own instruction file", p.stdout)
        self.assertIn(str(self.tmp / "CLAUDE.md"), p.stdout)
        self.assertIn("--workspace", p.stdout)

    @unittest.skipUnless(os.name == "nt", "the desktop app's private folder exists on Windows only")
    def test_program_is_found_in_the_desktop_apps_private_folder(self):
        local = self.tmp / "local"
        base = local / "Packages" / "Claude_abc123" / "LocalCache" / "Roaming" / "Claude" / "claude-code"
        write(base / "2.1.9" / "aaa" / "claude.exe", "older")
        write(base / "2.1.10" / "bbb" / "claude.exe", "newer")
        (self.tmp / "roaming").mkdir()
        (self.tmp / "empty-path").mkdir()
        env = self.env(APPDATA=str(self.tmp / "roaming"), LOCALAPPDATA=str(local), PATH=str(self.tmp / "empty-path"))
        p = subprocess.run([sys.executable, str(RUNNER), "--skill", str(self.skill), "--workspace", str(self.ws),
                            "--dry-run"], env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(str(base / "2.1.10" / "bbb" / "claude.exe"), p.stdout)


if __name__ == "__main__":
    unittest.main()
