# agent-plugins: project instructions

Plugins for Claude Code, Codex and GitHub Copilot, and the marketplace
that lists them. This repository is published. See README.md.

Rules for working here:

- **Nothing private goes into this repository.** No keys, no e-mail
  addresses, no paths inside a home folder, no names of the author's
  other projects, workspaces or employers, no working notes. Notes and
  plans live outside it. Run `python tools/publish_check.py` before any
  push and do not push while it reports a finding.
- **Other people's work stays out** unless its licence file and
  copyright line come with it and its changes are listed.
- **Anthropic's files in `plugins/core/skills/make-skill/` stay as they
  are.** Additions go in its `house/` folder. They differ from
  Anthropic's only where `house/CHANGES.md` says so: two spots in
  `SKILL.md` and one added line in four scripts. Any other change to an
  Anthropic file needs the user's word and a line in that file.
- **Before writing, splitting, renaming or changing any skill, load
  `make-skill`** and follow `house/rules.md`. That covers protocol
  skills too.
- **Scripts are Python**: 3.9 or later, standard library only, one file
  each, type hints on every function, unit tests against a stand-in for
  whatever the script talks to.
- **Nothing here is installed or registered in any app without the
  user's word.** That covers Claude Code, Codex and Copilot, plugins and
  marketplaces alike.
- **Copilot and Codex**: write description files to each app's published
  format and check them by letting that app's command line read them. No
  test runs in those apps without the user's word.
- **Plain words.** Everything a person reads (skill text, script
  messages, replies) must make sense to someone who arrived five minutes
  ago. No invented shorthand. A failure message says what happened, why
  it matters and what to do next.
- **Grading.** A model from the same family as the one that wrote the
  answer does not grade it unless the user agrees.
- Commit only when the user asks. Never push without the user's word.
