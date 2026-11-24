# Changes to Anthropic's skill-creator

This folder is a modified copy of Anthropic's `skill-creator`, used under
the Apache License 2.0 (see `../LICENSE.txt`, kept unchanged). This file
states what was changed, as section 4(b) of the license asks.

Source of the copy: `skill-creator` as found in the user's skills folder
on 2026-11-22, files dated 2026-06-13. The unchanged copy is on the git
branch `upstream/skill-creator`.

Checked on 2026-11-22 against Anthropic's public repository
`github.com/anthropics/skills`, folder `skills/skill-creator`, at commit
`e4bb5d9` of 2026-11-16: the same 18 files, identical apart from line
endings. So there was nothing to merge. That folder last changed
upstream on 2026-04-20 (a license notice), and its last change of
content was on 2026-03-06.

## Changed files

| File | Change | Date |
|---|---|---|
| `SKILL.md` | `name` changed from `skill-creator` to `make-skill`; `description` extended to cover making a skill from a finished session and checking whether a skill helps at all | 2026-11-22 |
| `SKILL.md` | A note added right under the title, pointing to `house/rules.md`, `house/from-session.md` and this file | 2026-11-22 |
| `SKILL.md` | `description` extended by two sentences saying it covers protocol skills too. Reason: the second protocol skill, `trail`, was written without this skill being loaded | 2026-11-22 |
| `eval-viewer/generate_review.py`, `scripts/improve_description.py`, `scripts/run_eval.py`, `scripts/run_loop.py` | One line added before the first import: `from __future__ import annotations`. Reason: these files write type hints as `dict \| None`, which Python 3.9 cannot read when it loads the file; 3.9 is the Python that comes with macOS. The line makes Python keep the hints as text. Nothing else in the files is changed | 2026-11-23 |

No other Anthropic file is changed.

## Added files (ours, not Anthropic's)

| File | What it is |
|---|---|
| `house/rules.md` | Our eight rules and how they change Anthropic's process |
| `house/from-session.md` | How to make a skill from a finished session |
| `house/from-existing.md` | How to bring something that already exists up to our rules: a skill, a plugin, an MCP server, an extension, a rules file |
| `house/procedure-template.md` | Template for a skill that describes a task with ordered steps |
| `house/conventions-template.md` | Template for a skill that describes how work in a domain is done |
| `house/examples.md` | Good and bad examples of skill sections |
| `house/test-result-template.md` | Template for the short record of a skill's test |
| `house/testing.md` | How to run a skill's tests and the outside grading from the command line |
| `house/scripts/run_tests.py` | Answers each test case with and without the skill through an app's command line (Claude Code for now) |
| `house/scripts/grade_outside.py` | Sends the answers of a case, with the sides hidden, to a grader from another model family through OpenCode |
| `house/CHANGES.md` | This file |
| `TEST-RESULT.md` | The record of this skill's own test: untested, with what one real use showed |

The self-tests for the two scripts are outside this folder, in
`tests/make-skill/` at the top of the repository, so they are not shipped
with the skill.
