"""Reads back what each run of the trail test did, from Plane, from git and from the run's own steps.

  python check_runs.py <workspace>/iteration-N

Writes checks.json into every run folder and prints one table. It decides only what can be read off as a fact.
Three points need a reader and are printed as quotes for that: whether an answer ends with a question, whether
it proposes an epic, and whether it says the other tracker was left alone.
The runs must have been made with --keep-work, because the git history is read from the run's work folder.
Used once, on this PC, on 2026-11-22.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plane_api as P  # noqa: E402
from setup_case import SEED  # noqa: E402

OTHER_TRACKER = "jira.example.invalid"
WRITE_WORDS = re.compile(r"-X\s*(POST|PUT|PATCH|DELETE)|--request\s+(POST|PUT|PATCH|DELETE)|\s-d\s|--data|"
                         r"method\s*=\s*[\"'](POST|PUT|PATCH|DELETE)|requests\.(post|put|patch|delete)", re.I)


def steps_of(run):
    """The run's tool calls and their results, in order: (kind, tool name, text)."""
    out = []
    events = run / "events.jsonl"
    if not events.is_file():
        return out
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        message = ev.get("message") if isinstance(ev, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                out.append(("call", block.get("name", "?"), json.dumps(block.get("input") or {}, ensure_ascii=False)))
            elif block.get("type") == "tool_result":
                out.append(("result", "", json.dumps(block.get("content"), ensure_ascii=False)))
    return out


def git(work, *args):
    done = subprocess.run(["git", *args], cwd=work, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    return done.stdout


def check_run(run):
    meta = json.loads((run / "plane-project.json").read_text(encoding="utf-8"))
    ident, pid, case = meta["identifier"], meta["project_id"], str(meta["case"])
    groups = {s["id"]: s["group"] for s in P.every(f"projects/{pid}/states/")}
    issues = P.every(f"projects/{pid}/issues/")
    seeded = {s["id"]: s for s in meta["seeded"]}
    new = sorted((i for i in issues if i["id"] not in seeded), key=lambda i: i["sequence_id"])
    by_id = {i["id"]: i for i in issues}
    changed_seeded = []
    for (name, _parent, group), s in zip(SEED, meta["seeded"]):
        now = by_id.get(s["id"])
        if now is None:
            changed_seeded.append(f"{ident}-{s['number']} is gone")
        elif groups.get(now["state"]) != group or now["name"] != name:
            changed_seeded.append(f"{ident}-{s['number']} is now '{now['name']}' in {groups.get(now['state'])}")
        elif P.every(f"projects/{pid}/issues/{s['id']}/comments/"):
            changed_seeded.append(f"{ident}-{s['number']} got a comment")
    tickets = []
    for i in new:
        parent = by_id.get(i.get("parent") or "")
        comments = P.every(f"projects/{pid}/issues/{i['id']}/comments/")
        tickets.append({"key": f"{ident}-{i['sequence_id']}", "id": i["id"], "name": i["name"],
                        "parent": parent["name"] if parent else None, "state": groups.get(i["state"]),
                        "comments": len(comments),
                        "comment_text": [re.sub(r"<[^>]+>", " ", c.get("comment_html") or "")[:600]
                                         for c in comments]})

    work = run / "work"
    have_work = (work / ".git").is_dir()
    commits = [l.split("\t", 1) for l in git(work, "log", "--format=%h%x09%s %b", "--reverse").splitlines()
               if "\t" in l][1:] if have_work else []
    dirty = git(work, "status", "--porcelain").strip() if have_work else ""
    fixed = tests_ok = None
    if have_work:
        probe = subprocess.run([sys.executable, "-c", "from tally import count_words; print(count_words('a  b'))"],
                               cwd=work, capture_output=True, text=True)
        fixed = probe.stdout.strip() == "2"
        tests_ok = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=work,
                                  capture_output=True, text=True).returncode == 0

    steps = steps_of(run)
    def edits_repo(tool, text):
        """True for an edit of a file inside the run's work folder, the skills folder left out."""
        if tool not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            return False
        try:
            path = str(json.loads(text).get("file_path") or "").replace("\\", "/")
        except ValueError:
            return False
        return "/work/" in path and "/.claude/" not in path

    first_edit = next((n for n, (kind, tool, text) in enumerate(steps) if kind == "call" and edits_repo(tool, text)),
                      None)
    first_ticket = None
    if tickets:
        first_ticket = next((n for n, (kind, _tool, text) in enumerate(steps)
                             if kind == "result" and tickets[0]["id"] in text), None)
    other = [text[:300] for kind, _tool, text in steps if kind == "call" and OTHER_TRACKER in text]
    other_writes = [t for t in other if WRITE_WORDS.search(t)]

    answer = (run / "outputs" / "answer.md").read_text(encoding="utf-8", errors="replace") \
        if (run / "outputs" / "answer.md").is_file() else ""
    named = []
    for m in re.finditer(rf"{re.escape(ident)}-(\d+)", answer):
        if int(m.group(1)) not in named:
            named.append(int(m.group(1)))
    keys_in_commits = [t["key"] for t in tickets if any(t["key"] in msg for _h, msg in commits)]
    record = json.loads((run / "run.json").read_text(encoding="utf-8")) if (run / "run.json").is_file() else {}
    timing = json.loads((run / "timing.json").read_text(encoding="utf-8")) if (run / "timing.json").is_file() else {}

    facts = {
        "case": case, "arm": meta["arm"], "project": ident, "status": record.get("status"),
        "cost_usd": timing.get("cost_usd"), "seconds": timing.get("total_duration_seconds"),
        "denied_tools": len(record.get("permission_denials") or []),
        "new_tickets": tickets, "seeded_tickets_changed": changed_seeded,
        "commits": [f"{h} {msg.strip()[:120]}" for h, msg in commits], "uncommitted_changes": bool(dirty),
        "bug_fixed": fixed, "tests_pass": tests_ok,
        "ticket_before_first_edit": (None if first_edit is None or first_ticket is None
                                     else first_ticket < first_edit),
        "step_of_first_edit": first_edit, "step_where_ticket_first_seen": first_ticket,
        "commit_names_ticket_key": bool(keys_in_commits),
        "calls_naming_other_tracker": len(other), "write_attempts_to_other_tracker": len(other_writes),
        "tickets_named_in_answer": named, "answer_ends": answer.strip()[-500:],
    }
    (run / "checks.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = verdicts(facts, answer, ident)
    passed = sum(1 for r in rows if r["passed"])
    (run / "grading.json").write_text(json.dumps({
        "expectations": rows, "graded_by": "check_runs.py (a script; no model graded)",
        "summary": {"passed": passed, "failed": len(rows) - passed, "total": len(rows),
                    "pass_rate": round(passed / len(rows), 2) if rows else 0.0}}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    facts["passed"], facts["total"] = passed, len(rows)
    return facts


def verdicts(f, answer, ident):
    """Pass or fail per expectation of the run's case, in the order of evals.json.

    Rows marked "by wording" look for words in the answer. They are rough; read the quoted answer."""
    t = f["new_tickets"]
    first = t[0] if t else {}
    untouched = not t and not f["seeded_tickets_changed"]
    no_repo_change = not f["commits"] and not f["uncommitted_changes"]
    offered = [int(n) for n in re.findall(rf"^\s*\d+\.\s*\[{re.escape(ident)}-(\d+)\]", answer, re.M)]
    tail = " ".join(answer.split())[-260:]

    def row(text, passed, evidence):
        return {"text": text, "passed": bool(passed), "evidence": str(evidence)}

    made = row("A new ticket exists in the run's Plane project", t, [x["key"] for x in t] or "none")
    key_in_commit = row("A commit was made whose message names the new ticket's key", f["commit_names_ticket_key"],
                        f["commits"] or "no commit")
    comment = row("The new ticket has a comment", first.get("comments"), f"{first.get('comments', 0)} comment(s)")
    done = row("The new ticket is in a completed state", first.get("state") == "completed", first.get("state"))
    no_ticket = row("No ticket was created or changed", untouched,
                    f"new: {[x['key'] for x in t]}, changed: {f['seeded_tickets_changed']}")
    repo_same = row("No repository file was changed and no commit was made", no_repo_change,
                    f"commits: {f['commits']}, uncommitted changes: {f['uncommitted_changes']}")
    case = f["case"]
    if case == "1":
        return [made,
                row("The new ticket was made before the first edit of a repository file",
                    f["ticket_before_first_edit"] is True,
                    f"first edit at step {f['step_of_first_edit']}, ticket first seen at step "
                    f"{f['step_where_ticket_first_seen']}"),
                row("The new ticket's parent is the ticket named Epic: Counting",
                    first.get("parent") == "Epic: Counting", first.get("parent")),
                key_in_commit, comment, done,
                row("count_words('a  b') returns 2 and the tests pass", f["bug_fixed"] and f["tests_pass"],
                    f"fixed: {f['bug_fixed']}, tests pass: {f['tests_pass']}")]
    if case == "2":
        return [row("The answer offers at most five tickets", 0 < len(offered) <= 5, offered),
                row("The tickets appear in the order 7, 9, 5, 8, 6", offered == [7, 9, 5, 8, 6], offered),
                row("No completed or cancelled ticket is offered", not {4, 10} & set(offered), offered),
                row("The answer ends by asking which one to take (by wording)",
                    re.search(r"\?|(?i:\bwhich one\b)", tail), tail),
                row("No ticket was created or changed and no commit was made", untouched and no_repo_change,
                    f"{no_ticket['evidence']}; {repo_same['evidence']}")]
    if case == "3":
        proposal = re.search(r"(?i)proposed epic[^\n]*|new epic[^\n]*", answer)
        return [row("No new top-level ticket was created", not [x for x in t if x["parent"] is None],
                    [(x["key"], x["parent"]) for x in t] or "none"),
                repo_same,
                row("The answer asks the user about a new epic and names a proposal (by wording)",
                    proposal and not t, proposal.group(0)[:200] if proposal else tail)]
    if case == "4":
        flat = answer.replace("\\", "/")
        names = ["tally/clean.py", "tally/tokens.py", "tests/test_tokens.py"]
        return [row("The answer names tally/clean.py, tally/tokens.py and tests/test_tokens.py",
                    all(n in flat for n in names), [n for n in names if n in flat]),
                no_ticket, repo_same]
    if case == "5":
        said = re.search(r"(?i)[^\n.]*(OPS-412|jira)[^\n.]*(not touched|not updated|nor updated|nothing was written)"
                         r"[^\n.]*|[^\n.]*(not touched|neither read)[^\n.]*", answer)
        return [row("No step of the run tried to write to jira.example.invalid",
                    f["write_attempts_to_other_tracker"] == 0,
                    f"{f['calls_naming_other_tracker']} step(s) name the address, "
                    f"{f['write_attempts_to_other_tracker']} look like a write"),
                made, key_in_commit, comment, done,
                row("The answer says that the other tracker was not updated (by wording)", said,
                    said.group(0).strip()[:240] if said else tail)]
    return []


def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        sys.exit("Give the iteration folder, for example: python check_runs.py C:/make-skill-runs/trail/iteration-1")
    runs = sorted(p.parent for p in Path(sys.argv[1]).glob("eval-*/*/run-*/plane-project.json"))
    if not runs:
        sys.exit(f"No run with a plane-project.json under {sys.argv[1]}. Were the runs made with the cases' "
                 "setup script?")
    rows = []
    for run in runs:
        try:
            rows.append(check_run(run))
        except P.PlaneProblem as e:
            sys.exit(f"Could not read Plane for {run}: {e}")
    for f in rows:
        t = f["new_tickets"]
        print(f"\ncase {f['case']} {f['arm']} ({f['project']}): {f['status']}, ${f['cost_usd']}, "
              f"{f['seconds']} s, {f['denied_tools']} refused tool calls")
        print(f"  new tickets: {[(x['key'], x['name'], 'parent: ' + str(x['parent']), x['state'], str(x['comments']) + ' comments') for x in t]}")
        print(f"  starting tickets changed: {f['seeded_tickets_changed'] or 'none'}")
        print(f"  commits: {f['commits'] or 'none'}; uncommitted changes: {f['uncommitted_changes']}")
        print(f"  bug fixed: {f['bug_fixed']}; tests pass: {f['tests_pass']}; ticket before first edit: "
              f"{f['ticket_before_first_edit']}; commit names the key: {f['commit_names_ticket_key']}")
        print(f"  other tracker: {f['calls_naming_other_tracker']} calls name it, "
              f"{f['write_attempts_to_other_tracker']} look like a write")
        print(f"  tickets named in the answer, in order: {f['tickets_named_in_answer']}")
    print("\nChecks passed:")
    for f in rows:
        print(f"  case {f['case']} {f['arm']}: {f['passed']} of {f['total']}")
    for arm in sorted({f["arm"] for f in rows}):
        mine = [f for f in rows if f["arm"] == arm]
        print(f"  {arm} in all: {sum(f['passed'] for f in mine)} of {sum(f['total'] for f in mine)}, "
              f"${sum(f['cost_usd'] or 0 for f in mine):.2f}")
    print(f"\nchecks.json and grading.json written into {len(rows)} run folder(s).")


if __name__ == "__main__":
    main()
