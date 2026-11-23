#!/usr/bin/env python3
"""Answer a skill's test cases through an app's command line.

Each case is answered with the skill installed in the run's own project folder
and without it (or with an older copy, --compare-with), in the layout that
scripts/aggregate_benchmark.py and eval-viewer/generate_review.py read:
<workspace>/iteration-N/eval-<id>-<slug>/<arm>/run-<k>/. Starting the same
command again skips runs that already finished. Standard library only.
"""
import argparse, collections, concurrent.futures, hashlib, json, os, re, shutil, stat, subprocess, sys, threading, time, types
from datetime import datetime, timezone
from pathlib import Path

MAKE_SKILL_DIR = Path(__file__).resolve().parents[2]
LEAVE_OUT_OF_COPY = {"evals", "__pycache__", ".git"}
SETUP_TIMEOUT = 300  # seconds for a case's own preparation script
CASES_EXAMPLE = ('{"skill_name": "my-skill", "evals": [\n'
                 '  {"id": 1, "prompt": "What the user asks", "expectations": ["What a good answer does"]}\n'
                 ']}')
LINES_ARM = "without_skill_plus_lines"
NO_SKILL_ARMS = ("without_skill", LINES_ARM)


class Stop(Exception):
    """An expected problem. The message is written for a person."""


# The app-specific part. Another app gets its own class with the same methods.
class ClaudeApp:
    name = "claude"
    env_var = "MAKE_SKILL_CLAUDE_PROGRAM"

    def find_program(self, given):
        if given:
            if Path(given).is_file():
                return str(Path(given).resolve())
            if shutil.which(given):
                return shutil.which(given)
            raise Stop(f"The program given with --program does not exist: {given}\n"
                       "Check the path, or leave out --program so the script looks for claude itself.")
        env = os.environ.get(self.env_var)
        if env:
            if Path(env).is_file():
                return str(Path(env).resolve())
            raise Stop(f"The environment variable {self.env_var} points to {env}, but there is no file there.\n"
                       "Fix or clear that variable, or name the program with --program PATH.")
        looked = [f"the environment variable {self.env_var} (not set)", "a program called claude on the PATH"]
        if shutil.which("claude"):
            return shutil.which("claude")
        if os.name == "nt":
            # The desktop app keeps its own copy. Seen from inside the app that is under APPDATA; seen from
            # the user's own shell it is in the app's private folder under LOCALAPPDATA\Packages. App version
            # 6.28899 (November 2026) moved it to LOCALAPPDATA\Claude-Data\claude_<id>.
            bases = []
            if os.environ.get("LOCALAPPDATA"):
                bases += [p / "claude-code"
                          for p in sorted((Path(os.environ["LOCALAPPDATA"]) / "Claude-Data").glob("claude_*"))]
            if os.environ.get("APPDATA"):
                bases.append(Path(os.environ["APPDATA"]) / "Claude" / "claude-code")
            if os.environ.get("LOCALAPPDATA"):
                bases += [p / "LocalCache" / "Roaming" / "Claude" / "claude-code"
                          for p in sorted((Path(os.environ["LOCALAPPDATA"]) / "Packages").glob("Claude_*"))]
            for base in bases:
                looked.append(f"the copy bundled with the Claude desktop app, under {base}")
                found = sorted(base.glob("*/*/claude.exe"),
                               key=lambda p: (version_key(p.parent.parent.name), p.stat().st_mtime))
                if found:
                    return str(found[-1])
        raise Stop("Could not find the claude program, which answers the test cases. Looked at:\n  - "
                   + "\n  - ".join(looked)
                   + f"\nInstall Claude Code, or point at the program with --program PATH (or set {self.env_var}).")

    def command(self, program, args):
        cmd = [sys.executable, program] if program.lower().endswith(".py") else [program]
        cmd += ["-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence",
                "--permission-mode", args.permission_mode]
        if not args.keep_user_setup:
            cmd += ["--setting-sources", "project"]
        for flag, value in (("--model", args.model), ("--allowedTools", args.allow_tools),
                            ("--max-budget-usd", args.max_cost_per_run)):
            if value not in (None, ""):
                cmd += [flag, str(value)]
        return cmd

    def read_events(self, text, skill_name):
        info = {"model": None, "skills": [], "got_result": False, "is_error": False, "result": "",
                "duration_ms": None, "cost_usd": None, "num_turns": None, "tokens": 0,
                "denials": [], "used": False, "transcript": []}
        for line in text.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            kind = ev.get("type")
            if kind == "system" and ev.get("subtype") == "init":
                info["model"] = ev.get("model")
                info["skills"] = [s if isinstance(s, str) else str(s.get("name", s)) for s in ev.get("skills") or []]
            elif kind == "assistant":
                for part in (ev.get("message") or {}).get("content") or []:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "text" and part.get("text", "").strip():
                        info["transcript"].append(part["text"].strip())
                    elif part.get("type") == "tool_use":
                        tool, raw = part.get("name", "?"), json.dumps(part.get("input", {}), ensure_ascii=False)
                        info["transcript"].append(f"- Tool call `{tool}`: {shorten(raw, 200)}")
                        # Best guess, not yet checked against a signed-in run: the skill counts
                        # as used when the Skill tool is called with its name, or its SKILL.md is read.
                        flat = raw.replace("\\\\", "/")
                        if (tool == "Skill" and skill_name in raw) or \
                                (tool == "Read" and f"skills/{skill_name}/SKILL.md" in flat):
                            info["used"] = True
            elif kind == "result":
                usage = ev.get("usage") or {}
                info.update(got_result=True, is_error=bool(ev.get("is_error")), result=str(ev.get("result") or ""),
                            duration_ms=ev.get("duration_ms"), cost_usd=ev.get("total_cost_usd"),
                            num_turns=ev.get("num_turns"),
                            denials=[d.get("tool_name", "?") for d in ev.get("permission_denials") or []],
                            tokens=sum(int(usage.get(k) or 0) for k in (
                                "input_tokens", "output_tokens",
                                "cache_creation_input_tokens", "cache_read_input_tokens")))
        info["listed"] = skill_name in info["skills"]
        return info

    def not_signed_in(self, info):
        return info["is_error"] and ("not logged in" in info["result"].lower() or "/login" in info["result"])

    def sign_in_step(self, program):
        return f'open a terminal and run "{program}" auth login'


APPS = {"claude": ClaudeApp}


# Small helpers
def version_key(text):
    return tuple(int(n) for n in re.findall(r"\d+", text))


def shorten(text, limit):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_atomic(path, data):
    """Write to a temporary name, then rename, so a stop never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    os.replace(tmp, path)


def write_json(path, obj):
    # ASCII only, so Anthropic's readers (which use the default encoding) can always read it.
    write_atomic(path, json.dumps(obj, indent=2) + "\n")


def remove_tree(path):
    def make_writable(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if path.exists():
        # The handler's name changed in Python 3.12; both forms call it with three arguments.
        shutil.rmtree(path, **{"onexc" if sys.version_info >= (3, 12) else "onerror": make_writable})


def file_hashes(folder):
    out = {}
    for p in folder.rglob("*"):
        rel = p.relative_to(folder).as_posix()
        if p.is_file() and not (rel == ".claude" or rel.startswith(".claude/")):
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def slugify(text):
    words = re.sub(r"[\W_]+", " ", text.lower()).split()
    slug = ""
    for w in words:
        if len(slug) + len(w) + (1 if slug else 0) > 40:
            break
        slug = f"{slug}-{w}" if slug else w
    return slug or (words[0][:40] if words else "case")


def kill_tree(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


# Reading the inputs
def read_skill(folder, option):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise Stop(f"The skill folder given with {option} does not exist: {folder}\n"
                   "Pass the folder that holds the skill's SKILL.md.")
    md = folder / "SKILL.md"
    if not md.is_file():
        raise Stop(f"There is no SKILL.md in {folder}.\nThe app finds a skill by that file, so there is "
                   f"nothing to test. Pass the folder that holds SKILL.md with {option}.")
    lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        raise Stop(f"{md} does not start with a header between two --- lines.\nThe app reads the skill's name "
                   "and description from that header and will not list the skill without it. Add it, e.g.\n"
                   "---\nname: my-skill\ndescription: What the skill does and when to use it.\n---")
    end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
    if end is None:
        raise Stop(f"{md} opens its header with --- on the first line but never closes it with a second --- line.\n"
                   "The app cannot read the skill's name and description. Add the closing --- line.")
    for line in lines[1:end]:
        m = re.match(r"\s*name\s*:\s*(.+?)\s*$", line)
        if m:
            return folder, m.group(1).strip("'\"")
    print(f"Note: {md} has no name: line in its header; using the folder name {folder.name}.")
    return folder, folder.name


def read_cases(path, skill_dir, wanted):
    if not path.is_file():
        raise Stop(f"No test cases file at {path}.\nThe runner needs it to know what to ask. "
                   f"Create it in this format:\n{CASES_EXAMPLE}\nor point at another file with --cases-file PATH.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        raise Stop(f"The test cases file {path} is not valid JSON: {e}.\nFix that spot and start again.")
    cases = data.get("evals") if isinstance(data, dict) else None
    if not isinstance(cases, list) or not cases:
        raise Stop(f'The test cases file {path} has no list of cases under "evals".\n'
                   f"Without cases there is nothing to run. The format is:\n{CASES_EXAMPLE}")
    seen = set()
    for n, case in enumerate(cases, 1):
        where = f'Case number {n} in "evals" of {path}'
        if not isinstance(case, dict) or "id" not in case:
            raise Stop(f'{where} has no "id". Each case needs a unique id, used in its folder name. Add one.')
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            raise Stop(f'{where} (id {case["id"]}) has no "prompt" text, so there is nothing to ask. Add one.')
        if str(case["id"]) in seen:
            raise Stop(f'{where} repeats the id {case["id"]}. Two cases would share one folder. Give each its own id.')
        seen.add(str(case["id"]))
        setup = case.get("setup")
        if setup is not None:
            sp = Path(setup) if isinstance(setup, str) and setup.strip() else None
            if sp is None or sp.is_absolute() or ".." in sp.parts or not (skill_dir / sp).is_file():
                raise Stop(f'{where} (id {case["id"]}) has "setup": {json.dumps(setup)}, which is not a file inside '
                           "the skill folder.\nThat script is run in each run's folder before the app starts, to "
                           'prepare what copied files cannot. Give a path relative to the skill folder, or remove '
                           '"setup".')
        root = case.get("files_root")
        if root is not None:
            rp = Path(root) if isinstance(root, str) and root.strip() else None
            if rp is None or rp.is_absolute() or ".." in rp.parts or not (skill_dir / rp).is_dir():
                raise Stop(f'{where} (id {case["id"]}) has "files_root": {json.dumps(root)}, which is not a folder '
                           "inside the skill folder.\nThe case's files are copied into the run's folder with that "
                           'part of their path left off. Give a folder relative to the skill folder, or remove '
                           '"files_root".')
        for rel in case.get("files") or []:
            p = Path(rel)
            if p.is_absolute() or ".." in p.parts:
                raise Stop(f'{where} (id {case["id"]}) lists the file "{rel}". Files must be given relative to '
                           f"the skill folder, without .., so they can be copied into the run's folder.")
            if not (skill_dir / p).is_file():
                raise Stop(f'{where} (id {case["id"]}) lists the file "{rel}", but {skill_dir / p} does not exist.\n'
                           "The run would miss its input. Add the file or remove it from the case.")
            if root is not None and Path(root) not in p.parents:
                raise Stop(f'{where} (id {case["id"]}) lists the file "{rel}", which is not inside its '
                           f'"files_root" {json.dumps(root)}.\nThe runner would not know where to put it in the '
                           'run\'s folder. Move the file under that folder, or remove "files_root".')
    if wanted:
        unknown = [w for w in wanted if w not in seen]
        if unknown:
            raise Stop(f"No case with id {', '.join(unknown)} in {path}. The ids there are: {', '.join(sorted(seen))}.")
        cases = [c for c in cases if str(c["id"]) in wanted]
    return cases


def read_instruction_lines(given):
    path = Path(given).resolve()
    if not path.is_file():
        raise Stop(f"There is no file at {path}, given with --instruction-lines.\nThat file should hold the few "
                   "lines for CLAUDE.md that are tested against the skill. Check the path, or leave out "
                   "--instruction-lines.")
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        raise Stop(f"The file given with --instruction-lines could not be read as UTF-8 text: {path} ({e}).\n"
                   "Its text is written into CLAUDE.md for the runs, so it must be plain text. "
                   "Save it as UTF-8 and start again.")
    if not text.strip():
        raise Stop(f"The file given with --instruction-lines is empty or holds only blank lines: {path}.\n"
                   "Runs with an empty CLAUDE.md would be the same as the runs without the skill and would show "
                   "nothing. Write the lines into the file, or leave out --instruction-lines.")
    return path, text


def place_in_run(case, rel):
    """Where a case file lands in the run's folder: its path, with the case's files_root left off."""
    root = case.get("files_root")
    return Path(rel).relative_to(root) if root else Path(rel)


def check_no_claude_md(cases):
    for case in cases:
        for rel in case.get("files") or []:
            if place_in_run(case, rel).as_posix().lower() == "claude.md":
                raise Stop(f'Case {case["id"]} lists the file "{rel}", which is copied to CLAUDE.md at the top of '
                           "the run's folder. --instruction-lines writes its own CLAUDE.md there, so one would "
                           "overwrite the other.\nRename that file in the case (and in the skill folder), or leave "
                           "out --instruction-lines.")


def instruction_file_above(workspace):
    """The first instruction file in the workspace folder or a folder above it, or None.

    The user's own ~/.claude/CLAUDE.md counts. Claude Code reads it as the instruction file of the home folder
    for every project under that folder, even when the user's settings are left out (seen with 2.1.330)."""
    for folder in [workspace, *workspace.parents]:
        for name in ("CLAUDE.md", ".claude/CLAUDE.md"):
            if (folder / name).is_file():
                return folder / name
    return None


def users_own_instruction_file():
    return Path.home() / ".claude" / "CLAUDE.md"


def pick_iteration(workspace, given):
    if given is not None:
        print(f"Using iteration-{given} in {workspace}.")
        return given
    found = [int(m.group(1)) for p in (workspace.glob("iteration-*") if workspace.is_dir() else [])
             if (m := re.fullmatch(r"iteration-(\d+)", p.name)) and p.is_dir()]
    if found:
        print(f"Using iteration-{max(found)} in {workspace}, the highest one there "
              f"(pass --iteration {max(found) + 1} to start a new one).")
        return max(found)
    print(f"Using iteration-1 in {workspace} (new).")
    return 1


# One run
class Job:
    def __init__(self, case, case_dir, arm, k, install, install_name, lines_file=None):
        self.case, self.case_dir, self.arm, self.k = case, case_dir, arm, k
        self.install, self.install_name, self.lines_file = install, install_name, lines_file
        self.run_dir = case_dir / arm / f"run-{k}"
        self.label = f"case {case['id']}, {arm}, run {k}"


def copy_skill(src, dest, workspace):
    def leave_out(folder, names):
        return [n for n in names if (n in LEAVE_OUT_OF_COPY or n.endswith("-workspace")
                                     or (Path(folder) / n).resolve() == workspace)
                and (Path(folder) / n).is_dir()]
    shutil.copytree(src, dest, ignore=leave_out)


def run_setup(job, ctx, work):
    """Runs the case's own preparation script in the run's folder. Returns None, or what went wrong."""
    script = ctx.skill_dir / job.case["setup"]
    env = {**os.environ, "MAKE_SKILL_CASE": str(job.case["id"]), "MAKE_SKILL_ARM": job.arm,
           "MAKE_SKILL_RUN": str(job.k), "MAKE_SKILL_RUN_DIR": str(job.run_dir)}
    try:
        done = subprocess.run([sys.executable, str(script)], cwd=work, env=env, capture_output=True,
                              timeout=SETUP_TIMEOUT)
    except subprocess.TimeoutExpired:
        return (f"The case's preparation script {script} took longer than {SETUP_TIMEOUT} seconds and was stopped, "
                "so the app was not started for this run. Run the script by hand in an empty folder to see where "
                "it hangs.")
    except OSError as e:
        return f"The case's preparation script {script} could not be started ({e}), so the app was not started."
    write_atomic(job.run_dir / "setup.txt", done.stdout + done.stderr)
    if done.returncode != 0:
        return (f"The case's preparation script {script} ended with exit code {done.returncode}, so the app was not "
                f"started for this run. What the script printed is in {job.run_dir / 'setup.txt'}. Fix the cause "
                "and start again; finished runs are skipped.")
    return None


def do_run(job, ctx):
    if ctx.stop.is_set():
        return {"status": "not started", "started": False}
    a, app, run_dir = ctx.args, ctx.app, job.run_dir
    remove_tree(run_dir)  # a failed or half-written earlier attempt starts clean
    work = run_dir / "work"
    work.mkdir(parents=True)
    for rel in job.case.get("files") or []:
        dest = work / place_in_run(job.case, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ctx.skill_dir / rel, dest)
    if job.lines_file:
        (work / "CLAUDE.md").write_bytes(ctx.lines_text.encode("utf-8"))
    if job.install:
        copy_skill(job.install, work / ".claude" / "skills" / job.install_name, ctx.workspace)
    by_name = bool(a.load_by_name and job.install)
    prompt = f"/{job.install_name} {job.case['prompt']}" if by_name else job.case["prompt"]
    if job.case.get("setup"):
        reason = run_setup(job, ctx, work)
        if reason:
            write_json(run_dir / "run.json", {"status": "failed", "reason": reason, "arm": job.arm,
                                              "run_number": job.k, "started": now_iso(), "finished": now_iso()})
            return {"status": "failed", "reason": reason, "started": False}
    before = file_hashes(work)
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("CLAUDECODE", "PWD")}
    started, t0, timed_out = now_iso(), time.monotonic(), False
    try:
        proc = subprocess.Popen(ctx.command, cwd=work, env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        reason = f"Could not start the program {ctx.program}: {e}."
        write_json(run_dir / "run.json", {"status": "failed", "reason": reason, "arm": job.arm,
                                          "run_number": job.k, "started": started, "finished": now_iso()})
        return {"status": "failed", "reason": reason, "started": False}
    try:
        out, err = proc.communicate(prompt.encode("utf-8"), timeout=a.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            out, err = b"", b""
    wall_ms = int((time.monotonic() - t0) * 1000)
    info = app.read_events(out.decode("utf-8", errors="replace"), job.install_name or ctx.skill_name)

    status, reason, signed_out = "failed", None, False
    if timed_out:
        reason = (f"The run took longer than the limit of {a.timeout} seconds and was stopped. "
                  "If the task needs more time, raise --timeout.")
    elif app.not_signed_in(info):
        signed_out = True
        reason = "The program is not signed in, so it could not answer."
    elif not info["got_result"]:
        reason = (f"The program ended (exit code {proc.returncode}) without a final answer. "
                  f"Its error output starts: {shorten(err.decode('utf-8', 'replace'), 300) or '(empty)'}")
    elif info["is_error"]:
        reason = f"The app reported an error: {info['result'][:300]}"
    elif job.install and not info["listed"]:
        reason = (f"The app did not see the skill {job.install_name} (it was not in the app's list of skills), "
                  "so this answer says nothing about the skill. Check the header of its SKILL.md.")
    else:
        status = "ok"

    write_atomic(run_dir / "events.jsonl", out)
    if err.strip():
        write_atomic(run_dir / "stderr.txt", err)
    after = file_hashes(work)
    for rel, digest in sorted(after.items()):
        if before.get(rel) != digest:
            write_atomic(run_dir / "outputs" / rel, (work / rel).read_bytes())
    write_atomic(run_dir / "outputs" / "answer.md", info["result"] + "\n")
    transcript = [f"# {job.label}", "## Eval Prompt", job.case["prompt"].strip(), "## What happened",
                  *info["transcript"], "## Final answer", info["result"] or "(none)"]
    write_atomic(run_dir / "transcript.md", "\n\n".join(transcript) + "\n")
    duration_ms = info["duration_ms"] if isinstance(info["duration_ms"], (int, float)) else wall_ms
    timing = {"total_tokens": info["tokens"], "duration_ms": duration_ms,
              "total_duration_seconds": round(duration_ms / 1000, 1), "cost_usd": info["cost_usd"]}
    write_json(run_dir / "timing.json", timing)
    write_json(run_dir / "eval_metadata.json", ctx.metadata[str(job.case["id"])])
    record = {"status": status, "reason": reason, "arm": job.arm, "run_number": job.k, "app": app.name,
              "program": ctx.program, "model": info["model"], "command": ctx.command,
              "skill_listed": info["listed"], "skill_used": info["used"], "num_turns": info["num_turns"],
              "permission_denials": info["denials"], "started": started, "finished": now_iso()}
    if job.lines_file:
        record["instruction_lines_file"] = str(job.lines_file)
    if by_name:
        record["loaded_by_name"] = True
    if job.arm in NO_SKILL_ARMS:
        record["clean_comparison"] = not info["listed"]
    write_json(run_dir / "run.json", record)
    if status == "ok" and not a.keep_work:
        remove_tree(work)
    if signed_out:
        ctx.signed_out = True
        ctx.stop.set()
    return {**record, **timing, "started": True}


def read_json_file(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def earlier_result(job):
    """The saved result if this run already finished well, else None (so it is done again)."""
    rec = read_json_file(job.run_dir / "run.json")
    if rec.get("status") != "ok":
        return None
    return {**rec, **read_json_file(job.run_dir / "timing.json"), "status": "ok (earlier)", "started": False}


# Main
def parse_args(argv):
    p = argparse.ArgumentParser(description="Answer a skill's test cases with and without the skill, "
                                            "through an app's command line.")
    p.add_argument("--skill", required=True, help="folder that holds the skill's SKILL.md")
    p.add_argument("--cases-file", help="test cases (default: <skill>/evals/evals.json)")
    p.add_argument("--workspace", help="where results go (default: <skill-name>-workspace next to the skill)")
    p.add_argument("--iteration", type=int, help="iteration number (default: the highest existing, or 1)")
    p.add_argument("--compare-with", help="an older copy of the skill to compare against instead of no skill")
    p.add_argument("--instruction-lines", metavar="FILE",
                   help=f"also answer each case without the skill but with this file's text as CLAUDE.md "
                        f"(side {LINES_ARM})")
    p.add_argument("--load-by-name", action="store_true",
                   help="in runs with the skill, put /<skill name> in front of the prompt, the way a user loads "
                        "a skill by typing its name (for skills that are never picked by their description)")
    p.add_argument("--only-with-skill", action="store_true",
                   help="answer only with the skill, for a cheap look at how it behaves; there is then nothing "
                        "to compare against, so this cannot show whether the skill helps")
    p.add_argument("--runs", type=int, default=1, help="answers per case and arm (default 1)")
    p.add_argument("--cases", nargs="+", metavar="ID", help="only these case ids")
    p.add_argument("--parallel", type=int, default=2, help="runs at the same time (default 2)")
    p.add_argument("--timeout", type=float, default=900, help="seconds per run (default 900)")
    p.add_argument("--app", choices=sorted(APPS), default="claude", help="the app that answers")
    p.add_argument("--program", help="the app's program (default: looked up)")
    p.add_argument("--model", help="model name passed to the app")
    p.add_argument("--allow-tools", help='tools the runs may use without asking, e.g. "Bash,Write"')
    p.add_argument("--permission-mode", default="acceptEdits", help="passed to the app (default acceptEdits)")
    p.add_argument("--max-cost-per-run", type=float, metavar="USD", help="spending limit per run")
    p.add_argument("--keep-user-setup", action="store_true",
                   help="let runs see your own skills and settings (by default they are hidden)")
    p.add_argument("--dry-run", action="store_true", help="print what would run; create nothing")
    p.add_argument("--redo", action="store_true", help="run again runs that already finished")
    p.add_argument("--keep-work", action="store_true", help="keep each run's work folder")
    return p.parse_args(argv)


def prepare(a):
    ctx = types.SimpleNamespace()
    ctx.args, ctx.app = a, APPS[a.app]()
    ctx.skill_dir, ctx.skill_name = read_skill(a.skill, "--skill")
    old = read_skill(a.compare_with, "--compare-with") if a.compare_with else None
    ctx.lines_file, ctx.lines_text = read_instruction_lines(a.instruction_lines) if a.instruction_lines else (None, None)
    cases_file = Path(a.cases_file).resolve() if a.cases_file else ctx.skill_dir / "evals" / "evals.json"
    cases = read_cases(cases_file, ctx.skill_dir, [str(c) for c in a.cases or []])
    if ctx.lines_file:
        check_no_claude_md(cases)
    ctx.workspace = (Path(a.workspace) if a.workspace else
                     ctx.skill_dir.parent / f"{ctx.skill_name}-workspace").resolve()
    above = instruction_file_above(ctx.workspace)
    if above and above == users_own_instruction_file() and not a.keep_user_setup:
        home = Path.home()
        raise Stop(f"I can't start the runs with the workspace {ctx.workspace}. It is inside your home folder "
                   f"{home}, and Claude Code reads your own instruction file {above} for every project under that "
                   "folder, even with your settings left out. Every run, with and without the skill, would follow "
                   "your personal instructions, and their wording can turn up in answers that are later sent to an "
                   "outside grader. Nothing was started.\n"
                   f"Pass --workspace with a folder outside {home}, for example "
                   f"{Path(home.anchor) / 'make-skill-runs' / ctx.skill_name}. The temporary folder will not do "
                   "where it lies inside the home folder, as it does on Windows.\n"
                   "If the runs are meant to see your own setup, add --keep-user-setup.")
    if above:
        print(f"Note: the workspace {ctx.workspace} sits under a folder with its own instruction file ({above}). "
              "Claude Code also reads the instruction files of the folders above a project, so every run, with "
              "and without the skill, would follow those instructions too, and the comparison would say less "
              "about the skill.\nTo avoid that, pass --workspace with a folder that is outside any project "
              "and outside your home folder.\n")
    ctx.iteration = pick_iteration(ctx.workspace, a.iteration)
    ctx.program = ctx.app.find_program(a.program)
    print(f"Program: {ctx.program}")
    ctx.command = ctx.app.command(ctx.program, a)
    iteration_dir = ctx.workspace / f"iteration-{ctx.iteration}"
    arms = [("with_skill", ctx.skill_dir, ctx.skill_name, None),
            ("old_skill", old[0], old[1], None) if old else ("without_skill", None, None, None)]
    if ctx.lines_file:
        arms.append((LINES_ARM, None, None, ctx.lines_file))
    if a.only_with_skill:
        arms = arms[:1]
    ctx.jobs, ctx.metadata, ctx.case_dirs = [], {}, {}
    for case in cases:
        slug = slugify(str(case.get("name") or case["prompt"]))
        case_dir = iteration_dir / f"eval-{case['id']}-{slug}"
        ctx.case_dirs[case_dir] = str(case["id"])
        ctx.metadata[str(case["id"])] = {"eval_id": case["id"], "eval_name": slug, "prompt": case["prompt"],
                                         "assertions": case.get("expectations") or case.get("assertions") or []}
        for k in range(1, a.runs + 1):
            for arm, install, name, lines_file in arms:
                ctx.jobs.append(Job(case, case_dir, arm, k, install, name, lines_file))
    ctx.stop, ctx.signed_out, ctx.iteration_dir = threading.Event(), False, iteration_dir
    return ctx


def summary(ctx, results):
    rows = [("case", "arm", "run", "status", "seconds", "tokens", "cost", "skill listed", "skill used")]
    for job, r in results:
        cost = r.get("cost_usd")
        rows.append((str(job.case["id"]), job.arm, str(job.k), r["status"],
                     f"{r['total_duration_seconds']:.1f}" if "total_duration_seconds" in r else "-",
                     str(r.get("total_tokens", "-")), f"{cost:.4f}" if isinstance(cost, (int, float)) else "-",
                     {True: "yes", False: "no"}.get(r.get("skill_listed"), "-"),
                     {True: "yes", False: "no"}.get(r.get("skill_used"), "-") if job.arm not in NO_SKILL_ARMS else "-"))
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    print("\nAll runs:")
    for row in rows:
        print("  " + "  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip())

    notes = []
    failed = [(j, r) for j, r in results if r["status"] == "failed"]
    if failed and not ctx.signed_out:
        notes.append("These runs failed and will be done again the next time you start the same command:\n"
                     + "\n".join(f"  - {j.label} ({j.run_dir}): {r.get('reason')}" for j, r in failed))
    unclean = [j for j, r in results if j.arm in NO_SKILL_ARMS and r.get("skill_listed")]
    if unclean:
        notes.append(f"In {len(unclean)} run(s) without the skill, the app still listed a skill called "
                     f"{ctx.skill_name}. Another copy with that name is in your own setup, so those answers may "
                     "have used it and the comparison is not clean. Remove --keep-user-setup, or move the other "
                     "copy away while testing, then start again with --redo.")
    with_runs = [r for j, r in results if j.install and r["status"].startswith("ok")]
    unused = [r for r in with_runs if not r.get("skill_used") and not r.get("loaded_by_name")]
    if unused:
        notes.append(f"In {len(unused)} of {len(with_runs)} finished run(s) with the skill installed, the app listed "
                     "the skill but the model never opened it. That is a finding in itself: the skill's description "
                     "may not make the model reach for it. (This is read from the app's output and is a best guess.)")
    denied = collections.Counter(t for _, r in results for t in r.get("permission_denials") or [])
    if denied:
        notes.append("Some runs tried tools they were not allowed to use: "
                     + ", ".join(f"{t} ({n}x)" for t, n in sorted(denied.items()))
                     + ". Those answers may be worse for it. If you trust the skill, pass "
                     f'--allow-tools "{",".join(sorted(denied))}" and start again with --redo.')
    if ctx.signed_out:
        notes.append(f"The program is not signed in, so no test case can be answered and the remaining runs were "
                     f"not started. To fix it, {ctx.app.sign_in_step(ctx.program)}, then start the same command "
                     "again; runs already finished are kept.")
    for note in notes:
        print("\n" + note)
    if not ctx.signed_out:
        print(f"\nWhat next: grade the answers (a grading.json in each run folder), then from the make-skill "
              f"folder ({MAKE_SKILL_DIR}) run:\n  python -m scripts.aggregate_benchmark \"{ctx.iteration_dir}\" "
              f"--skill-name {ctx.skill_name}")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    a = parse_args(argv)
    if a.runs < 1 or a.parallel < 1 or a.timeout <= 0:
        print("--runs and --parallel must be 1 or more, and --timeout more than 0. Fix the value and start again.",
              file=sys.stderr)
        return 2
    try:
        ctx = prepare(a)
    except Stop as e:
        print(f"\n{e}", file=sys.stderr)
        return 2

    if a.dry_run:
        print("Dry run: nothing is created or started. The prompt would go in on standard input.")
        for job in ctx.jobs:
            skip = " (already finished, would be skipped)" if not a.redo and earlier_result(job) else ""
            print(f"\n{job.label}{skip}\n  folder:  {job.run_dir / 'work'}")
            if job.install:
                print(f"  skill:   {job.install} copied to .claude/skills/{job.install_name}")
            if job.lines_file:
                print(f"  lines:   {job.lines_file} written to CLAUDE.md")
            if job.case.get("setup"):
                print(f"  setup:   {ctx.skill_dir / job.case['setup']} run in that folder first")
            print(f"  command: {subprocess.list2cmdline(ctx.command)}")
        return 0

    for case_dir, case_id in ctx.case_dirs.items():
        write_json(case_dir / "eval_metadata.json", ctx.metadata[case_id])
    results = {} if a.redo else {job: r for job in ctx.jobs if (r := earlier_result(job))}
    todo = [job for job in ctx.jobs if job not in results]
    print(f"{len(ctx.jobs)} run(s) in total: {len(ctx.jobs) - len(todo)} finished earlier, {len(todo)} to do now.")
    lock = threading.Lock()

    def run_one(job):
        r = do_run(job, ctx)
        if r["status"] != "not started":
            with lock:
                line = f"Done: {job.label}: {r['status']}"
                if "total_duration_seconds" in r:
                    line += f", {r['total_duration_seconds']:.1f} s"
                print(line + (f". {r['reason']}" if r.get("reason") else ""), flush=True)
        return r

    with concurrent.futures.ThreadPoolExecutor(max_workers=a.parallel) as pool:
        for job, r in zip(todo, pool.map(run_one, todo)):
            results[job] = r
    ordered = [(job, results[job]) for job in ctx.jobs]
    summary(ctx, ordered)
    if ctx.signed_out or (todo and not any(results[j]["started"] for j in todo)):
        return 2
    return 0 if all(r["status"].startswith("ok") for _, r in ordered) else 1


if __name__ == "__main__":
    sys.exit(main())
