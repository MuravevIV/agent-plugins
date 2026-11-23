"""Reads back what each run of the plane tool skill's test did, from Plane and from the run's answer.

  python check_runs.py <workspace>/iteration-N

Writes checks.json and grading.json into every run folder and prints a table. A script decides everything;
one row goes by the wording of the answer and says so. Used once, on this PC, on 2026-11-23.
"""
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plane_api as P  # noqa: E402
from setup_case import SEED  # noqa: E402

OPEN = [1, 2, 3, 5, 6, 7, 8, 9]


def row(text: str, passed: Any, evidence: Any) -> Dict[str, Any]:
    return {"text": text, "passed": bool(passed), "evidence": str(evidence)}


def tool_calls(run: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    events = run / "events.jsonl"
    if not events.is_file():
        return counts
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        message = ev.get("message") if isinstance(ev, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = str(block.get("name", "?"))
                text = json.dumps(block.get("input") or {})
                if name == "Bash" and "plane.py" in text:
                    name = "Bash, the skill's script"
                counts[name] = counts.get(name, 0) + 1
    return counts


def check_run(run: Path) -> Dict[str, Any]:
    meta = json.loads((run / "plane-project.json").read_text(encoding="utf-8"))
    ident, pid, case = meta["identifier"], meta["project_id"], str(meta["case"])
    groups = {s["id"]: s["group"] for s in P.every(f"projects/{pid}/states/")}
    issues = P.every(f"projects/{pid}/issues/")
    by_id = {i["id"]: i for i in issues}
    seeded = {s["id"]: s for s in meta["seeded"]}
    new = sorted((i for i in issues if i["id"] not in seeded), key=lambda i: i["sequence_id"])
    changed: List[str] = []
    for (name, _parent, group), s in zip(SEED, meta["seeded"]):
        now = by_id.get(s["id"])
        if now is None:
            changed.append(f"{s['number']} is gone")
        elif groups.get(now["state"]) != group or now["name"] != name:
            changed.append(f"{s['number']} is now '{now['name']}' in {groups.get(now['state'])}")
    tickets = []
    for i in new:
        parent = by_id.get(i.get("parent") or "")
        tickets.append({"key": f"{ident}-{i['sequence_id']}", "name": i["name"],
                        "parent": parent["name"] if parent else None, "group": groups.get(i["state"]),
                        "comments": len(P.every(f"projects/{pid}/issues/{i['id']}/comments/"))})
    answer_file = run / "outputs" / "answer.md"
    answer = answer_file.read_text(encoding="utf-8", errors="replace") if answer_file.is_file() else ""
    named = sorted({int(n) for n in re.findall(rf"{re.escape(ident)}-(\d+)", answer)})

    if case == "1":
        listed_as_open = [n for n in (4, 10) if re.search(
            rf"{re.escape(ident)}-{n}\b[^\n]*(?i:backlog|todo|in progress|unstarted|started)", answer)]
        rows = [row("The answer names all eight open tickets", all(n in named for n in OPEN), named),
                row("The answer does not list ticket 4 or ticket 10 as open (by wording)",
                    not listed_as_open and not ({4, 10} & set(named)) or not listed_as_open,
                    f"named: {named}; shown with an open state: {listed_as_open}"),
                row("No ticket was created or changed", not tickets and not changed,
                    f"new: {[t['key'] for t in tickets]}, changed: {changed}")]
    elif case == "2":
        first = tickets[0] if tickets else {}
        rows = [row("Exactly one new ticket exists and its name is Count words in a file",
                    len(tickets) == 1 and first.get("name") == "Count words in a file",
                    [(t["key"], t["name"]) for t in tickets]),
                row("The new ticket's parent is the ticket named Epic: Counting",
                    first.get("parent") == "Epic: Counting", first.get("parent")),
                row("The new ticket is in a started state", first.get("group") == "started", first.get("group")),
                row("The new ticket has exactly one comment", first.get("comments") == 1, first.get("comments")),
                row("No starting ticket was changed", not changed, changed or "none")]
    else:
        five = by_id.get(meta["seeded"][4]["id"], {})
        others = [c for c in changed if not c.startswith("5 ")]
        rows = [row("Ticket 5 is in a completed state", groups.get(five.get("state")) == "completed",
                    groups.get(five.get("state"))),
                row("No other ticket was changed and no ticket was created", not others and not tickets,
                    f"changed: {others}, new: {[t['key'] for t in tickets]}"),
                row("The answer names ticket 1 or Epic: Counting as the parent",
                    1 in named or "Epic: Counting" in answer or re.search(r"(?i)\bCounting\b", answer), named)]

    passed = sum(1 for r in rows if r["passed"])
    record = json.loads((run / "run.json").read_text(encoding="utf-8")) if (run / "run.json").is_file() else {}
    timing = json.loads((run / "timing.json").read_text(encoding="utf-8")) if (run / "timing.json").is_file() else {}
    facts = {"case": case, "arm": meta["arm"], "project": ident, "status": record.get("status"),
             "cost_usd": timing.get("cost_usd"), "seconds": timing.get("total_duration_seconds"),
             "turns": record.get("num_turns"), "refused_tool_calls": len(record.get("permission_denials") or []),
             "skill_opened": record.get("skill_used"), "tool_calls": tool_calls(run),
             "new_tickets": tickets, "starting_tickets_changed": changed, "passed": passed, "total": len(rows)}
    (run / "checks.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")
    (run / "grading.json").write_text(json.dumps({
        "expectations": rows, "graded_by": "check_runs.py (a script; no model graded)",
        "summary": {"passed": passed, "failed": len(rows) - passed, "total": len(rows),
                    "pass_rate": round(passed / len(rows), 2)}}, indent=2, ensure_ascii=False), encoding="utf-8")
    return facts


def main() -> None:
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        sys.exit("Give the iteration folder, for example: python check_runs.py C:/make-skill-runs/tool-plane/iteration-1")
    runs = sorted(p.parent for p in Path(sys.argv[1]).glob("eval-*/*/run-*/plane-project.json"))
    if not runs:
        sys.exit(f"No run with a plane-project.json under {sys.argv[1]}.")
    facts = []
    for run in runs:
        try:
            facts.append(check_run(run))
        except P.PlaneProblem as e:
            sys.exit(f"Could not read Plane for {run}: {e}")
    for f in facts:
        print(f"case {f['case']} {f['arm']:<10} {f['passed']} of {f['total']}  ${f['cost_usd'] or 0:.2f}  "
              f"{f['seconds']} s  {f['turns']} turns  skill opened: {f['skill_opened']}  "
              f"refused: {f['refused_tool_calls']}  calls: {f['tool_calls']}")
    for arm in sorted({f["arm"] for f in facts}):
        mine = [f for f in facts if f["arm"] == arm]
        print(f"{arm} in all: {sum(f['passed'] for f in mine)} of {sum(f['total'] for f in mine)}, "
              f"${sum(f['cost_usd'] or 0 for f in mine):.2f}, {sum(f['seconds'] or 0 for f in mine):.0f} s, "
              f"{sum(f['turns'] or 0 for f in mine)} turns")


if __name__ == "__main__":
    main()
