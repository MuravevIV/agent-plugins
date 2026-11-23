"""Prepares one run's folder for the trail test. The test runner starts it in that folder before the app.

It turns the copied files into a small git repository, gives the run a fresh throwaway project in the local
Plane with the same starting tickets every time, and puts the tool skills of the run's side next to the skill
under test. Used once, on this PC, on 2026-11-22.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plane_api as P  # noqa: E402

CASE = os.environ.get("MAKE_SKILL_CASE", "0")
ARM = os.environ.get("MAKE_SKILL_ARM", "with_skill")
RUN = os.environ.get("MAKE_SKILL_RUN", "1")
RUN_DIR = Path(os.environ.get("MAKE_SKILL_RUN_DIR", "."))
USER_SKILLS = Path.home() / ".claude" / "skills"
OLD_SKILLS = Path.home() / ".claude" / "skills-disabled"
# The tool skills each side gets next to the skill under test.
TOOL_SKILLS = {"with_skill": [USER_SKILLS / "plane", USER_SKILLS / "bookstack"],
               "old_skill": [OLD_SKILLS / "bookstack-docs"]}
JIRA_LINE = ("\nThe double-space bug in `count_words` was reported upstream as "
             "https://jira.example.invalid/browse/OPS-412.\n")

# name, parent (index into this list or None), state group. Order gives the ticket numbers 1 to 10.
SEED = [
    ("Epic: Counting", None, "backlog"),
    ("Epic: Command line", None, "backlog"),
    ("Feature: Count by line", 0, "unstarted"),
    ("Handle empty input", 0, "completed"),
    ("Count words separated by tabs", 0, "unstarted"),
    ("Add a --json flag", 1, "backlog"),
    ("Read input from a file", 2, "started"),
    ("Report the longest line", 2, "unstarted"),
    ("Add a --version flag", 1, "started"),
    ("Drop Python 3.8 support", 1, "cancelled"),
]


def git(*args):
    done = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed in {Path.cwd()}: {done.stderr.strip()}")


def new_project():
    taken = {p.get("identifier") for p in P.every("projects/")}
    base = f"TR{CASE}{'N' if ARM == 'with_skill' else 'O'}{RUN}"
    ident = next(i for i in [base] + [base + c for c in "BCDEFGHJK"] if i not in taken)
    project = P.call("POST", "projects/", {"name": f"Trail test {ident}", "identifier": ident})
    states = {s["group"]: s["id"] for s in P.every(f"projects/{project['id']}/states/")}
    made = []
    for name, parent, group in SEED:
        body = {"name": name, "state": states[group]}
        if parent is not None:
            body["parent"] = made[parent]["id"]
        made.append(P.call("POST", f"projects/{project['id']}/issues/", body))
    return ident, project, made


def main():
    try:
        ident, project, made = new_project()
    except P.PlaneProblem as e:
        sys.exit(f"Could not prepare the Plane project for this run: {e}")
    readme = Path("README.md")
    text = readme.read_text(encoding="utf-8").replace("`TRL0`", f"`{ident}`")
    if CASE == "5":
        text += JIRA_LINE
    readme.write_text(text, encoding="utf-8", newline="\n")

    for src in TOOL_SKILLS.get(ARM, []):
        if not src.is_dir():
            sys.exit(f"The tool skill folder {src} does not exist, so this side of the test cannot be set up.")
        shutil.copytree(src, Path(".claude") / "skills" / src.name, dirs_exist_ok=True)

    git("init", "-q", "-b", "main")
    git("config", "user.name", "Trail Test")
    git("config", "user.email", "trail-test@example.invalid")
    Path(".git", "info", "exclude").write_text(".claude/\n", encoding="utf-8")  # the skills are not part of the repo
    git("add", "-A")
    git("commit", "-q", "-m", "Initial import")

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "plane-project.json").write_text(json.dumps({
        "identifier": ident, "project_id": project["id"], "case": CASE, "arm": ARM, "run": RUN,
        "seeded": [{"id": m["id"], "number": m["sequence_id"], "name": m["name"]} for m in made]}, indent=2),
        encoding="utf-8")
    print(f"Plane project {ident} with {len(made)} starting tickets; git repository with one commit; "
          f"tool skills: {', '.join(s.name for s in TOOL_SKILLS.get(ARM, [])) or 'none'}")


if __name__ == "__main__":
    main()
