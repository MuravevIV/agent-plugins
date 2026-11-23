# Test result: bookstack

## 2026-11-23, first test: against the loose skill it was made from

- **Decision:** keep (the user's decision, after this test)
- **What was tested:** two things.
  - The script `scripts/sync_docs_wiki.py`, a port of the PowerShell script the loose skill had: 41 unit tests against a stand-in for the wiki (`tests/tool-bookstack/` in the repository). Then a dry run, which changes nothing, on three of the user's real mirrors (eight pages): it found all eight unchanged, the same verdict the old script had given.
  - The skill: three made-up cases, each answered once with this skill and once with the loose skill `bookstack`, whose text is nearly the same and whose script is the PowerShell one. Six runs of `claude-fable-5-2` through Claude Code 2.1.330. The model got a plain request and had to open the skill by itself. Each run had its own shelf in the user's real local wiki and a small git repository with two docs. A script read the facts back from the wiki and the run's folder; no model graded.
- **Result:** both passed 13 of 13 checks. Both opened the skill by themselves in every run.

| | This skill | The loose original |
|---|---|---|
| Checks passed | 13 of 13 | 13 of 13 |
| Cost of three runs | $1.03 | $1.54 |
| Time | 126 s | 100 s |
| Steps taken | 30 | 51 |
| Tool calls refused | 3 | 12 |

### Per case

| Case | What had to happen | Both sides |
|---|---|---|
| 1. First mirror of new docs | Shelf, two books, two pages, both in the mapping, the link between them a permalink with its anchor, the title not repeated in the body | Yes |
| 2. Edit a doc, update the wiki | The new line on the page, still two pages with their old ids | Yes |
| 3. Rename a doc, keep its page | Mapping entry moved to the new path, same page id, no duplicate, the link still right | Yes |

### What this says

- The port does what the PowerShell script did, on these cases and on the real mirrors.
- Results are the same on both sides, so this test does not show the new version is better at the job. It was cheaper and took fewer steps here. Part of that is the test's own doing: the runs were not allowed the PowerShell tool, so the old side lost steps finding another way to start its script.
- The new script runs wherever Python does. The old one runs on Windows only. That was the reason for the port, and no test here measures it.

### Changed after the test

- On 2026-11-23 the plugin `tool` was installed in Claude Code for the user and the loose skill, with its PowerShell script, was parked outside the folder Claude Code loads skills from. From then on docs are mirrored with the Python script.

### Limits

- Three made-up cases, one run each, two small docs.
- No side without any skill.
- The script was run on Python 3.12 on Windows only. Its claim to work elsewhere is untested.
- Not tried against the real wiki: a failure in the middle of creating pages, a mapping with the older backslash keys being added to (covered in the unit tests only), and docs with non-English text.
- The port differs from the PowerShell script on purpose in a few places: it saves the mapping after each new page, rewrites the mapping only when its content changed, compares page text exactly, takes its settings from the environment or a settings file, and has `--dry-run`. Smaller differences are listed in the author's working notes, which are not part of this repository.

### Where the records are

- `C:\make-skill-runs\tool-bookstack\iteration-1\`: every run with its steps, answer, `checks.json` and `grading.json`; the review page is `C:\make-skill-runs\tool-bookstack\bookstack-review.html`. The wiki's token is in none of these files.
- The test's own material is in `evals/`: `evals.json`, the two docs under `files/repo/`, `setup_case.py`, `wiki_api.py` and `check_runs.py`. Used once, on this PC.
- Left in the user's wiki: six shelves whose names start with `zz-tool-test-`, each with two books and two pages.

### Where the skill came from

Made on 2026-11-22 and 23 with `house/from-existing.md` of `make-skill`, from the loose skill `bookstack` in the user's skills folder (until 2026-11-22 named `bookstack-docs`). The script was ported by `claude-opus-5-5` from a written brief and checked by the session's main model. There is no MCP server for the wiki, so there is no second plugin.
