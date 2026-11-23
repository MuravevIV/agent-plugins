# Test result: trail

## 2026-11-22, first test: against the old skill it was split from

- **Decision:** keep (the user's decision, after this test)
- **What was tested:** five made-up cases, each answered once with `trail` loaded by name and once with the old skill `plane-protocol` loaded by name. Ten runs of `claude-fable-5-2` through Claude Code 2.1.330, each in its own small git repository and its own throwaway project in the user's local Plane with the same ten starting tickets. A script read back what happened from Plane, from git and from each run's steps. No model graded.
- **Result:** `trail` passed 23 of 24 checks, the old skill 19 of 24. Cost $6.30 for the ten runs ($2.97 and $3.33), about a minute per run that did work.
- **Not covered:** see "Limits" below. The largest gaps: no side without any skill, the BookStack half, and two protocols loaded together.

### Per case

| Case | With `trail` | With the old skill |
|---|---|---|
| 1. A small bug, no ticket named | 6 of 7. Ticket under the epic "Counting", failing test first, commit with the key, completion comment, Done | 6 of 7. The same |
| 2. "What should I work on next?" | 5 of 5. Tickets 7, 9, 5, 8, 6 in that order, then a question; nothing changed | 5 of 5. The same |
| 3. A change that fits no epic | 3 of 3. Stopped, proposed the epic "Build and CI", changed nothing | 0 of 3. Made a ticket with no parent, did the work, committed |
| 4. "Which files use the re module?" | 3 of 3. Named the three files; no ticket, no page | 3 of 3. The same |
| 5. A bug with a link to another tracker | 6 of 6. Full course in Plane; said the other ticket was not touched and offered to show the text first | 5 of 6. Full course, but the commit does not name the ticket's key |

### What this says

- The split lost nothing. On every check the old skill passed, `trail` passed too.
- Two of the rules added on 2026-11-22 showed up: asking before a new epic (case 3) and the ticket's key in every commit (case 5; the old text did not ask for it and got it in one run of two).
- "Before the first edit" is not held. In case 1 both sides created the ticket a step or two after the first edit: the run wrote the failing test and the ticket in the same batch of steps. In case 5 `trail` had the order right. One of two.
- The fence was not really tried. Neither side attempted to write to the other tracker, and its address (`jira.example.invalid`) cannot be reached, so the case shows what the answers say and no more. The old skill, without any fence, also left it alone.
- Cases 2 and 4 show no difference between the sides. They guard against a regression; they prove nothing about what was added.
- In a run without a person (`claude -p`) the model still stopped and asked about the epic. It did not read such a run as "without the user at hand".

### Changed after the test

- "Before the first edit" was tightened on the user's word: the ticket is found or made in a step of its own, and a test file counts as an edit. Case 1 was then run once more with `trail` (`iteration-2`): 7 of 7, the ticket came before the first edit. One run, $0.87. That is one good run after one bad one, so it shows the line can work and no more.
- The user chose to keep the throwaway projects in Plane. With the rerun there are thirteen.
- A review step was added to "Finishing", with a fourth kind of step, judgement. It is done only when another loaded protocol provides a reviewer (`triad` does, with the outside model); with `trail` alone there is no review. Not tested, by the user's choice.

### Limits

- All five cases are made up, on one tiny repository. One run per case and side.
- The comparison is with the old skill, loaded by name, which is stronger than the old skill found by its description. There was no side without any skill, so this does not show that the protocol is needed, only that the new text does at least what the old one did.
- The repositories had no BookStack mirror. The rule that findings are written down, the major and minor test for research, and everything about pages are untested.
- `trail` and `triad` together: not run. A run starts with one skill name.
- Three checks go by the wording of the answer (ends with a question, proposes an epic, says the other tracker was left alone). The script looks for words; the quotes are in each run's `grading.json`.
- The runs could use `curl`, `git` and `python`, one command at a time. Chained commands were refused 18 times across the ten runs, about the same on both sides.
- Plane allows a key a limited number of calls per minute. With two runs at once it answered "too many calls"; the runs were then made one at a time.

### Where the records are

- `C:\make-skill-runs\trail\iteration-1\`: every run with its steps, answer, `checks.json` and `grading.json`; `benchmark.json`; the review page is `C:\make-skill-runs\trail\trail-review.html`. The folder is outside any project on purpose (see `house/testing.md` in `make-skill`).
- The Plane key is in none of these files (searched for on 2026-11-22).
- The test's own material is in `evals/`: `evals.json`, the small repository under `files/repo/`, `setup_case.py` (prepares a run: git repository, Plane project, tool skills), `plane_api.py` and `check_runs.py`. All three scripts were used once, on this PC.
- Left in the user's Plane: thirteen throwaway projects whose identifiers start with `TR` (`TRL0` and `TR<case><N or O>1`, one of them half filled). The user chose to keep them.

## 2026-11-22, before the test

### Where the text came from

- Most of it was moved, nearly word for word, from the user's earlier loose skills `plane-protocol` and `bookstack-docs` (kept whole by the author, outside this repository). Nothing in it was checked against the real Plane or BookStack while moving it.
- Added on the user's word the same day, in conversation: every repository change has a Plane ticket; findings are written down without being asked; the test for major and minor findings; a new epic is asked for first unless the session runs without the user at hand; the protocol writes only to the local Plane and BookStack; the sections "What kind each step is" and "With other protocols".

### What the writer was unsure about

- "Autopilot" is the user's word. The text reads it as: the app's autopilot or auto mode, or the user said to go on without asking. How a run can tell it is in such a mode differs per app and was not looked up.
- "Stop and ask if the skill points at something that is not the user's own local instance": the text gives the model no way to tell, beyond what the tool skills say.
- The paragraph on visible editor changes came from the old skill and may belong to one project only.
- The state names `started`, `unstarted`, `backlog` and the ladder task, feature, epic are Plane's.
- No session has run with this protocol and `triad` loaded together.
