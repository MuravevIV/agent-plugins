#!/usr/bin/env python3
"""File skills into plugins, keep the plugin description files in step, and switch a plugin on in a project.

This repository is a local marketplace for Claude Code, GitHub Copilot and OpenAI Codex. Each plugin in plugins/
has two description files that must agree (plugin.json for Copilot and Codex, .claude-plugin/plugin.json for
Claude Code), and the two marketplace files at the top of the repository must list every plugin.

    python pack_skill.py new-plugin <name> --description "<text>" [--category <text>]
    python pack_skill.py add <skill folder> --plugin <name> [--untested] [--anyway] [--replace]
    python pack_skill.py check [--fix]
    python pack_skill.py enable <plugin> --project <folder> [--apps claude copilot codex]

Every command takes --repo <folder> (default: the repository this script sits in). Standard library only; it
starts no other program and uses no network.
Exit codes: 0 done, 1 problems found or left, 2 the command could not be carried out as given,
3 nothing was changed because a choice by the person is needed.
"""
import argparse, copy, json, os, re, shutil, stat, sys, tempfile, tomllib
from datetime import date
from pathlib import Path

SCRIPT = Path(__file__).resolve()
DEFAULT_REPO = SCRIPT.parents[1]
CLAUDE_MARKET = Path(".claude-plugin/marketplace.json")
CODEX_MARKET = Path(".agents/plugins/marketplace.json")
MARKETS = ((CLAUDE_MARKET, "Claude Code and Copilot"), (CODEX_MARKET, "Codex"))
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
HOUSE = Path("plugins/core/skills/make-skill/house")
SHARED_KEYS = ("name", "version", "description", "author")
DECISIONS = ("keep", "shrink", "drop", "untested")
WHY_NOT = {"shrink": "only part of the skill made a difference, so the rest should be cut and the skill tested again",
           "drop": "the skill made no clear difference compared with working without it"}
APPS = {"claude": "Claude Code", "copilot": "Copilot", "codex": "Codex"}
BY_NAME_PLUGIN = "protocol"  # house rule 8: the user loads every skill in this plugin by typing its name
# Every app shows the plugin's name in front of the skill's (protocol:triad), so a skill name that repeats it
# (protocol-triad) would read protocol:protocol-triad.
BY_NAME_PREFIX = "protocol-"
IMPLICIT_OFF = re.compile(r"^\s*allow_implicit_invocation:\s*false\s*(#.*)?$", re.MULTILINE)
NAME_OK = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
DECISION_LINE = re.compile(r"^- \*\*Decision:\*\*(.*)$", re.MULTILINE)
MISSING = "is missing"
AGAIN = "Repair it by hand and run the same command again."


class Stop(Exception):
    """An expected problem: the message for the person and the exit code."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def q(path):
    """A path as it can be pasted into a command line."""
    return f'"{path}"' if " " in str(path) else str(path)


def show(value):
    return json.dumps(value, ensure_ascii=False)


def load_json(path):
    """Return (object, None), or (None, why it cannot be used)."""
    if not path.is_file():
        return None, MISSING
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        return None, f"is not valid JSON ({e})"
    except OSError as e:
        return None, f"could not be read ({e.strerror or e})"
    return (data, None) if isinstance(data, dict) else (None, "does not hold a JSON object ({ ... })")


def dump(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_file(path, text):
    """Write through a temporary file next to the target, so a stop halfway never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def need_json(repo, relpath):
    data, why = load_json(repo / relpath)
    if why:
        raise Stop(2, f"{relpath.as_posix()} in {repo} {why}, and this command needs it. Nothing was changed. Check "
                      "that --repo points at the agent-plugins repository, or repair the file by hand.")
    return data


def check_name(name, what):
    if not NAME_OK.match(name):
        raise Stop(2, f'"{name}" cannot be used as a {what} name: it must be lowercase letters, digits and hyphens, '
                      f'starting with a letter or digit (for example "my-{what}"). Nothing was changed.')


def need_plugin(repo, name, why):
    check_name(name, "plugin")
    if not (repo / "plugins" / name).is_dir():
        have = ", ".join(sorted(p.name for p in (repo / "plugins").iterdir() if p.is_dir())) or "none yet"
        raise Stop(2, f'There is no plugin "{name}" in {repo / "plugins"} (plugins there: {have}), so {why}')
    return repo / "plugins" / name


def this_command(repo, rest):
    return f"python {q(SCRIPT)} {rest}" + ("" if repo == DEFAULT_REPO else f" --repo {q(repo)}")


def front_matter(path):
    """Top-level keys between the first two --- lines; indented lines under a key are joined to its value."""
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    marks = [i for i, line in enumerate(lines) if line.strip() == "---"][:2]
    if len(marks) < 2:
        return None
    meta, key = {}, None
    for line in lines[marks[0] + 1:marks[1]]:
        m = re.match(r"([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key, value = m[1], m[2].strip()
            meta[key] = "" if value in ("|", ">", "|-", ">-", "|+", ">+") else value.strip("\"'")
        elif key and line[:1] in (" ", "\t"):
            meta[key] = (meta[key] + " " + line.strip()).strip()
    return meta


def test_decision(skill_dir):
    """The decision in the newest (top) block of TEST-RESULT.md, or None when it is not filled in."""
    path = skill_dir / "TEST-RESULT.md"
    m = DECISION_LINE.search(path.read_text(encoding="utf-8-sig", errors="replace")) if path.is_file() else None
    word = re.match(r"\s*([A-Za-z]+)", m[1]) if m else None  # the template's "<keep | ..." has no word here
    return word[1].lower() if word and word[1].lower() in DECISIONS else None


def by_name_problems(skill_dir, rel):
    """For a skill the user loads by name: a name that repeats the plugin's, and what still lets an app open it on
    its own, as (problem, how to fix)."""
    out = []
    meta = front_matter(skill_dir / "SKILL.md") or {}
    name = meta.get("name") or skill_dir.name
    if name.startswith(BY_NAME_PREFIX) or name == BY_NAME_PLUGIN:
        short = name[len(BY_NAME_PREFIX):] or "<name>"
        out.append((f"the skill is named {name}, and the apps show the plugin's name in front of it, so the user "
                    f"would see {BY_NAME_PLUGIN}:{name} with the word twice",
                    f"give it the protocol's own name, for example {short}: rename the skill's folder and the name: "
                    "line in its SKILL.md"))
    if meta.get("disable-model-invocation", "").lower() != "true":
        out.append((f"{rel}/SKILL.md does not say disable-model-invocation: true, so Claude Code and Copilot show "
                    "its description to the model, which can then open the skill on its own",
                    "add that line between the --- lines at its top"))
    path = skill_dir / "agents" / "openai.yaml"
    text = path.read_text(encoding="utf-8-sig", errors="replace") if path.is_file() else None
    if text is None or not IMPLICIT_OFF.search(text):
        out.append((f"{rel}/agents/openai.yaml {'is missing' if text is None else 'does not switch it off'}, so "
                    "Codex can open the skill on its own",
                    'put the two lines "policy:" and "  allow_implicit_invocation: false" in that file'))
    return out


# ---- check ----

def kept_elsewhere(entry):
    """True for a marketplace entry that points at a plugin kept somewhere else: an npm package, another
    repository. Its source is a table whose kind is not "local". Such a plugin has no folder here."""
    src = entry.get("source") if isinstance(entry, dict) else None
    return isinstance(src, dict) and src.get("source") not in (None, "local")


def check_repo(repo, only=None, fix=False):
    """Check (and with fix, put right) the plugin files. Returns (problems left, things put right, skill lines)."""
    left, fixed, skills = [], [], []

    def found(text, how, done=None):
        """Record a problem. True means: put it right now (only when fixing and it can be fixed)."""
        if fix and done:
            fixed.append(f"{text}; {done}.")
            return True
        left.append(f"{text}; {how}.")
        return False

    markets, dirty = {}, set()
    for relpath, app in MARKETS:
        data, why = load_json(repo / relpath)
        if not why and not isinstance(data.setdefault("plugins", []), list):
            why = 'has a "plugins" value that is not a list'
        if why:
            found(f"{relpath.as_posix()} {why}, so {app} cannot see the plugins it should list",
                  "repair it by hand (git holds the last good copy), then run check again")
        else:
            markets[relpath] = data

    names = sorted(p.name for p in (repo / "plugins").iterdir() if p.is_dir())
    for name in [only] if only else names:
        folder, pj_rel = repo / "plugins" / name, f"plugins/{name}/plugin.json"
        cj, cj_rel = folder / ".claude-plugin" / "plugin.json", f"plugins/{name}/.claude-plugin/plugin.json"
        check_skills(folder, name, found, skills)
        meta, why = load_json(folder / "plugin.json")
        if why:
            found(f"{pj_rel} {why}, and it is the file the other plugin files are compared with",
                  "write it by hand in the shape of plugins/core/plugin.json")
            continue
        if meta.get("name") != name:
            found(f"{pj_rel} gives the name {show(meta.get('name'))} but its folder is called {name}, so the other "
                  f'files of this plugin were not compared with it', f'set "name" to "{name}" or rename the folder')
            continue
        lacking = [k for k in SHARED_KEYS if k not in meta]
        if lacking:
            found(f"{pj_rel} has no {' and no '.join(lacking)}", "add them by hand in the shape of plugins/core/plugin.json")
        want = {k: meta[k] for k in SHARED_KEYS if k in meta}

        cmeta, why = load_json(cj)
        if why == MISSING:
            if found(f"{cj_rel} is missing, so Claude Code cannot read this plugin",
                     "run check --fix to create it from plugin.json", "created it from plugin.json"):
                write_file(cj, dump(want))
        elif why:
            found(f"{cj_rel} {why}", "repair it by hand, or delete it and run check --fix to make it again from plugin.json")
        else:
            changed = False
            for k, v in want.items():
                said = f"{k} {show(cmeta[k])}" if k in cmeta else f"no {k}"
                if cmeta.get(k) != v and found(
                        f"{cj_rel} has {said} but {pj_rel} has {show(v)}, and the apps must see the same values",
                        "run check --fix to copy the value from plugin.json", "copied the value from plugin.json"):
                    cmeta[k], changed = v, True
            if changed:
                write_file(cj, dump(cmeta))

        path = f"./plugins/{name}"
        for relpath, app in MARKETS:
            data, mrel = markets.get(relpath), relpath.as_posix()
            entries = [e for e in data["plugins"] if isinstance(e, dict) and e.get("name") == name] if data else None
            if entries == []:
                new = ({"name": name, "source": path, "description": want.get("description", "")}
                       if relpath == CLAUDE_MARKET else codex_entry(name))
                if found(f"{mrel} does not list the plugin {name}, so {app} will not offer it",
                         "run check --fix to add it", "added it"):
                    data["plugins"].append(new)
                    dirty.add(relpath)
            if not entries:
                continue
            if len(entries) > 1:
                found(f"{mrel} lists the plugin {name} {len(entries)} times", "remove all but one entry by hand")
            entry, src = entries[0], entries[0].get("source")
            if relpath == CLAUDE_MARKET:
                expect = {"source": path, **({"description": want["description"]} if "description" in want else {})}
            else:
                expect = {"source": {**(src if isinstance(src, dict) else {}), "source": "local", "path": path}}
            for k, v in expect.items():
                if entry.get(k) != v and found(
                        f"{mrel} gives the plugin {name} the {k} {show(entry.get(k))} where {show(v)} is expected"
                        + (f" (as in {pj_rel})" if k == "description" else ""), "run check --fix to correct it",
                        "corrected it"):
                    entry[k] = v
                    dirty.add(relpath)

    for relpath, data in [] if only else markets.items():
        for e in data["plugins"]:
            n = e.get("name") if isinstance(e, dict) else None
            if n not in names and kept_elsewhere(e):
                # a pointer: the plugin's files live at its source, and nothing of it is checked here
                src = e["source"]
                where = " ".join(str(src[k]) for k in ("package", "repo", "url", "path") if src.get(k))
                skills.append(f"  {n}: kept elsewhere ({src['source']} {where}); only listed in {relpath.as_posix()}")
            elif n not in names:
                found(f"{relpath.as_posix()} lists a plugin {show(n)} that has no folder in plugins/",
                      "remove that entry by hand, or create the plugin with new-plugin")
    for relpath in dirty:
        write_file(repo / relpath, dump(markets[relpath]))
    return left, fixed, skills


def check_skills(folder, name, found, skills):
    sdir = folder / "skills"
    for d in sorted(p for p in sdir.iterdir() if p.is_dir()) if sdir.is_dir() else []:
        srel = f"plugins/{name}/skills/{d.name}/SKILL.md"
        meta = front_matter(d / "SKILL.md") if (d / "SKILL.md").is_file() else None
        if not (d / "SKILL.md").is_file():
            found(f"{srel} is missing, so the apps will not see this skill", "add it, or remove the folder")
        elif meta is None:
            found(f"{srel} has no front matter between two --- lines at its top", "add name and description there")
        else:
            if meta.get("name") != d.name:
                found(f"{srel} gives the name {show(meta.get('name'))} but its folder is called {d.name}",
                      f"set name to {d.name} in it or rename the folder")
            if not meta.get("description"):
                found(f"{srel} has no description, which the apps use to decide when to use the skill", "add one")
            if name == BY_NAME_PLUGIN:
                for text, how in by_name_problems(d, f"plugins/{name}/skills/{d.name}"):
                    found(text, how)
        skills.append(f"{name} / {d.name}: {test_decision(d) or 'no test result'}")


def report(result, what):
    left, fixed, skills = result
    for line in fixed:
        print(f"Fixed: {line}")
    for line in left:
        print(f"Problem: {line}")
    if skills:
        print("Skills and the decision of their last test:\n" + "\n".join(f"  {line}" for line in skills))
    if left:
        print(f"{len(left)} problem(s) remain in {what}. Each line starting with Problem: says how to put it right.")
        return 1
    print(f"Checked {what}: everything is in step{' now' if fixed else ''}.")
    return 0


def cmd_check(repo, args):
    return report(check_repo(repo, fix=args.fix), "the plugin and marketplace files")


# ---- new-plugin ----

def codex_entry(name, category="Productivity"):
    return {"name": name, "source": {"source": "local", "path": f"./plugins/{name}"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": category}


def cmd_new_plugin(repo, args):
    check_name(args.name, "plugin")
    folder, description = repo / "plugins" / args.name, args.description.strip()
    if folder.exists():
        raise Stop(2, f"The plugin folder {folder} already exists, so nothing was created. To check its files run "
                      f"check; to file a skill into it run add with --plugin {args.name}.")
    if not description:
        raise Stop(2, "The description is empty. The apps show it when they offer the plugin, so give one with "
                      '--description "<what the plugin is for>". Nothing was created.')
    claude, codex = need_json(repo, CLAUDE_MARKET), need_json(repo, CODEX_MARKET)
    for data, relpath in ((claude, CLAUDE_MARKET), (codex, CODEX_MARKET)):
        if not isinstance(data.setdefault("plugins", []), list):
            raise Stop(2, f'{relpath.as_posix()} has a "plugins" value that is not a list, so the new plugin cannot be '
                          "added to it. Repair it by hand (git holds the last good copy). Nothing was created.")
    owner = claude.get("owner")
    if not isinstance(owner, dict) or not owner.get("name"):
        raise Stop(2, f'{CLAUDE_MARKET.as_posix()} has no "owner" with a "name", which a new plugin takes as its author. '
                      'Add "owner": {"name": "<your name>"} to it and run the same command again. Nothing was created.')
    meta = {"$schema": SCHEMA, "name": args.name, "version": "0.1.0", "description": description, "author": owner}
    write_file(folder / "plugin.json", dump(meta))
    write_file(folder / ".claude-plugin" / "plugin.json", dump({k: meta[k] for k in SHARED_KEYS}))
    write_file(folder / "skills" / ".gitkeep", "")
    for data, new in ((claude, {"name": args.name, "source": f"./plugins/{args.name}", "description": description}),
                      (codex, codex_entry(args.name, args.category))):
        old = [e for e in data["plugins"] if isinstance(e, dict) and e.get("name") == args.name]
        if old:  # an entry left behind by an earlier plugin of that name is reused
            old[0].update(new)
        else:
            data["plugins"].append(new)
    write_file(repo / CLAUDE_MARKET, dump(claude))
    write_file(repo / CODEX_MARKET, dump(codex))
    print(f"Created the plugin {args.name} in {folder}: plugin.json, .claude-plugin/plugin.json and an empty skills "
          f"folder, and added it to {CLAUDE_MARKET.as_posix()} and {CODEX_MARKET.as_posix()}.\n"
          f"To file a skill into it: {this_command(repo, f'add <skill folder> --plugin {args.name}')}")
    return report(check_repo(repo, only=args.name), f"the plugin {args.name}")


# ---- add ----

def skip_junk(folder, names):
    return [n for n in names if n in ("__pycache__", ".git") or n.endswith(".pyc")
            or (n.endswith("-workspace") and os.path.isdir(os.path.join(folder, n)))]


def make_writable(func, path, exc):
    """Windows refuses to delete read-only files: clear the flag and try once more."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def copy_skill(src, target):
    """Copy into a temporary folder next to the target first, so a stop halfway leaves the old copy in place."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=target.parent, prefix=f".{target.name}-new-"))
    try:
        shutil.copytree(src, tmp / target.name, ignore=skip_junk)
        if target.exists():
            shutil.rmtree(target, onexc=make_writable)
        os.replace(tmp / target.name, target)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def write_untested(path, name):
    """Put an "untested" block on top of TEST-RESULT.md, below a single title, keeping older blocks."""
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if path.is_file() else []
    while lines and (not lines[0].strip() or lines[0].startswith("# Test result")):
        lines.pop(0)
    rest = "\n".join(lines).rstrip()
    write_file(path, f"# Test result: {name}\n\n## {date.today().isoformat()}\n\n"
                     "- **Decision:** untested (the user chose to skip the test)\n- **What was tested:** nothing\n"
                     "- **Not covered:** everything; nobody knows yet whether this skill helps\n"
                     + (f"\n{rest}\n" if rest else ""))


# Folders that hold a project's skills. The folder above one of them is the project the skill was taken from.
SKILL_HOMES = (".claude", ".agents", ".codex", ".opencode", ".github")
ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/](?![\\/])[^\s`\"'<>|)\]]+|/(?:home|Users)/[^\s`\"'<>|)\]]+)")
TEXT_ENDINGS = (".md", ".txt", ".yaml", ".yml", ".json", ".py", ".ps1", ".sh")


def local_facts(src):
    """What in a skill's text belongs to one machine or one project: absolute paths, and the name of the project
    folder the skill was taken from. Test records and test material are left out; they name such places rightly."""
    home = None
    for marker in SKILL_HOMES:
        if marker in src.parts and src.parts.index(marker) > 0:
            home = src.parts[src.parts.index(marker) - 1]
            break
    if home and home.lower() == Path.home().name.lower():
        home = None  # the user's own skills folder; the name above it is the user's, not a project's
    found = []
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if (not path.is_file() or path.suffix.lower() not in TEXT_ENDINGS or path.name == "TEST-RESULT.md"
                or any(part in ("evals", "__pycache__") or part.endswith("-workspace") for part in rel.parts)):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for hit in sorted(set(m.rstrip(".,;:") for m in ABSOLUTE_PATH.findall(text))):
            found.append(f"{rel.as_posix()}: the path {hit}")
        if home and re.search(rf"(?<![\w-]){re.escape(home)}(?![\w-])", text, re.IGNORECASE):
            found.append(f"{rel.as_posix()}: the name {home}, the project folder this skill was taken from")
    return found


def cmd_add(repo, args):
    src = Path(args.skill).resolve()
    if not (src / "SKILL.md").is_file():
        raise Stop(2, f"{src} {'has no SKILL.md' if src.is_dir() else 'does not exist'}, so there is no skill to file. "
                      "Give the folder that holds the skill's SKILL.md. Nothing was changed.")
    meta = front_matter(src / "SKILL.md") or {}
    name = meta.get("name", "")
    if not name or not meta.get("description"):
        raise Stop(2, f"{src / 'SKILL.md'} needs a name and a description between the first two --- lines at its top; "
                      "the apps use them to find the skill and to decide when to use it. Add them and run the same "
                      "command again. Nothing was changed.")
    check_name(name, "skill")
    plugin = need_plugin(repo, args.plugin, "the skill has nowhere to go. Nothing was changed. Create the plugin first "
                         "with\n  " + this_command(repo, f'new-plugin {args.plugin} --description "<what it is for>"')
                         + "\nor give the name of a plugin that exists.")
    target = plugin / "skills" / name
    if target == src or target in src.parents or src in target.parents:
        raise Stop(2, f"{src} is the filed copy itself, or holds it, so filing it would copy it onto itself. Give "
                      f"the folder you work on, outside {plugin / 'skills'}. Nothing was changed.")
    shown = by_name_problems(src, str(src)) if args.plugin == BY_NAME_PLUGIN else []
    if shown:
        raise Stop(2, f"I can't file the skill {name} into the plugin {BY_NAME_PLUGIN} yet. The skills in that plugin "
                      f"are picked by the user, by typing {BY_NAME_PLUGIN}:<name>, so each carries the protocol's "
                      "own name and no app may open it on its own. "
                      "Nothing was changed. Still to do:\n" + "\n".join(f"  - {t}; {how}." for t, how in shown)
                      + "\nThen run the same command again.")
    decision = test_decision(src)
    test_cmd = f"python {q(repo / HOUSE / 'scripts' / 'run_tests.py')} --skill {q(src)}"
    if decision in WHY_NOT and not args.anyway:
        raise Stop(3, f"I can't file the skill {name} into the plugin {args.plugin} without asking you first. Its last "
                      f'test decided "{decision}" (see {src / "TEST-RESULT.md"}): {WHY_NOT[decision]}. Filing it puts '
                      "it into every project that switches the plugin on. Nothing was changed. Two ways on:\n"
                      f"  1. Change the skill and test it again:\n       {test_cmd}\n"
                      "  2. File it as it is: run the same command again with --anyway added.")
    if decision is None and not args.untested:
        why = ("its folder has no TEST-RESULT.md" if not (src / "TEST-RESULT.md").is_file()
               else "its TEST-RESULT.md has no filled-in decision line")
        raise Stop(3, f"I can't file the skill {name} into the plugin {args.plugin} yet. It has never been tested "
                      f"({why}), so nobody knows whether it helps. Nothing was changed. Two ways on:\n"
                      f"  1. Test it now:\n       {test_cmd}\n"
                      f"     How the tests work is explained in {repo / HOUSE / 'testing.md'}.\n"
                      "  2. File it anyway, marked as untested: run the same command again with --untested added.")
    if target.exists() and not args.replace:
        raise Stop(3, f"The skill {name} is already filed in the plugin {args.plugin}, in {target}. Nothing was "
                      f"changed. To put the current version from {src} in its place, run the same command again "
                      "with --replace added.")
    replaced = target.exists()
    copy_skill(src, target)
    print(f"{'Replaced' if replaced else 'Filed'} the skill {name} in the plugin {args.plugin}: the copy is in {target}.")
    if decision is None:
        # the note goes into the copy only: the folder it was copied from may be someone else's and stays as it is
        write_untested(target / "TEST-RESULT.md", name)
        print(f"The copy is marked as untested in its TEST-RESULT.md: nobody knows yet whether the skill {name} "
              "helps. The folder you gave was not changed, so filing it again needs --untested again.")
    elif decision == "untested":
        print(f"The skill {name} is marked as untested in its TEST-RESULT.md: nobody knows yet whether it helps.")
    elif decision in WHY_NOT:
        print(f'Filed although its last test decided "{decision}": {WHY_NOT[decision]}.')
    print(f"The original in {src} is still there. You can delete it, or keep working in it and file it again "
          "with --replace.")
    facts = local_facts(src)
    if facts:
        print(f"Note: the skill's text holds {len(facts)} thing(s) that belong to one machine or one project:")
        for fact in facts[:12]:
            print(f"  - {fact}")
        if len(facts) > 12:
            print(f"  - and {len(facts) - 12} more")
        print("A skill in a plugin is used in other places too. For each of these, make it general, turn it into a "
              "setting, or say in the text whose fact it is. Nothing was stopped because of this.")
    return report(check_repo(repo, only=args.plugin), f"the plugin {args.plugin}")


# ---- enable ----

def enable_json(path, key, market=None, repo=None):
    """Merge the switch (and for Claude Code the marketplace) into a settings file; write only when it changes."""
    data, why = load_json(path) if path.exists() else ({}, None)
    if why:
        return False, [f"{path} {why}, so it was left unchanged. {AGAIN}"]
    before, notes = copy.deepcopy(data), []
    sections = [data.setdefault(k, {}) for k in ("enabledPlugins", "extraKnownMarketplaces")[:2 if market else 1]]
    if not all(isinstance(s, dict) for s in sections):
        return False, [f'{path}: "enabledPlugins" or "extraKnownMarketplaces" in it is not a JSON object, so it was '
                       f"left unchanged. {AGAIN}"]
    sections[0][key] = True
    did = f"switched on {key}"
    if market:
        want = {"source": {"source": "directory", "path": repo.as_posix()}}
        if sections[1].setdefault(market, want) != want:
            notes.append(f'It already names a marketplace "{market}" with another place, {show(sections[1][market])}. '
                         "That entry was left as it is, so Claude Code may take the plugin from there. To use this "
                         f"repository, change it to {show(want)} by hand.")
        else:
            did += f" and told Claude Code where the marketplace {market} is ({repo.as_posix()})"
    if data == before:
        return not notes, [f"{path} already switches the plugin on; nothing was written."] + notes
    write_file(path, dump(data))
    return not notes, [f"Wrote {path}: {did}."] + notes


def enable_codex(path, key):
    text = ""
    if path.is_file():
        with open(path, encoding="utf-8-sig", newline="") as f:  # keep the file's own line ends
            text = f.read()
    try:
        plugins = tomllib.loads(text).get("plugins", {})
    except tomllib.TOMLDecodeError as e:
        return False, [f"{path} is not valid TOML ({e}), so it was left unchanged. {AGAIN}"]
    if not isinstance(plugins, dict):
        return False, [f'{path} has a "plugins" value that is not a table, so it was left unchanged. {AGAIN}']
    header, table = f'[plugins."{key}"]', plugins.get(key)
    if table is None:
        nl = "\r\n" if "\r\n" in text else "\n"
        text += (nl if text and not text.endswith("\n") else "") + (nl if text.strip() else "")
        write_file(path, text + f"{header}{nl}enabled = true{nl}")
        return True, [f"Wrote {path}: added {header} with enabled = true."]
    if isinstance(table, dict) and table.get("enabled") is True:
        return True, [f"{path} already switches the plugin on; nothing was written."]
    return False, [f"{path} already has a part for {key} that does not switch it on, so it was left alone (it may "
                   f"have been switched off on purpose). To switch it on, {codex_line(text, key)}"]


def codex_line(text, key):
    """Say which line to change by hand: the enabled line under the table header, else the header."""
    lines = text.splitlines()
    head = re.compile(r"\s*\[\s*plugins\s*\.\s*([\"']?)" + re.escape(key) + r"\1\s*\]")
    for i, line in enumerate(lines):
        if head.match(line):
            for j in range(i + 1, len(lines)):
                if lines[j].lstrip().startswith("["):
                    break
                if re.match(r"\s*enabled\s*=", lines[j]):
                    return f"change line {j + 1} ({lines[j].strip()}) to enabled = true."
            return f"add the line enabled = true under line {i + 1} ({line.strip()})."
    return f'set enabled = true for "{key}" where the file sets up plugins.'


def cmd_enable(repo, args):
    listed, _why = load_json(repo / CLAUDE_MARKET)
    pointer = any(isinstance(e, dict) and e.get("name") == args.plugin and kept_elsewhere(e)
                  for e in (listed or {}).get("plugins") or [])
    if pointer:
        # kept at its own source and listed for Claude Code only; the other apps' files do not know it
        if [a for a in APPS if a in args.apps and a != "claude"]:
            print(f"Note: {args.plugin} is kept elsewhere and only listed for Claude Code, so it is switched on "
                  "for Claude Code only.")
        args.apps = ["claude"]
    else:
        need_plugin(repo, args.plugin, "there is nothing to switch on. Give the name of one of those plugins. "
                                       "Nothing was changed.")
    project = Path(args.project).resolve()
    if not project.is_dir():
        raise Stop(2, f"The project folder {project} does not exist, so there is nowhere to switch the plugin on. "
                      "Give the folder of an existing project. Nothing was changed.")
    market = need_json(repo, CLAUDE_MARKET).get("name")
    if not isinstance(market, str) or not market:
        raise Stop(2, f'{CLAUDE_MARKET.as_posix()} has no "name", which the apps use as the marketplace name. Add it '
                      '(for example "name": "agent-plugins") and run the same command again. Nothing was changed.')
    key, where, all_ok = f"{args.plugin}@{market}", q(repo.as_posix()), True
    later = {"claude": "when the project is opened in Claude Code, it asks whether to trust the project folder; it "
                       "reads the project settings only after a yes.",
             "copilot": f"once per PC, run copilot plugin marketplace add {where}",
             "codex": f"once per PC, run codex plugin marketplace add {where}. Codex reads the project's "
                      ".codex/config.toml only for projects it trusts."}
    print(f"Switching on {key} for the project {project}.")
    for app in [a for a in APPS if a in args.apps]:
        if app == "codex":
            ok, lines = enable_codex(project / ".codex" / "config.toml", key)
        elif app == "copilot":
            ok, lines = enable_json(project / ".github" / "copilot" / "settings.json", key)
        else:
            ok, lines = enable_json(project / ".claude" / "settings.json", key, market, repo)
        all_ok = all_ok and ok
        print(f"{APPS[app]}:\n" + "\n".join(f"  {line}" for line in lines + [f"Still needed, not done by this "
                                                                            f"script: {later[app]}"]))
    if {"copilot", "codex"} & set(args.apps):
        print("The Copilot and Codex project files follow those apps' docs and have not been tried on this PC yet.")
    if not all_ok:
        print("Not everything could be switched on; the lines above say what was left and what to do.")
    return 0 if all_ok else 1


# ---- command line ----

def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=str(DEFAULT_REPO), help="the agent-plugins repository (default: %(default)s)")
    ap = argparse.ArgumentParser(description="File skills into plugins and keep the plugin files in step.")
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")
    p = sub.add_parser("new-plugin", parents=[common], help="create an empty plugin and list it in both marketplaces")
    p.add_argument("name")
    p.add_argument("--description", required=True)
    p.add_argument("--category", default="Productivity", help="category shown by Codex (default %(default)s)")
    p = sub.add_parser("add", parents=[common], help="copy a skill folder into a plugin")
    p.add_argument("skill", help="the folder that holds the skill's SKILL.md")
    p.add_argument("--plugin", required=True)
    p.add_argument("--untested", action="store_true", help="file a skill that has no test result, marked as untested")
    p.add_argument("--anyway", action="store_true", help='file a skill whose last test decided "shrink" or "drop"')
    p.add_argument("--replace", action="store_true", help="put the current version in place of the filed copy")
    p = sub.add_parser("check", parents=[common], help="check the plugin and marketplace files")
    p.add_argument("--fix", action="store_true", help="bring the other files in line with each plugin.json")
    p = sub.add_parser("enable", parents=[common], help="switch a plugin on for one project")
    p.add_argument("plugin")
    p.add_argument("--project", required=True)
    p.add_argument("--apps", nargs="+", choices=list(APPS), default=list(APPS))
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    commands = {"new-plugin": cmd_new_plugin, "add": cmd_add, "check": cmd_check, "enable": cmd_enable}
    try:
        if not (repo / "plugins").is_dir():
            raise Stop(2, f"{repo} has no plugins folder, so it does not look like the agent-plugins repository. "
                          "Point --repo at that repository. Nothing was changed.")
        return commands[args.command](repo, args)
    except Stop as stop:
        print(stop)
        return stop.code
    except OSError as e:
        print(f"Could not finish: {e}. What was done before this point stays done. Fix the cause (often a file "
              "open in another program, or missing rights) and run the same command again.")
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
