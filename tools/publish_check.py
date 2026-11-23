"""Looks through a repository for things that must not be published. Run it before every push.

  python tools/publish_check.py [--repo FOLDER] [--words FILE] [--no-history]

It reads every tracked file and, unless --no-history is given, every commit that any local branch or tag
reaches: who made it, its message, and every line it added. It looks for
  - keys and tokens,
  - e-mail addresses,
  - paths inside a user's home folder,
  - any word of a private list (--words FILE, or the file named by PUBLISH_CHECK_WORDS; one word or phrase per
    line, lines starting with # are skipped). Keep that list outside the repository: it is private itself.
It changes nothing and sends nothing. Exit code 0: nothing found. 1: something found. 2: it could not run.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

KEY_PATTERNS: Sequence[Tuple[str, "re.Pattern[str]"]] = (
    ("a private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a key with a known prefix", re.compile(r"\b(?:sk-[A-Za-z0-9_\-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|"
                                             r"github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|"
                                             r"plane_api_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9\-]{20,})")),
    ("a value given to a key, token, secret or password",
     re.compile(r"(?i)\b[A-Za-z0-9_\-]*(?:api[_\-]?key|secret|token|passw(?:or)?d)[A-Za-z0-9_\-]*[\"']?\s*[:=]\s*"
                r"[\"']?([A-Za-z0-9_\-+/=]{24,})")),
)
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
HOME_PATH = re.compile(r"(?:[A-Za-z]:[\\/]+Users[\\/]+|/home/|/Users/)([A-Za-z0-9._\-]+)")
# Names that stand for "some user" in examples and tests.
PLACEHOLDER_USERS = {"you", "user", "username", "name", "someone", "me", "public", "shared", "default"}
SAFE_EMAIL = re.compile(r"(?i)(?:@users\.noreply\.github\.com|noreply@|@example\.|\.invalid$|\.test$|@localhost)")
# A value that only looks like a secret: placeholders and words written in capitals.
NOT_A_SECRET = re.compile(r"^(?:[A-Z_]+|x+|\*+|<.*>|[a-z_]+)$")


class CannotRun(Exception):
    """The check could not be made. The message says what to do."""


def git(repo: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    except OSError as e:
        raise CannotRun(f"git could not be started ({e}). The check reads the repository through git, so "
                        "nothing was looked at. Install git or put it on the path, then run the check again.")
    if done.returncode != 0:
        raise CannotRun(f"`git {' '.join(args[:2])}` failed in {repo}: "
                        f"{done.stderr.decode('utf-8', 'replace').strip()[:300]}\nThe check reads the repository "
                        "through git, so nothing was looked at. Give the folder of a git repository with --repo.")
    return done.stdout.decode("utf-8", "replace")


def mask(value: str) -> str:
    """Enough of a finding to recognise it, never the whole of it."""
    return value if len(value) <= 8 else f"{value[:4]}...{value[-2:]} ({len(value)} characters)"


def read_words(path: Optional[str]) -> List[str]:
    if not path:
        return []
    file = Path(path)
    if not file.is_file():
        raise CannotRun(f"The private word list {file} does not exist. Without it the check would pass files "
                        "that name private things. Give the right file with --words, or leave --words out to "
                        "check without a list.")
    return [line.strip() for line in file.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.strip().startswith("#")]


def findings_in(text: str, words: Sequence[str]) -> List[Tuple[str, str]]:
    """What one line of text holds that must not be published: (kind, masked detail)."""
    found: List[Tuple[str, str]] = []
    for kind, pattern in KEY_PATTERNS:
        for m in pattern.finditer(text):
            value = m.group(1) if m.groups() else m.group(0)
            if not NOT_A_SECRET.match(value):
                found.append((kind, mask(value)))
    for m in EMAIL.finditer(text):
        if not SAFE_EMAIL.search(m.group(0)):
            found.append(("an e-mail address", mask(m.group(0))))
    for m in HOME_PATH.finditer(text):
        if m.group(1).lower() not in PLACEHOLDER_USERS:
            found.append(("a path inside a user's home folder", m.group(0)))
    lowered = text.lower()
    for word in words:
        if word.lower() in lowered:
            found.append(("a word of the private list", word))
    return found


def check_files(repo: Path, words: Sequence[str]) -> List[str]:
    out: List[str] = []
    for rel in git(repo, "ls-files", "-z").split("\0"):
        path = repo / rel
        if not rel or not path.is_file():
            continue
        raw = path.read_bytes()
        if b"\0" in raw[:8000]:
            continue  # not a text file
        for number, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
            for kind, detail in findings_in(line, words):
                out.append(f"{rel}, line {number}: {kind}: {detail}")
    return out


def check_history(repo: Path, words: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen: Dict[str, int] = {}
    log = git(repo, "log", "--all", "--format=%x01%h%x02%an <%ae>%x02%cn <%ce>%x02%s %b%x03", "-p", "--no-color",
              "--no-ext-diff", "--text")
    commit, path = "?", "?"
    for line in log.splitlines():
        if line.startswith("\x01"):
            head = line[1:].split("\x02")
            commit = head[0]
            for who, value in (("author", head[1] if len(head) > 1 else ""),
                               ("committer", head[2] if len(head) > 2 else "")):
                for kind, detail in findings_in(value, words):
                    key = f"{who} of commits: {kind}: {detail}"
                    seen[key] = seen.get(key, 0) + 1
            for kind, detail in findings_in((head[3] if len(head) > 3 else "").replace("\x03", ""), words):
                out.append(f"commit {commit}, its message: {kind}: {detail}")
        elif line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and not line.startswith("+++"):
            for kind, detail in findings_in(line[1:], words):
                out.append(f"commit {commit}, {path}: {kind}: {detail}")
    out = [f"{key} (in {count} commit(s))" for key, count in seen.items()] + out
    return out


def report(title: str, found: Sequence[str], limit: int = 25) -> None:
    print(f"\n{title}: {len(found)} finding(s)")
    for line in found[:limit]:
        print(f"  - {line}")
    if len(found) > limit:
        print(f"  - and {len(found) - limit} more of the same kinds")


def main(argv: Optional[Iterable[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Look through a repository for things that must not be published.")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]),
                        help="the repository to check (default: the one this script is in)")
    parser.add_argument("--words", default=os.environ.get("PUBLISH_CHECK_WORDS"),
                        help="a file with private words, one per line (default: the file named by PUBLISH_CHECK_WORDS)")
    parser.add_argument("--no-history", action="store_true", help="look at the tracked files only, not at old commits")
    args = parser.parse_args(list(argv) if argv is not None else None)
    repo = Path(args.repo).resolve()
    try:
        words = read_words(args.words)
        git(repo, "rev-parse", "--git-dir")
        in_files = check_files(repo, words)
        in_history = [] if args.no_history else check_history(repo, words)
    except CannotRun as e:
        print(f"publish_check.py: {e}", file=sys.stderr)
        return 2
    print(f"Checked {repo}." + ("" if words else " No private word list was given, so only keys, e-mail addresses "
                                                 "and home-folder paths were looked for."))
    report("In the files as they are now", in_files)
    if args.no_history:
        print("\nThe history was not looked at (--no-history). Old commits are published with a push too.")
    else:
        report("In the history (every commit a branch or tag reaches)", in_history)
    if in_files or in_history:
        print("\nDo not push yet. A finding in a file: change the file. A finding in the history stays there even "
              "after the file is changed; publish from a fresh history instead, or ask before rewriting it.")
        return 1
    print("\nNothing found. This check is rough: it knows common shapes of keys and the words it was given. "
          "Read through what is new before a first push all the same.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
