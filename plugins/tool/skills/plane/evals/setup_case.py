"""Prepares one run's folder for the test of the plane tool skill. The test runner starts it there before the app.

Each run gets a fresh throwaway project in the user's local Plane with the same ten starting tickets, and a
README that names the project. Used once, on this PC, on 2026-11-23.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plane_api as P  # noqa: E402

CASE = os.environ.get("MAKE_SKILL_CASE", "0")
ARM = os.environ.get("MAKE_SKILL_ARM", "with_skill")
RUN = os.environ.get("MAKE_SKILL_RUN", "1")
RUN_DIR = Path(os.environ.get("MAKE_SKILL_RUN_DIR", "."))

# name, parent (index into this list or None), state group. Order gives the ticket numbers 1 to 10.
SEED: List[Tuple[str, Optional[int], str]] = [
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


def new_project() -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    taken = {p.get("identifier") for p in P.every("projects/")}
    base = f"TP{CASE}{'N' if ARM == 'with_skill' else 'O'}{RUN}"
    ident = next(i for i in [base] + [base + c for c in "BCDEFGHJK"] if i not in taken)
    project = P.call("POST", "projects/", {"name": f"Tool test {ident}", "identifier": ident})
    states = {s["group"]: s["id"] for s in P.every(f"projects/{project['id']}/states/")}
    made: List[Dict[str, Any]] = []
    for name, parent, group in SEED:
        body: Dict[str, Any] = {"name": name, "state": states[group]}
        if parent is not None:
            body["parent"] = made[parent]["id"]
        made.append(P.call("POST", f"projects/{project['id']}/issues/", body))
    return ident, project, made


def main() -> None:
    try:
        ident, project, made = new_project()
    except P.PlaneProblem as e:
        sys.exit(f"Could not prepare the Plane project for this run: {e}")
    readme = Path("README.md")
    readme.write_text(readme.read_text(encoding="utf-8").replace("`TRL0`", f"`{ident}`"), encoding="utf-8",
                      newline="\n")
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "plane-project.json").write_text(json.dumps({
        "identifier": ident, "project_id": project["id"], "case": CASE, "arm": ARM, "run": RUN,
        "seeded": [{"id": m["id"], "number": m["sequence_id"], "name": m["name"]} for m in made]}, indent=2),
        encoding="utf-8")
    print(f"Plane project {ident} with {len(made)} starting tickets")


if __name__ == "__main__":
    main()
