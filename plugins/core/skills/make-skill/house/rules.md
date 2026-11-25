# Our rules for making skills

Read this before following `SKILL.md`. Where the two differ, this file
wins. `SKILL.md` and the folders `agents/`, `scripts/`, `eval-viewer/`,
`assets/` and `references/` are Anthropic's and are kept as they came, apart
from the few changes listed in `house/CHANGES.md`, so that new versions can
be merged in. Everything of ours is in this `house/`
folder.

A word on terms: Anthropic's text says "eval" for a test of a skill and
"assertion" for one thing a test checks. This file says "test" and
"check". When talking to the user, use the plain words.

## Which way in

| The user wants | Start with |
|---|---|
| A skill from scratch | `SKILL.md`, "Creating a skill" |
| A skill from the session that just finished | `house/from-session.md`, then come back here for testing |
| A better version of an existing skill | `SKILL.md`, "Improving the skill" |
| Something that exists brought up to these rules: a skill, a plugin, an MCP server, an extension, a rules file, or a mix | `house/from-existing.md`, then come back here for testing |
| A skill of one project made available elsewhere (promoting it) | `house/from-existing.md`, its section "Promoting a skill from one project to a plugin" |

## How far this skill has to go

Ask early, if the user has not said: will this skill stay in one project,
or should it be available in other projects and apps?

| Where it will live | What that requires |
|---|---|
| One project only | Nothing more. Offer a test, do not insist. A project skill is cheap and easy to delete. |
| Shared: other projects, other apps, or "global" | Tested first (rules 1 to 3), then placed in a plugin (rule 6). |

The reason for the difference: a shared skill costs something in every
session that can see it, and nobody remembers later why it is there. A
skill in one project is seen by the person who asked for it.

There are only these two end states. A skill kept loose in the user's
own skills folder is not one: it reaches one app on one machine and
cannot be moved or switched on per project. It may sit there while it
is being worked on, and then goes into a plugin.

## The eight rules

### 1. Prove it helps before sharing it

Run every test case twice: once with the skill and once without it. Then
write down one of three decisions.

- **Keep**: the answers with the skill are clearly better.
- **Shrink**: only part of the skill made a difference. Cut the rest and
  test again.
- **Drop**: no clear difference. Tell the user so, and do not share the
  skill.

The skill has to earn its place. "It did no harm" is a reason to drop it.

Before testing, also ask one question: would a single line in the
project's instruction file (`CLAUDE.md`, `AGENTS.md`) do the same job? If
yes, propose that line instead of a skill. If the answer is not obvious,
test it: write the few lines down and let `run_tests.py` answer each case
a third time, without the skill and with those lines
(`--instruction-lines`, see `house/testing.md`). A skill that does no
better than its own short summary is a "shrink" or a "drop".

Why: we tested a general rule-book skill over four rounds. It looked
useful on cases we had invented and gave no gain on real ones. A strong
model already knows general good practice. A skill helps when it carries
what the model cannot know: the user's own decisions, local facts, a
procedure that was hard to get right.

How this changes Anthropic's text:

- "Capture Intent", point 4, lets the user skip tests. For a shared skill
  the test is required. If the user wants to share without testing, do not
  refuse: say plainly that the skill is untested, and record it that way
  (see "Writing down the result").
- The run without the skill is never left out silently. Anthropic's
  section for apps without subagents skips it. If it cannot be run where
  you are, say so and record the result as "not compared".
- Where the app has a command line, the runs can be made with
  `house/scripts/run_tests.py` instead of subagents. It keeps the two
  sides apart and writes the same folders. `house/testing.md` has the
  steps.
- Anthropic's loop ends when the user is happy with the output. Ours ends
  with one of the three decisions above.

### 2. Test on real cases first

Take test cases, in this order, from:

1. The session the skill came from: the original request and what the
   right result turned out to be.
2. Past requests of the same kind that went wrong. Ask the user where to
   find them. Do not read other projects or session histories without
   their yes.
3. Cases you make up. Use these only when the first two give too little,
   and label each one "made up" in the test file and in the result.

Why: invented cases are written by the same mind that wrote the skill, so
they tend to ask exactly what the skill answers. Real cases carry the
mess that made the task hard.

How this changes Anthropic's text: "Test Cases" tells you to come up with
two or three realistic prompts. Do that only after looking for real ones.

Before a real case goes into a test file, remove passwords, keys,
addresses of machines and personal details.

### 3. Let a different model family grade

Checks that a script can decide come first: a file exists, a value
matches, a command passes. They cost nothing and do not argue.

For what a script cannot decide, the grader should be a model from a
different family than the one that wrote the answers. A model grading its
own family's work shares its blind spots and tends to be generous.

How this changes Anthropic's text: "Step 4: Grade" starts a grader
subagent or grades inline. Both are the same model family marking its own
work. Instead:

- If an outside grader is set up on this machine, use it through
  `house/scripts/grade_outside.py` (see `house/testing.md`). The user
  agreed on 2026-11-22 that test material and source code may go to the
  outside grader, since it already goes to Claude; no yes per item is
  needed for sharing it. What is still asked is the cost: the grader
  runs on another paid account, so say roughly how many prompts a job
  takes and ask before spending, unless the user's request already
  asked for the outside grader. Passwords, keys, machine addresses and
  personal details are still taken out first.
- If none is set up, say so plainly and offer three ways on: the user
  grades by reading the answers side by side in the review page; the same
  model family grades and the result is marked "graded by the same
  family"; or stop here and set up an outside grader first.

Do not pick the second way without asking.

### 4. Turn fixed steps into scripts

When a step ran, or will run, the same way every time with no judgement
involved, put it in one script under the skill's `scripts/` folder. The
parts that change become the script's inputs. The skill text then says
when to run the script and what to do with its output.

Why: a script does the same thing every time, costs almost nothing to
run, and does not need to be reread into the conversation.

Write every script in Python: version 3.9 or later, the standard library
only, one file per script, nothing to build and nothing to install. Put
type hints on every function. Where a type checker is at hand, let the
skill's self-tests run it over the script; the script itself must run
without one.

Why Python: a skill lands on a machine and its script has to run as it
is. Web calls, JSON, command-line options, files and subprocesses are
all in the standard library, the scripts in this skill are Python
already, and one language means one way to write and test them.

A script lifted from a single session has only ever run once, on one set
of inputs. Say so next to it in the skill text ("used once, on <what>")
until it has worked a second time on something else.

Each script must say what went wrong in plain words when it fails, and
must be safe to run again after a failure (rule 7).

How this changes Anthropic's text: it looks for repeated work only after
test runs ("How to think about improvements", point 4). Look for it while
writing the first draft as well.

### 5. Work without an MCP server

An MCP server is a separate program that gives the agent tools for an
outside system. Some workplaces switch these off. So a skill reaches
outside systems through a script in its own folder or through a
command-line tool. An MCP server may be offered as a faster path, never
as the only one. Build the script path also where a server is at hand:
a skill made in one place is used in another. If a skill does come with
a server, the server goes into a second plugin (`<name>-mcp`), so that
it can be switched on and off by itself. `house/from-existing.md`,
step 4, has the shape.

### 6. A shared skill ships as a plugin for three apps

A shared skill lives in a plugin in this repository, under
`plugins/<plugin>/skills/<skill-name>/`, and has to work in Claude Code,
Codex and GitHub Copilot.

- Its tests must pass in Claude Code.
- For Copilot and Codex, at this stage: the plugin's description files
  are written to each app's published format and checked by letting that
  app's command line read them (add the marketplace, install the plugin,
  list it, uninstall it). This runs no model and costs nothing. It shows
  the app accepts the files. It does not show how the skill behaves
  there, and no test runs are made in those apps for now.
- Ask the user before the first install into Copilot or Codex. It changes
  their setup for a moment.

To keep a skill usable in all three, write its text without leaning on
one app: say "ask the user" instead of naming one app's question tool,
and "the project's skills folder" with `.claude/skills/` as an example.

### 7. Speak plainly and recover

This holds for what you say while using `make-skill`, and for every skill
and script it produces.

- A message to a person must make sense to someone who installed the
  skill five minutes ago and saw nothing that came before.
- Every stop says three things: what happened, why it matters, what to do
  next.
- No invented terms. Over a long session an agent starts naming things
  for its own convenience. Those names mean nothing to the reader. If a
  name was not in the user's own words or in the app's documentation,
  replace it with a description.
- Offer a way forward instead of a flat refusal.
- A run that stopped halfway can be started again without cleaning up by
  hand.

Bad: "Cannot perform the pack step: validation is not passing the P1
gate."

Good: "I can't add this skill to the shared plugin yet. It has never been
tested, so nobody knows whether it helps. I can test it now, which takes
about ten minutes, or add it anyway and mark it as untested. Which do you
prefer?"

Test this rule like the others: make the skill fail on purpose (a missing
file, a wrong input) and ask whether a new developer could act on the
message.

### 8. A protocol skill is loaded by name and stays hidden

A protocol skill holds the user's own way of working for a whole session:
who does what, and rules that hold on every turn. The user picks it by
typing its name. No app should open it on its own.

- Hide its description from the model. In `SKILL.md`, between the `---`
  lines: `disable-model-invocation: true` (read by Claude Code and
  Copilot). For Codex, a file `agents/openai.yaml` with the two lines
  `policy:` and `  allow_implicit_invocation: false`.
- Test it loaded by name: `run_tests.py --load-by-name` puts the skill's
  name in front of each request, the way the user would type it.
- A shared protocol skill goes into the plugin `protocol`. Every skill
  in that plugin follows this rule.
- Give it the protocol's own name, for example `triad`, with no
  `protocol-` in front. Claude Code, Copilot and Codex all show the
  plugin's name before the skill's, so the user sees and picks
  `protocol:triad`. The plugin's name already says what it starts; a
  skill named `protocol-triad` would read `protocol:protocol-triad`.
- The user may load several protocols in one session, so each one is
  written to stand next to others. It says its own side in general
  terms and names another protocol only when a general rule cannot say
  it. In practice:
  - A protocol with steps says what kind each step is: talking to the
    user, shared record (a tracker, a commit, a wiki sync), work, or
    judgement (a review whose verdict is the result). A judgement step
    is done only when another loaded protocol provides the judge.
  - A protocol that gives roles to agents says which kinds stay with
    which role.
  - Every protocol carries a section "With other protocols" with the
    same three rules: where two disagree the stricter wins, and the
    user is asked when that is unclear; an agent that gets work handed
    to it sees no protocol, so the rules for its piece go into its
    brief; each protocol keeps its own line in a summary and never
    removes another's.
- Only the user loads a protocol. No other skill loads one by name or
  tells the model to. A skill may say that a protocol exists and what
  it is for, and may tell the user that it is not loaded.
- A protocol the user loaded stays loaded when the session is
  summarised. Its section "When the conversation is summarised" keeps
  one line in the summary with the path of its own file, and tells the
  model to read that file again when the text is gone and to say so in
  one line. That is not loading a protocol: the user already picked
  it. The user is asked to type the name again only when the file
  cannot be read.
- A protocol that writes to a system outside the session (a tracker, a
  wiki) names that system and says it writes nowhere else. Words such
  as "the tracker" are not enough: where a second tracker is in reach,
  for example a company's next to the user's local one, a protocol that
  acts on its own would write to the wrong one.
- `tools/pack_skill.py` does not file a skill into that plugin while its
  name starts with `protocol-` or an app can still open it on its own,
  and its `check` command reports one that got in another way.

Why: the first skill tested here was such a protocol. Left for the model
to find by its description, it was never opened on a plain request and
did worse than seven lines in an instruction file. Loaded by name, it was
followed in every run. Rules for every turn have to be read every time,
and a skill the user starts by name is. A hidden description also costs
nothing in the sessions that do not use the protocol.

How this changes Anthropic's text: "Write the SKILL.md" asks for a pushy
description so the skill gets picked, and a later step tunes the
description. Skip both for a protocol skill. Its description is one plain
sentence for a person reading a list. Rule 1 still holds: compare with
and without the skill, both sides given the same request.

## Writing down the result

After testing, or after the user chose to skip it, put a file named
`TEST-RESULT.md` in the skill's folder, filled from
`house/test-result-template.md`. It is short on purpose. It answers the
question a person asks a year later: was this ever tested, on what, and
what came out?

## What is not built yet

As of 2026-11-22. When one of these matters, tell the user in plain words
what is missing and what can be done instead.

| Missing | What to do meanwhile |
|---|---|
| Test runs through the command line of Copilot or Codex. `run_tests.py` covers Claude Code only | Test in Claude Code (rule 6 asks for no more at this stage) |

## What is built

| Piece | Where | How to use it |
|---|---|---|
| Test runs through Claude Code's command line, with and without the skill | `house/scripts/run_tests.py` | `house/testing.md` |
| Grading by a model from another family | `house/scripts/grade_outside.py` | `house/testing.md`. It sends nothing until the user has agreed |
| Plugin and marketplace files that Claude Code, Copilot and Codex all accept (tried 2026-11-22 with the `core` plugin) | The repository's `README.md` | Made and kept in step by the filing script below |
| Filing a skill into a plugin, creating a plugin, checking the description files, switching a plugin on in a project | `tools/pack_skill.py` at the top of the repository | `python tools/pack_skill.py --help`. Used for real on 2026-11-22: the `protocols` plugin and its first skill |
