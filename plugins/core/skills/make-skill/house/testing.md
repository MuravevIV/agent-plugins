# Running a skill's tests from the command line

Two scripts in `house/scripts/` do the test work that Anthropic's text
does with subagents ("Running and evaluating test cases", steps 1, 3 and
4). They write the same folders and files, so Anthropic's
`scripts/aggregate_benchmark.py` and `eval-viewer/generate_review.py` work
on the result unchanged. Use them where the app has a command line; fall
back to Anthropic's subagent way where it does not, or where the command
line is not signed in.

Both need only Python, with nothing to install (written for 3.9 or
later, tried on 3.12 only). Run them from the `make-skill` folder.

## 1. Answer the test cases: `run_tests.py`

```bash
python house/scripts/run_tests.py --skill <skill folder> --dry-run
python house/scripts/run_tests.py --skill <skill folder>
```

It reads `<skill folder>/evals/evals.json` and answers every case twice:
once in a project folder that holds the skill, once in a project folder
without it. Each answer is one separate run of the app's command line
(`claude -p` for now), so the two answers share nothing.

Useful options:

| Option | What it does |
|---|---|
| `--dry-run` | Prints the commands and creates nothing. Start with this |
| `--compare-with <older copy>` | Compares against an older copy of the skill instead of no skill |
| `--instruction-lines <file>` | Adds a third side: no skill, but the file's text as `CLAUDE.md` in the project folder |
| `--load-by-name` | For a skill the user starts by typing its name (rule 8): puts the skill's name in front of each request on the side that has the skill |
| `--only-with-skill` | Answers only on the side that has the skill. Cheap, and it proves nothing about whether the skill is needed |
| `--runs 3` | Three answers per case and side, to see how much answers vary |
| `--cases 1 4` | Only these case ids |
| `--model <name>` | The model that answers. A short name picks what the app means by it (on 2026-11-22 `fable` meant `claude-fable-5-1`). A full name such as `claude-fable-5-2` works, with a warning from the app that it does not know the name |
| `--allow-tools "Bash(python:*),PowerShell(python:*)"` | Tools the runs may use without asking. This example allows single `python` commands in both shells and nothing else |
| `--workspace <folder>` | Where the results go. See the note on the workspace below |
| `--max-cost-per-run 0.50` | Spending limit per run, in dollars |
| `--keep-user-setup` | Lets the runs see your own skills and settings. Off by default, so the "without" answer cannot pick up the same skill from your user folder |
| `--redo` | Runs again what already finished |

What comes out, under `<skill-name>-workspace/iteration-N/` next to the
skill:

```
eval-<id>-<name>/
├── eval_metadata.json
├── with_skill/run-1/
│   ├── outputs/        answer.md plus every file the run created or changed
│   ├── transcript.md   what the run did, step by step
│   ├── timing.json     tokens, time, cost
│   ├── run.json        status, model, the command, whether the skill was listed and opened
│   ├── events.jsonl    the app's raw output
│   └── stderr.txt
└── without_skill/run-1/   the same
```

Things the script checks for you and says in plain words:

- The program is not signed in. It stops at once, tells you the command
  that signs it in, and keeps what already finished.
- The skill was not offered to a run that should have had it. That run
  counts as failed.
- The skill was offered to a "without" run. The run is kept and marked
  `"clean_comparison": false`. Do not use that pair as proof.
- The skill was offered and never opened. Counted in the summary. If this
  happens in most runs, the description is the problem, and the answers
  say nothing about the skill's content.
- A run was refused a tool. The message names the tool and the option
  that allows it.

Starting the same command again skips runs that finished and repeats the
ones that failed. Nothing has to be cleaned up by hand.

`--instruction-lines <file>` answers the question asked before a skill is
kept: would a few lines in `CLAUDE.md` do the same job? Each case gets a
third side, `without_skill_plus_lines`: no skill, and the file's text
written to `CLAUDE.md` at the top of the project folder. Anthropic's
adding-up script lists it as a third side in `benchmark.json` and its
printed summary (its `benchmark.md` table shows only the first two), and
its "delta" still compares the first two sides. After changing the
lines in the file, start again with `--redo`: finished runs are skipped
even when the file's text is new. Checked on real runs: the app reads
that `CLAUDE.md` while the user's own setup stays hidden.

Where the workspace goes matters. Claude Code also reads the instruction
files of the folders above a project. A workspace next to a skill that
lives inside a project therefore passes that project's `CLAUDE.md` to
every run, on every side, and the comparison says less about the skill.
The script points this out when it sees it. Pass `--workspace` with a
folder outside any project and outside your home folder, and copy the
results to where you keep them afterwards.

Your home folder counts as such a project. Claude Code reads your own
instruction file (`.claude/CLAUDE.md` in the home folder) for every
project under the home folder, even when your settings are left out. On
Windows the temporary folder is inside the home folder, so a workspace
there gives every run your personal instructions, and their wording can
turn up in answers that go to an outside grader. That happened in the
tests of 2026-11-22. The script now refuses such a workspace and
suggests a folder, for example `C:\make-skill-runs\<skill name>`. With
`--keep-user-setup` it goes ahead, since then you asked for your own
setup to be seen.

On allowed tools: a rule such as `Bash(python:*)` covers one command at a
time. A run that chains commands (`cd x && python y`) is refused, and the
summary counts it. In the first real test that happened 76 times in 36
runs, the same on every side, and the runs went on with single commands.

A case's input files are listed in its `files`, relative to the skill
folder, and are copied into the run's folder at the same path. A model
that sees `evals/files/...` in its folder can tell it is being tested. To
avoid that, give the case a `files_root`: that part of each path is left
off in the run's folder.

```json
{"id": 2, "prompt": "Fix the port in notes/setup.md",
 "files_root": "evals/files/case-2",
 "files": ["evals/files/case-2/notes/setup.md"]}
```

Some cases need more than copied files: a git repository with a first
commit, or a fresh project in an outside system. Give such a case a
`setup`: a Python script inside the skill folder. The runner starts it
in the run's folder after the files and the skill are in place and
before the app. It gets the case id, the side and the run number in the
environment variables `MAKE_SKILL_CASE`, `MAKE_SKILL_ARM` and
`MAKE_SKILL_RUN`, and the run's own folder in `MAKE_SKILL_RUN_DIR`.
What it prints is kept in `setup.txt`. If it fails, the app is not
started for that run and the run counts as failed. Used once, for the
test of the `trail` protocol on 2026-11-22.

```json
{"id": 1, "prompt": "Fix the bug in count.py", "setup": "evals/setup_case.py"}
```

Where the program is looked for: `--program`, then the environment
variable `MAKE_SKILL_CLAUDE_PROGRAM`, then `claude` on the path, then the
copy that ships inside the Claude desktop app on Windows. That copy has
two addresses. From inside the app it is under
`%APPDATA%\Claude\claude-code\`. From your own shell it is in the app's
private folder,
`%LOCALAPPDATA%\Packages\Claude_...\LocalCache\Roaming\Claude\claude-code\`.
The script looks in both. To sign that copy in, run it from your own
shell with `auth login`, using the second address.

## 2. Checks a script can decide

Do these first, as rule 3 says: a file exists, a value matches, a command
passes. Write a small script per skill and let it fill in what it can.
There is no general script for this, because the checks differ per skill.

The outside grader gets only the files in `outputs/`. It does not see
what a run did on the way: which tools it called, what it handed to a
subagent. Where a test is about that, the per-skill script has to read
`events.jsonl` and either decide the point itself or write what it found
into a file under `outputs/` for the grader to read.

`grade_outside.py` replaces a `grading.json` that an outside model did
not write. So keep the script's rows in a file of their own first, and
add them to `grading.json` after the outside grading.

## 3. Grade the rest with an outside model: `grade_outside.py`

```bash
python house/scripts/grade_outside.py --iteration <workspace>/iteration-N --skill <skill folder>
```

Without `--yes` it sends nothing. It builds one prompt per case, prints
which files would leave this computer and where they would go, and stops.
Read that list. The user agreed on 2026-11-22 that test material may go
to the outside grader, so the question left to ask is the cost: say how
many prompts would be sent and ask whether to spend that, unless the
user already asked for the outside grading. Then run it again with
`--yes`.

Before the list it may print "Look at this before anything is sent".
That means the answers use wording that also stands in an instruction
file on this computer (your own, or one in a folder above the runs) and
is not part of the test's own material. The runs probably read that
file. Search the prompt files for the words it names, read the sentences
around them, and decide whether they may leave the computer. The check
compares pairs of neighbouring words, so it is rough: it can point at
harmless wording and it can miss things. It does not replace reading the
prompt files.

What it does to keep the grading fair:

- The answers of one case go to the grader together in one prompt, under
  letters in random order. With two sides and one run that is A and B;
  with three sides and three runs it is A to I, and nine answers in one
  prompt worked (the longest prompt so far was about 100,000 characters).
  The grader is not told which answer had the skill. Folder names and
  paths that would give it away are replaced with `[removed]`.
- It refuses a grader from the family that wrote the answers, unless you
  pass `--same-family-ok`. Do not pass it without asking the user
  (rule 3).
- The grader gets no tools, only the text of the prompt.

It writes `grading.json` into each run folder in the form Anthropic's
viewer reads, with the grader's model recorded, plus `comparison.md` and
`ranking.json` per case under `<iteration>/outside-grading/`. Next to
them, `prompt.md` is the exact text that left this computer.

OpenCode leaves a working folder of its own at
`<iteration>/outside-grading/.grader/` (about 60 MB of its packages).
Leave it out when you copy or keep the results.

A case with no `expectations` has nothing for the grader to judge and is
skipped with a message saying so.

The default grader is `openai/gpt-6.2-sol` through the OpenCode command
line. `--model` and `--variant` change it. On another machine, point
`--program` or `MAKE_SKILL_OPENCODE_PROGRAM` at the `opencode` program.

One limit: an answer that names the skill in its own text can still give
away which side it came from. Read `comparison.md` with that in mind.

## 4. Add up and show

Anthropic's steps from here on are unchanged:

```bash
python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
python eval-viewer/generate_review.py <workspace>/iteration-N --skill-name <name> --benchmark <workspace>/iteration-N/benchmark.json
```

Three things to know:

- On Windows, set `PYTHONUTF8=1` before `generate_review.py`. Its page
  template contains characters the default Windows encoding cannot read.
- With `--compare-with`, the table's "delta" reads old copy minus new
  copy, because the sides are sorted by name. A negative number there
  means the new copy did better.
- Anthropic's step 1 shows no `run-1` folder level. The adding-up script
  needs one, and `run_tests.py` creates it.

Then finish as rule 1 says: keep, shrink or drop, written into
`TEST-RESULT.md`.

## What has been tried

The scripts pass their own tests (`tests/make-skill/` in the repository,
39 tests against stand-in programs).

On 2026-11-22 they did their first real job, the test of the `triad`
skill: 54 runs through Claude Code 2.1.299 (6 cases, 3 sides, 3 runs
each), then one real grading by `openai/gpt-6.2-sol` (5 prompts, about a
minute each, $0.40 in all). How a run shows that it opened the skill and
how refused tools are listed were both checked against those runs and
needed no change.

Not tried: `--compare-with` on real runs, any app other than Claude Code,
and any Python other than 3.12.

What that first test taught about writing cases:

- A case the model gets right without any help shows no difference
  between the sides and proves nothing. Two of the six were like that.
  Try each case once without the skill before spending runs on it.
- Count how often the skill was opened per case, not only overall. A
  skill that is never opened for one kind of request fails there no
  matter how good its text is.
- The outside grader reads expectations word for word. One thing per
  expectation, no brackets, nothing vague such as "the reader can follow".

## The built-in alternative in Claude Code

Claude Code has its own command, `claude plugin eval`, with its own case
format and a with-and-without mode. It is not used here for three
reasons: it works in Claude Code only, its model judge is from the same
family as the answers, and on Windows its shell tools need a sandbox that
is not available outside WSL. For a skill that will only ever live in
Claude Code it is a fair choice.
