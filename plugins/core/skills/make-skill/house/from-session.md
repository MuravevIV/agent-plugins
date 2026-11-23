# Making a skill from a finished session

A session that got a task right has already paid for its mistakes. A fresh
agent will make the same ones unless they are written down. This file
shows how to capture the working path, the constraints and the pitfalls
from the current conversation in a form the next agent can follow without
having been here.

Work collaboratively by default: show the draft before saving it into a
skills folder. A skill is live from the next session on, and only the user
can say whether the pitfalls are recorded correctly. If the user says
"just do it", save without the review.

## Before writing

- **The task must be finished and checked.** Pitfalls are only visible in
  hindsight. A draft written mid-task records the path that later turned
  out wrong. Take notes during, write after.
- **Look for an existing home.** Check the project's skills folder, the
  user's global skills, and the project instruction file (`CLAUDE.md`,
  `AGENTS.md`). If something already covers this task, update it (see
  "Updating an existing skill") instead of creating a near-duplicate.
- **Ask whether one line would do.** If what the session taught fits in
  one line of the project instruction file, propose that line instead of
  a skill (`house/rules.md`, rule 1).
- **Make sure you can still see the mistakes.** Long sessions get
  summarized, and summaries keep the result and lose the wrong turns. If
  the early part is gone, read the transcript if the app keeps one, or ask
  the user which corrections they remember. Do not reconstruct pitfalls
  from guesswork.

## When the source is an old rules file

Sometimes there is no session, only a file of rules or notes that
someone wrote earlier and wants as a skill. Then skip step 1: there is
no winning path and no dropped attempt to sort out. Go to step 2 with
the file as the material, and keep these three things in mind.

- Add no fact. Reshape what the file says; do not fill gaps from your
  own knowledge, and say in the review note that nothing was checked
  against the real system.
- Tell the user what you were unsure about: versions the file leaves
  open, names that may belong to one project only, links that do not
  say what their label claims.
- A file gives no first test case. That comes from the next real task
  the skill is used on (`house/rules.md`, rule 2).

## Step 1: Three passes over the session

Do these in order, before writing anything.

1. **Winning path.** Separate the approach that worked from the attempts
   that were dropped. Only the working path becomes instructions.
2. **Constraints.** Collect every rule the user stated: versions, banned
   or required libraries, architecture decisions, limits on what the agent
   may do. These become prerequisites or rules.
3. **Pitfalls.** Collect every error, wrong assumption and invented API
   that needed correcting, including the ones the agent made, even though
   the final result is now right. The next agent starts with the same
   wrong instincts.

While you are at it, note two more things for later:

- **The test case this session is.** Write down the original request as
  the user made it, and what the right result turned out to be. This is
  the first real test case for the skill (`house/rules.md`, rule 2).
- **Steps that needed no judgement.** Commands or edits that ran the same
  way each time are candidates for a script (rule 4).

## Step 2: Choose the kind

| What the session taught | Write | Template |
|---|---|---|
| How to do a task: ordered steps toward one result | A procedure skill | `house/procedure-template.md` |
| How work in a domain should be done: standards, library usage, gotchas | A conventions skill | `house/conventions-template.md` |
| What a term means here, after the agent got it wrong | A glossary line in the project instruction file | Format below |
| More about a task that already has a skill | An update to that skill | "Updating an existing skill" |

One skill covers one repeatable unit of work or one domain. If the session
taught two unrelated things, write two. If you find yourself writing
ordered steps inside a conventions skill, that part is a procedure and
belongs in its own skill.

Glossary line format:

```markdown
- **<Term>**: <what it means in this project, one to three sentences>.
  Not to be confused with <the common wrong reading>.
```

## Step 3: Write the draft

- **Where.** The current project's skills folder (`.claude/skills/<name>/`
  or the app's equivalent). A skill meant for other projects or apps goes
  through testing first and then into a plugin (`house/rules.md`, "How far
  this skill has to go").
- **Name.** Kebab-case. A verb phrase for a procedure (`add-card-type`),
  the domain for conventions (`lua-ffi`).
- **Description.** State what the skill does and when to use it, in the
  words the user would use, including the situations that should bring it
  up. It is the only part the agent always sees, so it decides whether the
  skill ever loads.
- **Body.** Fill the matching template. Read `house/examples.md` for what
  good and bad sections look like.

Rules for the body, and why:

- **Write instructions as commands** ("Create", "Register", "Run"), with
  no session history. "First we tried X" teaches the next agent nothing it
  can act on.
- **Give the reason with each rule.** An agent that knows why can handle
  the case the rule did not foresee. A bare "never" cannot.
- **Generalize.** Replace names from this session with `<Placeholder>`
  values so the skill covers the category of task and not one instance.
- **Isolate.** No keys, no real user data, no absolute paths from this
  machine unless the skill is for this machine only.
- **Trim.** Cut what any model knows from training. Keep what was
  surprising, version-specific or decided by the user.
- **Show shapes, not code.** An example lists the input and which files
  change. Pasted implementation biases the next agent toward that exact
  code, and it goes stale.
- **Leave out empty sections.** A section with nothing real in it is
  noise. Never invent a pitfall to fill one.
- **Move bulk out.** Long tables or reference material go in
  `references/` files that the body points to.
- **Turn fixed steps into a script.** Steps that ran the same way with no
  judgement go into one script in `scripts/`, with the changing parts as
  inputs. Mark it "used once, on <what>" in the skill text until it has
  worked a second time (`house/rules.md`, rule 4).
- **Do not depend on an MCP server.** If the session reached an outside
  system through one, give the skill a script or command-line path as
  well (rule 5).
- **Promote costly pitfalls.** A pitfall that broke a build, lost data or
  cost more than about ten minutes becomes a rule in the main text, where
  it is read before the mistake and not after.

## Step 4: Check the draft

- A fresh agent could follow it with no access to this session.
- The description says when to use it, not only what it is.
- Every pitfall names the symptom and the fix.
- No secrets, real data or stray session paths.
- A procedure that changes files or state says how to undo a half-done run.
- No names that were coined during the session and never explained
  (`house/rules.md`, rule 7).

## Step 5: Review and save

Show the user the draft with a short note: what kind it is, where it will
be saved, and anything you were unsure about. Apply their corrections,
then save. Tell them it loads from the next session.

Then:

- If the skill stays in this project, offer a test and stop there if the
  user declines.
- If the skill is to be shared, continue with testing: `house/rules.md`
  for what is required, `SKILL.md` ("Running and evaluating test cases")
  for how. The request noted in step 1 is the first test case.

## Updating an existing skill

After another run of a task that already has a skill:

- Add the new pitfalls and rules.
- Change the steps only if the right approach changed.
- Remove existing content only when this session proved it wrong.
- Reread the description. If the scope moved, the description has to move
  with it or the skill stops loading when it should.
- A script marked "used once" that worked again in this session loses the
  mark.

## Undo

Delete the skill folder that was created, or revert the edits to the
existing skill or instruction file.
