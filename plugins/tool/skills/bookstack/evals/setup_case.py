"""Prepares one run's folder for the test of the bookstack tool skill. The test runner starts it there before the app.

Each run gets its own shelf name in the user's local BookStack, written into docs/.wiki-sync.json, and a git
repository with one commit. Cases 2 and 3 start from docs that are already mirrored: for them the sync script of
this skill is run once here. Used once, on this PC, on 2026-11-23.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List

CASE = os.environ.get("MAKE_SKILL_CASE", "0")
ARM = os.environ.get("MAKE_SKILL_ARM", "with_skill")
RUN = os.environ.get("MAKE_SKILL_RUN", "1")
RUN_DIR = Path(os.environ.get("MAKE_SKILL_RUN_DIR", "."))
SYNC = Path(__file__).resolve().parent.parent / "scripts" / "sync_docs_wiki.py"


def run(cmd: List[str]) -> str:
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        sys.exit(f"{' '.join(cmd[:3])} ... failed in {Path.cwd()}: {(done.stderr or done.stdout).strip()[:600]}")
    return done.stdout


def main() -> None:
    shelf = f"zz-tool-test-{CASE}{'n' if ARM == 'with_skill' else 'o'}{RUN}-{time.strftime('%m%d-%H%M%S')}"
    state = Path("docs") / ".wiki-sync.json"
    state.write_text(json.dumps({"shelf": shelf, "pages": {}}, indent=2) + "\n", encoding="utf-8", newline="\n")
    first_sync = ""
    if CASE in ("2", "3"):
        first_sync = run([sys.executable, str(SYNC)])
    run(["git", "init", "-q", "-b", "main"])
    run(["git", "config", "user.name", "Tool Test"])
    run(["git", "config", "user.email", "tool-test@example.invalid"])
    Path(".git", "info", "exclude").write_text(".claude/\n", encoding="utf-8")
    run(["git", "add", "-A"])
    run(["git", "commit", "-q", "-m", "Initial import"])
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "wiki-shelf.json").write_text(json.dumps({
        "shelf": shelf, "case": CASE, "arm": ARM, "run": RUN,
        "pages_before": json.loads(state.read_text(encoding="utf-8"))["pages"]}, indent=2), encoding="utf-8")
    print(f"shelf name {shelf}; git repository with one commit; first sync: {first_sync.strip().splitlines()[-1:] or 'none'}")


if __name__ == "__main__":
    main()
