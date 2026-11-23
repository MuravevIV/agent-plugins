#!/usr/bin/env python3
"""Decide the checks of the triad test cases that a script can decide, run by run.

The test runner (make-skill's scripts/run_tests.py) leaves one folder per run:
<iteration>/eval-<id>-<slug>/<side>/run-<k>/ with events.jsonl, run.json and outputs/.
For each run this script decides the case's "script_checks" from evals.json and writes
script_checks.json into the run folder. Cases with "show_handoffs": true also get
outputs/handoffs.md, a readable list of the work the main session handed to subagents.
With --merge the rows are also folded into the run's grading.json.

    python check_runs.py --iteration <iteration folder> [--skill <skill folder>] [--cases 1 4] [--merge]

Checked against real runs of Claude Code 2.1.299 on 2026-11-22. What the script
relies on in events.jsonl is all read in one function, read_record(), so it is easy
to correct if a later version of the app changes it:
  - a tool call is a part {"type": "tool_use", "id", "name", "input"} in the
    message.content list of an event {"type": "assistant", ...};
  - a call is made by the main session (top level) when the event's
    parent_tool_use_id is missing or null; calls inside a subagent carry the id
    of the Agent call that started it;
  - a hand-off is a top-level call named Agent or Task, whose input has "prompt"
    and may have "description", "subagent_type" and "model";
  - the main session's model is run.json "model", else the "model" of the event
    {"type": "system", "subtype": "init"};
  - shell commands are the "command" input of calls named Bash or PowerShell
    (PowerShell is added because Claude Code on Windows offers that tool too);
  - a call the app refused to carry out is listed by its id in
    "permission_denials" (items with "tool_use_id") of the event {"type": "result"}.

Standard library only, Python 3.9 or later. Makes no model calls and uses no network.
Safe to run again: it overwrites only script_checks.json, outputs/handoffs.md and,
with --merge, the script rows of grading.json.
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

MADE_BY = "check_runs.py"
HANDOFF_TOOLS = ("Agent", "Task")
SHELL_TOOLS = ("Bash", "PowerShell")
NOT_READING_TOOLS = ("Write", "Edit", "Agent", "Task")
FAMILIES = ("fable", "opus", "sonnet", "haiku")
COMMAND_SECONDS = 120
HANDOFFS_INTRO = ("This file was made by a script from the record of the run. "
                  "It lists each piece of work the main session handed to a subagent.")
NO_HANDOFFS = "No work was handed to a subagent in this run."


class Stop(Exception):
    """An expected problem that ends the script. The message is written for a person."""


class BadCheck(Exception):
    """A check in evals.json lacks a field it needs."""


# Reading the record of a run. Every guess about the app's output lives here.
def read_record(run_dir):
    """Return (tool calls in file order, model from the init event), or (None, None) without events.jsonl."""
    path = run_dir / "events.jsonl"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    calls, init_model, refused = [], None, set()
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            if init_model is None and isinstance(ev.get("model"), str):
                init_model = ev["model"]
        elif ev.get("type") == "assistant":
            top_level = ev.get("parent_tool_use_id") is None
            message = ev.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            for part in content if isinstance(content, list) else []:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    given = part.get("input")
                    calls.append({"id": part.get("id"), "name": str(part.get("name") or ""),
                                  "input": given if isinstance(given, dict) else {},
                                  "top_level": top_level, "refused": False})
        elif ev.get("type") == "result":
            denials = ev.get("permission_denials")
            refused.update(d.get("tool_use_id") for d in denials if isinstance(d, dict)) \
                if isinstance(denials, list) else None
    for call in calls:
        call["refused"] = call["id"] is not None and call["id"] in refused
    return calls, init_model


# Small helpers
def read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def read_json(path):
    """The parsed file, or None when it is missing or not valid JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))
    os.replace(tmp, path)


def write_json(path, obj):
    write_atomic(path, json.dumps(obj, indent=2) + "\n")


def remove_tree(path):
    def make_writable(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if path.exists():
        shutil.rmtree(path, **{"onexc" if sys.version_info >= (3, 12) else "onerror": make_writable})


def shorten(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def natural_key(path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.name)]


def need(check, field):
    value = check.get(field)
    if value is None or value == "":
        raise BadCheck(field)
    return value


def out_file(run, rel):
    return run["outputs"].joinpath(*[p for p in str(rel).replace("\\", "/").split("/") if p])


def not_made(rel):
    return f"outputs/{rel} does not exist, so the run did not create or change {rel}."


def model_of(call):
    model = call["input"].get("model")
    return str(model).strip() if model not in (None, "") else ""


def handoffs(run):
    return [c for c in run["calls"] if c["top_level"] and c["name"] in HANDOFF_TOOLS]


def shell_command(call):
    if call["name"] not in SHELL_TOOLS:
        return None
    command = call["input"].get("command")
    return command if isinstance(command, str) else None


# The checks. Each takes (check entry, run) and returns (passed, evidence).
def check_no_handoff(check, run):
    found = handoffs(run)
    if not found:
        return True, "The main session handed no work to a subagent."
    models = ", ".join(model_of(c) or "none named" for c in found)
    return False, f"The main session handed work to a subagent {len(found)} time(s); models named: {models}."


def check_handoffs_name_model(check, run):
    found = handoffs(run)
    if not found:
        return False, "no subagent was used"
    manager = (run["manager_model"] or "").lower()
    family = next((f for f in FAMILIES if f in manager), None)
    listed = "; ".join(f"{model_of(c) or 'none named'} ({c['input'].get('subagent_type') or 'no subagent_type'})"
                       for c in found)
    unnamed = [c for c in found if not model_of(c)]
    own = [c for c in found if family and family in model_of(c).lower()]
    if unnamed:
        return False, f"{len(unnamed)} of {len(found)} hand-off(s) name no model. Hand-offs: {listed}."
    if own:
        return False, (f"{len(own)} hand-off(s) name a {family} model, the main session's own "
                       f"({run['manager_model']}). Hand-offs: {listed}.")
    if not family:
        return True, (f"Every hand-off names a model; the main session's model "
                      f"({run['manager_model'] or 'not known'}) is of no known family, so it was not compared. "
                      f"Hand-offs: {listed}.")
    return True, f"Every hand-off names a model other than {family}. Hand-offs: {listed}."


def check_file_exists(check, run):
    rel = need(check, "file")
    if out_file(run, rel).is_file():
        return True, f"outputs/{rel} exists."
    return False, not_made(rel)


def check_file_absent(check, run):
    files = need(check, "files")
    files = [files] if isinstance(files, str) else list(files)
    there = [rel for rel in files if out_file(run, rel).exists()]
    if there:
        return False, f"The run created or changed: {', '.join(there)}."
    return True, f"None of {', '.join(files)} is in outputs/."


def check_file_contains(check, run):
    rel, value = need(check, "file"), str(need(check, "value"))
    text = read_text(out_file(run, rel))
    if text is None:
        return False, not_made(rel)
    if value in text:
        return True, f"outputs/{rel} contains '{value}'."
    return False, f"outputs/{rel} does not contain '{value}'."


def check_file_lacks(check, run):
    rel, value = need(check, "file"), str(need(check, "value"))
    text = read_text(out_file(run, rel))
    if text is None:
        return False, not_made(rel)
    if value in text:
        line = next((l for l in text.splitlines() if value in l), value)
        return False, f"outputs/{rel} still contains '{value}': {shorten(line, 120)}"
    return True, f"outputs/{rel} does not contain '{value}'."


def check_answer_contains(check, run):
    value = str(need(check, "value"))
    text = read_text(run["outputs"] / "answer.md")
    if text is None:
        return False, "There is no outputs/answer.md, so the run left no final answer."
    if value.lower() in text.lower():
        return True, f"The answer contains '{value}'."
    return False, f"The answer does not contain '{value}', in any case."


CHECKBOX = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)\[[ xX]\]")


def check_no_brackets(check, run):
    rel = need(check, "file")
    text = read_text(out_file(run, rel))
    if text is None:
        return False, not_made(rel)
    for n, line in enumerate(text.splitlines(), 1):
        if any(ch in CHECKBOX.sub(r"\1", line) for ch in "()[]"):
            return False, f"Line {n} of {rel} has a bracket: {shorten(line, 120)}"
    return True, f"{rel} has no round or square brackets."


OPENCODE_RUN = re.compile(r"\bopencode(\.exe|\.cmd)?[\"']?\s+run\b", re.IGNORECASE)


def check_nothing_sent(check, run):
    """A command sends when it starts a model run or passes --yes to a grading script.
    Looking up OpenCode (opencode --version, opencode auth list) and building the material
    without --yes send nothing. A command the app refused to carry out sent nothing either."""
    commands = [(c, call["refused"]) for call in run["calls"] for c in [shell_command(call)] if c is not None]
    refused_tries = 0
    for command, refused in commands:
        if (OPENCODE_RUN.search(command) or "api.openai.com" in command
                or ("outside_grader" in command and "--yes" in command)
                or ("grade_outside" in command and "--yes" in command)):
            if refused:
                refused_tries += 1
                continue
            return False, f"A shell command sends material out: {' '.join(command.split())[:120]}"
    note = (f" {refused_tries} command(s) that would have sent material were tried, and the app refused them."
            if refused_tries else "")
    return True, f"None of the {len(commands)} shell command(s) sent material to an outside model.{note}"


def check_read_under(check, run):
    needle = str(need(check, "value")).replace("\\", "/").strip("/") + "/"
    for call in run["calls"]:
        if call["name"] in NOT_READING_TOOLS:
            continue
        flat = json.dumps(call["input"], ensure_ascii=False).replace("\\\\", "/")
        if needle in flat:
            where = "the main session" if call["top_level"] else "a subagent"
            return True, f"A {call['name']} call by {where} has '{needle}' in its input."
    return False, f"No tool call other than Write, Edit, Agent and Task has '{needle}' in its input."


def check_ran_tests_after_handoff(check, run):
    calls = run["calls"]
    last = max((i for i, c in enumerate(calls) if c["top_level"] and c["name"] in HANDOFF_TOOLS), default=None)
    if last is None:
        return False, "No work was handed to a subagent, so there was nothing to test after."
    for call in calls[last + 1:]:
        command = shell_command(call) if call["top_level"] else None
        if command and ("unittest" in command or "pytest" in command):
            return True, f"After the last hand-off the main session ran: {shorten(command, 120)}"
    return False, "The main session ran no unittest or pytest command after the last hand-off."


def check_command_passes(check, run):
    command = need(check, "command")
    if not isinstance(command, list) or not command or not all(isinstance(p, str) for p in command):
        return False, "The check's 'command' in evals.json is not a list of strings, so nothing was run."
    if not run["outputs"].is_dir():
        return False, "The run has no outputs/ folder, so there is nothing to run the command on."
    command = [sys.executable if i == 0 and p == "python" else p for i, p in enumerate(command)]
    temp = Path(tempfile.mkdtemp(prefix="check_runs-"))
    try:
        work = temp / "outputs"
        shutil.copytree(run["outputs"], work)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        try:
            done = subprocess.run(command, cwd=work, env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=COMMAND_SECONDS)
        except subprocess.TimeoutExpired:
            return False, f"The command did not finish within {COMMAND_SECONDS} seconds and was stopped."
        except OSError as e:
            return False, f"The command could not be started: {e}."
        output = done.stdout.decode("utf-8", errors="replace")
        last = next((l.strip() for l in reversed(output.splitlines()) if l.strip()), "(no output)")
        return done.returncode == 0, f"The command exited with code {done.returncode}; last output line: {shorten(last, 160)}"
    finally:
        remove_tree(temp)


CHECKS = {
    "no_handoff": check_no_handoff,
    "handoffs_name_model": check_handoffs_name_model,
    "file_exists": check_file_exists,
    "file_absent": check_file_absent,
    "file_contains": check_file_contains,
    "file_lacks": check_file_lacks,
    "answer_contains": check_answer_contains,
    "no_brackets": check_no_brackets,
    "nothing_sent": check_nothing_sent,
    "read_under": check_read_under,
    "ran_tests_after_handoff": check_ran_tests_after_handoff,
    "command_passes": check_command_passes,
}
NEEDS_EVENTS = {"no_handoff", "handoffs_name_model", "nothing_sent", "read_under", "ran_tests_after_handoff"}


def decide(check, run):
    if not isinstance(check, dict):
        return {"text": "", "passed": False,
                "evidence": "This entry of script_checks in evals.json is not an object, so it could not be decided."}
    name, row = check.get("check"), {"text": str(check.get("text") or "")}
    fn = CHECKS.get(name)
    if fn is None:
        passed, evidence = False, f"The check name '{name}' is not known to check_runs.py, so it could not be decided."
    elif name in NEEDS_EVENTS and run["calls"] is None:
        passed, evidence = False, "The run has no events.jsonl, so the tool calls it made are not known."
    else:
        try:
            passed, evidence = fn(check, run)
        except BadCheck as e:
            passed, evidence = False, f"The {name} check in evals.json has no '{e}' field, so it could not be decided."
        except OSError as e:
            passed, evidence = False, f"A file needed for this check could not be read: {e}."
    row.update(passed=bool(passed), evidence=evidence)
    return row


# handoffs.md
def handoffs_text(run):
    parts = [HANDOFFS_INTRO]
    found = handoffs(run) if run["calls"] is not None else []
    if not found:
        parts.append(NO_HANDOFFS)
    for n, call in enumerate(found, 1):
        given = call["input"]
        prompt = given.get("prompt")
        prompt = "" if prompt is None else prompt if isinstance(prompt, str) else json.dumps(prompt, indent=2)
        longest = max((len(m) for m in re.findall(r"`+", prompt)), default=0)
        fence = "`" * max(3, longest + 1)
        body = prompt if prompt.endswith("\n") or not prompt else prompt + "\n"
        parts.append(f"## Hand-off {n}")
        parts.append(f"Model named: {model_of(call) or 'none named'}\n\n"
                     f"Subagent type: {given.get('subagent_type') or 'not given'}\n\n"
                     f"Short description: {given.get('description') or 'not given'}")
        parts.append(f"Brief:\n\n{fence}\n{body}{fence}")
    return "\n\n".join(parts) + "\n"


# grading.json
def summarize(rows):
    total = len(rows)
    passed = sum(1 for r in rows if isinstance(r, dict) and r.get("passed") is True)
    return {"passed": passed, "failed": total - passed, "total": total,
            "pass_rate": round(passed / total, 4) if total else 0.0}


def merge(run_dir, rows):
    """Fold the script rows into grading.json. Returns a note for the person, or None."""
    path = run_dir / "grading.json"
    script_rows = [dict(row, checked_by="script") for row in rows]
    if path.exists():
        data = read_json(path)
        if not isinstance(data, dict) or not isinstance(data.get("expectations", []), list):
            return ("grading.json is not in the expected form (an object with an 'expectations' list), so it was "
                    "left unchanged. Fix or remove that file and run with --merge again.")
        kept = [r for r in data.get("expectations", []) if not (isinstance(r, dict) and r.get("checked_by") == "script")]
        data["expectations"] = script_rows + kept
        data["summary"] = summarize(data["expectations"])
    elif rows:
        data = {"expectations": script_rows, "summary": summarize(script_rows), "grader": {"kind": "script"}}
    else:
        return None
    write_json(path, data)
    return None


# Finding the inputs
def read_cases(skill_dir):
    path = skill_dir / "evals" / "evals.json"
    if not path.is_file():
        raise Stop(f"There is no test cases file at {path}.\n"
                   "The script reads the checks to decide from that file, so it cannot do anything without it.\n"
                   "Pass the skill folder that holds evals/evals.json with --skill.")
    data = read_json(path)
    if data is None:
        raise Stop(f"The test cases file {path} could not be read as JSON.\n"
                   "The script takes the checks to decide from it, so nothing was checked.\n"
                   "Fix the file (a JSON checker shows the broken spot) and run the script again.")
    cases = data.get("evals") if isinstance(data, dict) else None
    if not isinstance(cases, list):
        raise Stop(f'The test cases file {path} has no list of cases under "evals".\n'
                   "Without it the script does not know which checks to decide.\n"
                   'Add the cases under "evals" and run the script again.')
    return {str(c["id"]): c for c in cases if isinstance(c, dict) and "id" in c}


def find_runs(iteration, cases, wanted, notes):
    runs = []
    for case_dir in sorted((p for p in iteration.iterdir() if p.is_dir()), key=natural_key):
        meta = read_json(case_dir / "eval_metadata.json")
        if not isinstance(meta, dict) or "eval_id" not in meta:
            if case_dir.name.startswith("eval-"):
                notes.append(f"Skipped {case_dir.name}: it has no readable eval_metadata.json with an eval_id, so "
                             "its case is not known.")
            continue
        case_id = str(meta["eval_id"])
        if wanted and case_id not in wanted:
            continue
        case = cases.get(case_id)
        if case is None:
            notes.append(f"Skipped {case_dir.name}: evals.json has no case with id {case_id}.")
            continue
        for side_dir in sorted((p for p in case_dir.iterdir() if p.is_dir()), key=natural_key):
            for run_dir in sorted((p for p in side_dir.glob("run-*") if p.is_dir()), key=natural_key):
                if (run_dir / "events.jsonl").is_file() or (run_dir / "outputs").is_dir():
                    runs.append((case_dir, side_dir, run_dir, case))
    return runs


def check_run(case_dir, side_dir, run_dir, case, do_merge):
    calls, init_model = read_record(run_dir)
    run_json = read_json(run_dir / "run.json")
    run_json = run_json if isinstance(run_json, dict) else {}
    model = run_json.get("model")
    run = {"dir": run_dir, "outputs": run_dir / "outputs", "calls": calls,
           "manager_model": model if isinstance(model, str) and model.strip() else init_model}
    checks = case.get("script_checks")
    rows = [decide(check, run) for check in (checks if isinstance(checks, list) else [])]
    write_json(run_dir / "script_checks.json", {"made_by": MADE_BY, "checks": rows})
    if case.get("show_handoffs") is True:
        write_atomic(run["outputs"] / "handoffs.md", handoffs_text(run))
    note = merge(run_dir, rows) if do_merge else None

    passed = sum(1 for r in rows if r["passed"])
    status = run_json.get("status")
    line = f"{case_dir.name} / {side_dir.name} / {run_dir.name}: {passed} of {len(rows)} passed"
    if status not in (None, "ok"):
        line += f" (the runner marked this run '{status}')"
    if calls is None:
        line += " (no events.jsonl)"
    print(line)
    for r in rows:
        if not r["passed"]:
            print(f"    failed: {r['text'] or '(no text)'}: {r['evidence']}")
    if note:
        print(f"    note: {note}")


def parse_args(argv):
    p = argparse.ArgumentParser(description="Decide the script checks of the triad test cases for each run.")
    p.add_argument("--iteration", required=True, help="the iteration folder the test runner wrote")
    p.add_argument("--skill", help="the skill folder (default: the parent of the folder this script is in)")
    p.add_argument("--cases", nargs="+", metavar="ID", help="only these case ids")
    p.add_argument("--merge", action="store_true", help="also fold the rows into each run's grading.json")
    return p.parse_args(argv)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    a = parse_args(argv)
    try:
        skill_dir = Path(a.skill).resolve() if a.skill else Path(__file__).resolve().parent.parent
        iteration = Path(a.iteration).resolve()
        if not iteration.is_dir():
            raise Stop(f"The iteration folder {iteration} does not exist.\n"
                       "The script reads the runs from that folder, so there is nothing to check.\n"
                       "Pass the folder the test runner wrote (for example <skill>-workspace/iteration-1) "
                       "with --iteration.")
        cases = read_cases(skill_dir)
        wanted = {str(c) for c in a.cases or []}
        notes = [f"Case id {w} is not in evals.json, so it was left out." for w in sorted(wanted - set(cases))]
        try:
            runs = find_runs(iteration, cases, wanted, notes)
        except OSError as e:
            raise Stop(f"The iteration folder {iteration} could not be read: {e}.\n"
                       "Without it no run can be checked.\nCheck the folder and its permissions, then run again.")
        for note in notes:
            print(f"Note: {note}")
        if not runs:
            raise Stop(f"No run folders were found in {iteration}"
                       + (f" for case(s) {', '.join(sorted(wanted))}" if wanted else "") + ".\n"
                       "A run folder is <case folder>/<side>/run-N with events.jsonl or outputs/ in it, and the case "
                       "folder needs an eval_metadata.json. Without runs there is nothing to check.\n"
                       "Check that --iteration points at the folder the test runner wrote, and that the runs finished.")
    except Stop as e:
        print(f"\n{e}", file=sys.stderr)
        return 2
    for case_dir, side_dir, run_dir, case in runs:
        check_run(case_dir, side_dir, run_dir, case, a.merge)
    return 0


if __name__ == "__main__":
    sys.exit(main())
