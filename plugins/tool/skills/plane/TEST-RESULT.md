# Test result: plane

## 2026-11-23, first test: against the loose skill it was made from

- **Decision:** keep (the user's decision, after this test)
- **What was tested:** two things.
  - The script `scripts/plane.py`: 37 unit tests against a stand-in for Plane (`tests/tool-plane/` in the repository), and then every command once by hand against a throwaway project in the user's real local Plane.
  - The skill: three made-up cases, each answered once with this skill and once with the loose skill `plane` it was made from, which has the same facts and no script. Six runs of `claude-fable-5-2` through Claude Code 2.1.330. The model was given a plain request and had to open the skill by itself. Each run had its own throwaway Plane project with ten starting tickets. A script read the facts back from Plane; no model graded.
- **Result:** this skill passed 11 of 11 checks, the loose one 10 of 11. Both opened the skill by themselves in every run.

| | This skill | The loose original |
|---|---|---|
| Checks passed | 11 of 11 | 10 of 11 |
| Cost of three runs | $1.10 | $1.45 |
| Time | 62 s | 85 s |
| Steps taken | 20 | 33 |
| Tool calls refused | 0 | 6 |

### What this says

- With the script the model reaches Plane in fewer steps. Without it, every run first wrote its own small helper program for the calls, and chained shell commands that were refused.
- The one failed check is about wording, not about the script. Asked to "mark ticket 5 as done", the run with the loose skill did not do it and asked whether to load `protocol:trail` first, as the last paragraph of the skill tells it to for closing a ticket. The run with this skill, which has the same paragraph, closed the ticket without asking. So that paragraph is followed in one run of two, and it was unclear whether a bare change of state should trigger it at all. Settled afterwards, see below.

### Changed after the test

- The last paragraph was narrowed on the user's word: the note about `protocol:trail` is for a request to implement a ticket only, a plain change such as marking a ticket done is just done, and the skill says outright that only the user loads a protocol. Not run again.
- On 2026-11-23 the plugin `tool` was installed in Claude Code for the user and the loose skill was parked outside the folder Claude Code loads skills from.

### Limits

- Three made-up cases, one run each, one tiny project.
- The comparison is with the loose skill, so it shows that the script helps, not that a skill is needed at all. There was no side without any skill.
- Only the script path was tried. No run had a Plane MCP server, so "use the server's tools when they are there" is untested.
- Attachments were tried only as an empty list. Download was never run against the real Plane.
- The script was run on Python 3.12 only.
- Details of Plane's answers that the script's writer had to assume and that the hand check did not reach: more than one state in a group, attachments, a parent ticket in another project.

### Where the records are

- `C:\make-skill-runs\tool-plane\iteration-1\`: every run with its steps, answer, `checks.json` and `grading.json`; the review page is `C:\make-skill-runs\tool-plane\plane-review.html`. The Plane key is in none of these files.
- The test's own material is in `evals/`: `evals.json`, `setup_case.py` (a fresh Plane project per run), `plane_api.py` and `check_runs.py`. Used once, on this PC.
- Left in the user's Plane: six more throwaway projects, identifiers starting with `TP`, and one ticket `TRL0-3` from the hand check.

### Where the skill came from

Made on 2026-11-22 and 23 with `house/from-existing.md` of `make-skill`, from the loose skill `plane` in the user's skills folder (itself split from `plane-protocol` the day before) and the Plane MCP server the user runs in OpenCode. The script was written by `claude-opus-5-5` from a written brief and checked by the session's main model. The server's registration is in the separate plugin `plane-mcp`.
