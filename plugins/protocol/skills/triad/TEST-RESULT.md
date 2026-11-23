# Test result: triad

On names: the skill is `triad` in the plugin `protocol`, so the user types `/protocol:triad`. The short `/triad` alone did not load the skill in three small runs with Claude Code 2.1.330 on 2026-11-22. All runs below were made when the skill was a loose skill named `triad`, so `/triad` in this file is what was typed then. For part of 2026-11-22 it was called `protocol-triad` in a plugin `protocols`; that doubled the word in every app's menu and was undone the same day on the user's word. Nothing else in the skill changed with either rename.

## 2026-11-22, decision after the retests

- **Decision:** keep, as one file that the user loads by name. The user decided this on 2026-11-22. It replaces "shrink" from the first test below.
- **Why not shrink:** "shrink" answered the question "does the model find and open this skill by its description". It does not, in the case that counted. The user then said how the skill is meant to be used: it is a protocol, picked for a session by typing its name, never found by description, and not wanted as lines in a global instruction file. Loaded by name, the skill is always read, which was the one thing the seven lines had over it.
- **What was tested:** the skill in this folder, `SKILL.md` alone (about 1,050 words, description hidden with `disable-model-invocation: true`, no reference files, no grading script). Before that, the full version loaded by name. Both retests are written up at the end of this file.
- **Test cases:** cases 2, 4 and 5 of the first test, and one new case (7) in which the run makes the grading call to the outside model itself. All made up.
- **Who answered:** Claude Code 2.1.299 from the command line, model `claude-fable-5-2`, one run per case, skill loaded by putting `/triad` in front of the request.
- **Who graded:** script checks, then counts and facts read from the records. No model graded these runs. In case 7 the outside model `openai/gpt-6.2-sol` did the grading the case asks for.
- **With the skill:** all four runs followed the protocol; script checks 7 of 7. The grading call made by hand worked on the first call.
- **Without the skill:** not run again. The first test stands for it: 112 of 150 without, 139 of 150 with the full skill when it was found by description.
- **Not covered:**
  - No side-by-side run of the one-file version against no skill or against the full version. The four runs were looked at on their own.
  - Cases 1, 3 and 6 were not run on the one-file version, and no case more than once.
  - The judged expectations of the first test were not graded again by the outside model.
  - Copilot and Codex: the settings that hide the description are taken from their documentation and were not run.
  - The last wording change (the `--dir` option in the grading call) was made after the run that found it.
  - The section "When the conversation is summarised" was added on 2026-11-22 after all runs and is not tested. No test run here was long enough to be summarised. The first real session started with the skill is its trial. That session was summarised once on 2026-11-22, in Claude Code: the app put the whole skill text back by itself and the line was in the summary. The case where the text is lost has not happened yet.
  - The rule that a request naming the outside grader and the files counts as the yes for those files was added on 2026-11-22 on the user's word, after all runs, and is not tested. Case 7's request carried a plain yes, which is close to it.
  - The rule on sending material to the outside grader was changed late on 2026-11-22 on the user's word: material, source code included, may go to it without a yes per item, "since it already goes to Claude". What is asked before a job is the cost. Passwords, keys, machine addresses and personal details are still taken out. The earlier rule (a yes for each set of material) is the one the tests ran under; the new one is not tested.
  - On 2026-11-23, on the user's word, the manager stopped being a named model. It is the main session on whatever model the user chose, and it may hand work to a stronger model than itself. The rule "never hand work to your own model" became "never hand work to `claude-fable-5-2`", which costs the most. Every test here ran with `claude-fable-5-2` managing. How a session on another model writes briefs and checks reports under this protocol is not tested, by the user's choice.
  - The section "Review before a commit" was added late on 2026-11-22 on the user's word and is not tested, by the user's choice: when another loaded protocol has a judgement step before a commit (`trail` has one), the outside model reviews every change that alters behaviour. The cost is asked once per session. The figure "5 to 15 cents" per review is a guess from the one grading job run so far.
  - The section "With other protocols", the two lines that keep shared records with the manager and let an executor write up research, and the last sentence of "When the task ends" were added late on 2026-11-22 on the user's word, when the second protocol `trail` was made. None of it is tested, and no session has run with two protocols loaded yet.
  - Found on 2026-11-22, after all runs: every run of this skill's tests, on every side, also read the user's own global instruction file, because the workspaces lay inside the home folder. That file is about something else (use of the PC's graphics card), no answer mentions it, and all sides saw the same, so the comparisons hold. The side "without the skill" was still not a bare model. The runner refuses such a workspace now.
- **Where the full version went:** `..\triad-full\` holds it whole (`SKILL.md`, four reference files, `scripts/outside_grader.py`). Its self-tests in `..\tests\` still pass. Case 7 is kept out of `evals/evals.json` on purpose, because its request carries a yes for sending, so running all cases would send material out unasked; it is defined in `..\triad-workspace\single-file-test\build_single_test.py`.

## 2026-11-22, first test: the whole skill, found by its description

The files this block names (`references/`, `scripts/outside_grader.py`) now live in `..\triad-full\`.

- **Decision:** shrink. The rules that matter most work better as seven lines in the project's instruction file than as a skill. Keep a smaller skill for the grading work only. The change itself is not made yet; it waits on the user's word.
- **What was tested:** the whole skill as drafted on 2026-11-22 (`SKILL.md`, four reference files, `scripts/outside_grader.py`), against no skill, and against no skill plus the seven lines in `evals/instruction-lines.md` written into the project's `CLAUDE.md`.
- **Test cases:** 6, of which 0 real and 6 made up. Each is built on something that really happened in the trial; the input files are all made up. `evals/evals.json` says for each case what it is modelled on.
- **Where the real cases came from:** none are real. The patterns come from the one day of trial use in the author's own working session of 2026-11-21 and 2026-11-22.
- **Who answered:** Claude Code 2.1.299 from the command line, model `claude-fable-5-2`, three runs per case and side, 54 runs in all. Each run was a fresh project folder that could not see the user's own skills or settings.
- **Who graded:** script checks first (`evals/check_runs.py`, 66 of the 150 checks per side), then the outside model `openai/gpt-6.2-sol` through OpenCode for the rest. Sol saw the nine answers of a case together, under letters in random order. No Claude model graded.
- **With the skill:** 139 of 150 checks passed (93%). The skill was opened in 10 of 18 runs.
- **Without the skill:** 112 of 150 (75%).
- **Without the skill, with the seven lines:** 146 of 150 (97%).
- **What the difference was:** Both the skill and the seven lines fix what goes wrong without them: subagents started with no model named, briefs with no stop line, grading done by the same model without asking, expectations a literal grader trips over. The skill lost to the lines in one place: when asked to summarise five reports with subagents, the model never opened the skill (0 of 3 runs), so all five subagents ran on the manager's own expensive model with thin briefs. The lines are always read, so they cannot be skipped that way.
- **Would one line in the project instruction file do?** Yes, seven lines do. They are in `evals/instruction-lines.md`. In the three cases where the skill was opened every time (3, 4, 5) the two sides came out level: 85 of 87 with the skill, 83 of 87 with the lines. Sol ranked the skill's answers first in the two grading cases (4 and 5), so the skill's longer text still adds something there.
- **Not covered:**
  - No real case. All six were written by the same author as the skill and the lines, who knew what the skill says.
  - One answering model. Cheaper models as manager were not tried.
  - A small, empty project. In a real project with a long instruction file, seven more lines may get less attention than they got here.
  - Whether a better description would make the model open the skill for plain hand-off requests. Not tried.
  - No run got as far as sending material to an outside model, so the skill's script was only used up to the point where it stops and asks.
  - Sol could sometimes tell the sides apart, because some answers name the skill or "the rules in this folder".
  - Shell commands were limited to single `python` commands in all runs, the same for every side.

### Numbers per case

Checks passed out of all checks, three runs added together.

| Case | With the skill | Without | With the seven lines | Skill opened |
|---|---|---|---|---|
| 1 small job done by the manager | 18 of 18 | 18 of 18 | 18 of 18 | 0 of 3 (right: nothing to hand off) |
| 2 parallel summaries by subagents | 15 of 24 | 19 of 24 | 24 of 24 | 0 of 3 |
| 3 build handed to one subagent | 36 of 36 | 27 of 36 | 36 of 36 | 3 of 3 |
| 4 asked to grade three answers | 27 of 27 | 12 of 27 | 26 of 27 | 3 of 3 |
| 5 expectations for a literal grader | 22 of 24 | 15 of 24 | 21 of 24 | 3 of 3 |
| 6 notes from a cheap search | 21 of 21 | 21 of 21 | 21 of 21 | 1 of 3 |
| All | 139 of 150 | 112 of 150 | 146 of 150 | 10 of 18 |

Cases 1 and 6 show no difference between the sides. The model does those right on its own, so they prove nothing about the skill and can be dropped or made harder.

Average per run: with the skill 38 seconds and $0.59; without 40 seconds and $0.50; with the lines 43 seconds and $0.48. The prices are list prices; the runs drew on the subscription.

### What "shrink" would mean

1. The seven lines go where they are always read: the instruction file of each project that works this way, or the user's own global instruction file.
2. The skill keeps what seven lines cannot carry: the script that calls the outside grader, the notes on its traps, and the notes on writing expectations for it. Its description narrows to grading and outside-grader work, where the model opened it 6 times out of 6.
3. The parts about when to hand off, which model to name and what a brief holds leave the skill, because the lines cover them and the skill was not opened when they were needed.

Then test again: the smaller skill plus the lines against the lines alone, on the grading cases.

### Where the records are

The run records are kept by the author outside this repository: every run with its answer, the record of the run, the script checks and the outside model's grades, a review page, the exact text that went to the outside model for each case, and what it said with the letters resolved. The runs were made in a temporary folder outside any project, because Claude Code reads the instruction files of parent folders and a project's own instructions would leak into every side.

Cost of the test: 54 runs and 2 trial runs at about $29 list price; the outside grading cost $0.40.

## Retest with the skill loaded by name (2026-11-22)

The user pointed out that this skill is a protocol: the user picks it for a session by typing its name, and the model is not meant to find it by its description. The test above judged it loaded by description, so "shrink" is a verdict on that way of loading only. The decision line above is left as it was until the user decides.

What changed in the skill: `disable-model-invocation: true` in the header (Claude Code then keeps the description out of the model's context; the user loads the skill with `/triad`), `agents/openai.yaml` for Codex (`$triad`), models named by provider and version, and the grader reachable as a subagent where the app offers the model.

What was run: case 2 only, the case the skill lost because it was never opened. Two runs, `claude-fable-5-2`, the prompt sent as `/triad <the case's prompt>` (runner option `--load-by-name`). Script checks only. Nothing went to an outside grader, so the six judged expectations of this case were not graded again.

| | Earlier, found by description (3 runs) | Loaded by name (2 runs) |
|---|---|---|
| Skill text reached the model | 0 of 3 | 2 of 2 |
| Subagent calls naming a model, none the manager's own | all | 10 of 10, all `haiku` |
| Briefs with a "Done looks like" part | not counted | 10 of 10 |
| Briefs with the stop line, word for word | not counted | 10 of 10 |
| Final answer closes with a note on how the split went, naming the model | not counted | 2 of 2 |
| `summary.md` written | 3 of 3 | 2 of 2 |

The last four rows were counted by text search in `handoffs.md` and by reading the two answers. They are counts, not grades.

Two short trial runs on the Haiku model first showed that a prompt starting with `/triad` loads the skill in `claude -p`, and that the model no longer sees the skill's name or description in its list.

Cost: two runs, $1.19 list price, 97 seconds together. The trial runs cost under one cent.

Records: `..\triad-workspace\retest-by-name\`.

Not known: how Copilot and Codex treat the same settings (taken from their documentation, not run); whether the judged expectations hold when graded by the outside grader.

## Test of the one-file version (2026-11-22)

The one-file version is now `SKILL.md` in this folder (it was `..\triad-single\SKILL.md` when tested): the same protocol in a single file of about 1,000 words, with no reference files and no grading script. The grading call through OpenCode is written out in the file and made by hand.

What was run: four runs on `claude-fable-5-2`, skill loaded by name, one run per case, only the side with the skill. Cases 2, 4 and 5 are the ones from the first test. Case 7 is new: the request already holds the user's yes for sending, so the run has to make the OpenCode call itself. The user said yes to sending case 7's five made-up files to the outside grader.

| Case | What the run did | Script checks | Cost | Time |
|---|---|---|---|---|
| 2, summaries by subagents | 5 hand-offs, all naming `haiku`; all 5 briefs hold the done line, the "do not build" line, the stop line word for word and what to report; `summary.md` written; closing note names the model | 2 of 2 | $0.59 | 45 s |
| 4, asked to grade three answers | did not grade and did not pick a winner; counted words by script; listed what would be sent; spotted the login in `b.md`; offered the three other ways; sent nothing | 2 of 2 | $0.34 | 19 s |
| 5, expectations for the grader | rewrote the list with one thing per item, no brackets, examples marked in words, the word limit moved to a script check | 2 of 2 | $0.39 | 37 s |
| 7, grading call made by hand | wrote the grader's agent file with all tools denied, word for word from the skill; message starts with "Task:"; answers relabelled A, B, C in a drawn order, file names gone; login replaced by `[LOGIN REMOVED]` before sending; one call, the grader answered as `outside-grader · gpt-6.2-sol`; the final answer maps the labels back correctly (a 5 of 5, b 1 of 5, c 5 of 5), marks the grader's pick between a and c as opinion, and closes with the split note | 1 of 1 | $0.67 | 81 s |

These are counts and facts read from the records, not grades.

One thing went wrong and is fixed in the file: "run in that folder" could not be done as written, because the test's shell rules refuse a change of folder joined with reading a file. The run found the `--dir` option of `opencode run` on its own. The file now says `--dir` outright, and tells the manager to check that the reply opens with `> outside-grader`. That new wording has not been run again. Six tool calls were refused in case 7 before it got there.

What the hand-made call lacks next to the grading script: no saved record of what was sent unless the manager keeps the message file, no fixed reasoning setting for the grader, no retry, and the cost of the grader's call is not shown.

Cost: four runs, $1.98 list price, about 3 minutes together. The grader's one call was not measured (a few cents).

Records: `..\triad-workspace\single-file-test\`. The agent file and the message that was sent are in `eval-7-grading-sent-by-hand-after-a-yes\grading-call\`. Case 7 is defined in `build_single_test.py` there.

Not known: whether the one-file version holds on cases 1, 3 and 6 (not run); anything beyond one run per case; how it does against the full skill side by side, since both were only looked at on their own.
