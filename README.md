# agent-plugins

One person's plugins for coding agents: Claude Code first, with
description files that GitHub Copilot and OpenAI Codex also accept. The
repository is its own plugin marketplace, named `agent-plugins`.

These are working tools, published as they are. The protocols and tool
skills assume the author's setup: a self-hosted Plane tracker, a
self-hosted BookStack wiki, and an outside model reached through the
OpenCode command line. Read a skill before you use it.

## What is here

| Plugin | Skill | What it is |
|---|---|---|
| `core` | `make-skill` | Making a skill, turning a finished session or an existing thing into one, and testing whether a skill helps. A fork of Anthropic's `skill-creator` with house rules added |
| `protocol` | `triad` | A way of working for a session: one strong model manages, cheaper models do written-out work, a model from another family grades and reviews |
| `protocol` | `trail` | A way of working for ticketed work: every change has a ticket, a local commit and a wiki page that point at each other |
| `tool` | `plane` | Reaching a Plane tracker. Comes with `scripts/plane.py`, so no MCP server is needed |
| `tool` | `bookstack` | Mirroring a project's `docs/` folder to a BookStack wiki. Comes with `scripts/sync_docs_wiki.py` |
| `plane-mcp` | none | Only the registration of Plane's MCP server, for places that allow servers |

Two kinds of skill, kept apart on purpose:

- **Tool skills** hold facts about a system and a script that reaches
  it. The model finds them by their description when a task calls for
  them.
- **Protocol skills** hold rules for a whole session. They are hidden
  from the model and loaded only by the user, by typing the name, for
  example `/protocol:trail`. No skill loads a protocol.

```
agent-plugins/
├── .claude-plugin/marketplace.json    marketplace file for Claude Code and Copilot
├── .agents/plugins/marketplace.json   marketplace file for Codex
├── plugins/<plugin>/
│   ├── plugin.json                    plugin file for Copilot and Codex
│   ├── .claude-plugin/plugin.json     plugin file for Claude Code
│   └── skills/<skill>/                SKILL.md, scripts/, references/, evals/, TEST-RESULT.md
├── tests/                             unit tests for every script
└── tools/                             the filing script and the check before publishing
```

Every skill carries a `TEST-RESULT.md`: what was tested, on what, what
came out, and what was not covered. "Untested" is said plainly where it
applies.

## Installing

In Claude Code:

```
/plugin marketplace add MuravevIV/agent-plugins
/plugin install core@agent-plugins
/plugin install protocol@agent-plugins
/plugin install tool@agent-plugins
```

The path of a local clone works in place of the address. `plane-mcp` is
installed only where MCP
servers are allowed, and needs `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`,
`PLANE_BASE_URL` and `PLANE_API_HOST_URL` set in the environment.

Copilot and Codex: the description files follow each app's published
format, and each app's command line accepted them once, from a local
folder (`copilot plugin marketplace add <folder>`,
`codex plugin marketplace add <folder>`). The skills have not been run
in those two apps.

What the tool skills need:

- `plane`: `PLANE_BASE_URL`, `PLANE_WORKSPACE_SLUG` and `PLANE_API_KEY`
  in the environment, or the same three in a JSON file named by
  `PLANE_CONFIG_FILE`.
- `bookstack`: `BOOKSTACK_URL`, `BOOKSTACK_TOKEN_ID` and
  `BOOKSTACK_TOKEN_SECRET` in the environment, or a file named by
  `BOOKSTACK_ENV_FILE`.

Both scripts are Python 3.9 or later with the standard library only.
Neither prints a key.

## make-skill

Anthropic's `skill-creator` (Apache 2.0) with the author's rules added.

- Anthropic's files are kept as they are, apart from two spots in
  `SKILL.md`: the name and description at the top, and a note under the
  title that points to the house rules.
- The additions are in `plugins/core/skills/make-skill/house/`. Start
  with `house/rules.md`.
- `house/CHANGES.md` lists every change to Anthropic's files and every
  added file, as the licence asks.
- `house/testing.md` explains the two scripts in `house/scripts/`:
  `run_tests.py` answers each test case with and without a skill, each
  as a separate command-line run; `grade_outside.py` hands the answers,
  with the sides hidden, to a model from another family. The second one
  sends nothing until it is started with `--yes`.

To take a new version from Anthropic, replace their files with the ones
from `github.com/anthropics/skills`, folder `skills/skill-creator`, and
put the two spots in `SKILL.md` back. The copy here matched their commit
`e4bb5d9` of 2026-11-16.

## Tests

```
python -m unittest discover -s tests/make-skill
python -m unittest discover -s tests/tools
python -m unittest discover -s tests/tool-plane
python -m unittest discover -s tests/tool-bookstack
```

On Windows, set `PYTHONUTF8=1` first. Every script is tested against a
stand-in for what it talks to. No test needs a sign-in, calls a model or
costs anything.

The tests of the skills themselves are a different thing: runs of a real
agent, with and without the skill. Their material is in each skill's
`evals/` folder and their outcome in its `TEST-RESULT.md`.

## Tools

`tools/pack_skill.py` does the bookkeeping for plugins. It starts no app
and installs nothing.

```
python tools/pack_skill.py check
python tools/pack_skill.py new-plugin <name> --description "<what it is for>"
python tools/pack_skill.py add <skill folder> --plugin <name>
python tools/pack_skill.py enable <plugin> --project <project folder>
```

- `check` compares each plugin's description files with the marketplace
  files and lists every skill with the decision of its last test.
- `add` copies a skill into a plugin. A skill with no test result is not
  filed until you choose: test it, or add `--untested`.
- `enable` writes the files that switch a plugin on in one project.

`tools/publish_check.py` is run before anything is pushed. It looks
through every tracked file and the commit history for keys, e-mail
addresses, paths inside a user's home folder, and any word on a private
list kept outside the repository.

## Licence

The author's own work is under the MIT licence, see `LICENSE`.

`plugins/core/skills/make-skill` is a modified copy of Anthropic's
`skill-creator` and stays under the Apache License 2.0, see
`plugins/core/skills/make-skill/LICENSE.txt` and `house/CHANGES.md`
there. The files under its `house/` folder are the author's.
