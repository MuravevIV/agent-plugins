"""Tests for tools/publish_check.py. Each test builds a small git repository in a temporary folder.

Run with:
  python -m unittest discover -s tests/tools
"""
import io
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Tuple

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "publish_check.py"
spec = importlib.util.spec_from_file_location("publish_check_under_test", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

# Made-up values in the shapes the check looks for. None of them is real.
FAKE_KEY = "plane_api_" + "0123456789abcdef0123456789abcdef"
FAKE_TOKEN = "Zx9" + "Qw8Er7Ty6Ui5Op4As3Df2Gh1Jk0L"
# Put together here, so that this file does not trip the check it tests.
AT, SLASH = "@", chr(92)
MAIL_ONE = "jane.doe" + AT + "realmail.org"
MAIL_TWO = "real.person" + AT + "realmail.org"
WIN_HOME = "C:" + SLASH + "Users" + SLASH + "Realname"
UNIX_HOME = "/" + "home/realname"
MAC_HOME = "/" + "Users/Realname"


class PublishCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="publish-check-test-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test Person")
        self.git("config", "user.email", "12345+test@users.noreply.github.com")
        self.write("README.md", "# A clean project\n\nNothing private here.\n")
        self.commit("first")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def run_check(self, *args: str) -> Tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = check.main(["--repo", str(self.repo), *args])
        return code, out.getvalue()

    def test_clean_repository_passes_and_says_the_check_is_rough(self) -> None:
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("Nothing found", out)
        self.assertIn("No private word list was given", out)

    def test_key_is_found_and_never_printed_whole(self) -> None:
        self.write("notes.md", f"use {FAKE_KEY} for the tracker\nAPI_TOKEN = \"{FAKE_TOKEN}\"\n")
        self.commit("notes")
        code, out = self.run_check("--no-history")
        self.assertEqual(code, 1, out)
        self.assertIn("notes.md, line 1: a key with a known prefix", out)
        self.assertIn("notes.md, line 2: a value given to a key, token, secret or password", out)
        self.assertNotIn(FAKE_KEY, out)
        self.assertNotIn(FAKE_TOKEN, out)
        self.assertIn("Do not push yet", out)

    def test_names_of_settings_and_placeholders_are_not_keys(self) -> None:
        self.write("doc.md", "Set PLANE_API_KEY in the environment.\napi_key = <your key>\n"
                             "token: PLANE_API_KEY\nAPI_TOKEN_SECRET = API_TOKEN_SECRET_GOES_HERE_PLEASE\n")
        self.commit("doc")
        code, out = self.run_check("--no-history")
        self.assertEqual(code, 0, out)

    def test_email_is_found_but_hidden_and_example_addresses_are_let_through(self) -> None:
        self.write("a.md", f"write to {MAIL_ONE}\nor to someone@example.com, noreply@anthropic.com,\n"
                           "tool-test@example.invalid and 1+x@users.noreply.github.com\n")
        self.commit("mail")
        code, out = self.run_check("--no-history")
        self.assertEqual(code, 1, out)
        self.assertIn("a.md, line 1: an e-mail address", out)
        self.assertNotIn("a.md, line 2", out)
        self.assertNotIn("a.md, line 3", out)

    def test_home_folder_path_is_found_and_placeholder_users_are_let_through(self) -> None:
        self.write("a.md", f"logs are in {WIN_HOME}{SLASH}logs\nand {UNIX_HOME}/x and {MAC_HOME}/y\n"
                           "but C:\\Users\\Someone\\logs and /home/user/x are examples\n")
        self.commit("paths")
        code, out = self.run_check("--no-history")
        self.assertEqual(code, 1, out)
        self.assertEqual(out.count("a path inside a user's home folder"), 3, out)
        self.assertNotIn("line 3", out)

    def test_private_word_list_is_used_and_a_missing_list_stops_the_check(self) -> None:
        self.write("a.md", "This came out of the Bluebird project.\n")
        self.commit("word")
        words = self.tmp / "words.txt"
        words.write_text("# private names\nbluebird\n\n", encoding="utf-8")
        code, out = self.run_check("--no-history", "--words", str(words))
        self.assertEqual(code, 1, out)
        self.assertIn("a.md, line 1: a word of the private list: bluebird", out)
        code, out = self.run_check("--no-history")
        self.assertEqual(code, 0, out)
        code, out = self.run_check("--words", str(self.tmp / "nowhere.txt"))
        self.assertEqual(code, 2, out)
        self.assertIn("does not exist", out)

    def test_something_removed_from_the_files_is_still_found_in_the_history(self) -> None:
        self.write("old.md", f"key: {FAKE_KEY}\n")
        self.commit("add a key by mistake")
        (self.repo / "old.md").unlink()
        self.commit("remove it")
        code, out = self.run_check("--no-history")
        self.assertEqual(code, 0, out)
        self.assertIn("history was not looked at", out)
        code, out = self.run_check()
        self.assertEqual(code, 1, out)
        self.assertIn("In the files as they are now: 0 finding(s)", out)
        self.assertIn("old.md: a key with a known prefix", out)
        self.assertNotIn(FAKE_KEY, out)
        self.assertIn("publish from a fresh history", out)

    def test_private_address_of_a_commits_author_is_found_once_with_a_count(self) -> None:
        self.git("config", "user.email", MAIL_TWO)
        self.write("b.md", "one\n")
        self.commit("second")
        self.write("b.md", "two\n")
        self.commit("third")
        code, out = self.run_check()
        self.assertEqual(code, 1, out)
        self.assertIn("author of commits: an e-mail address", out)
        self.assertIn("(in 2 commit(s))", out)
        self.assertNotIn(MAIL_TWO, out)

    def test_folder_that_is_no_repository_says_what_to_do(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = check.main(["--repo", str(self.tmp)])
        self.assertEqual(code, 2, out.getvalue())
        self.assertIn("Give the folder of a git repository with --repo", out.getvalue())


if __name__ == "__main__":
    unittest.main()
