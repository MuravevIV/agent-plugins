# Procedure skill template

For a repeatable task with ordered steps. Copy the block, fill it, and
delete every section that has nothing real in it. Only the frontmatter,
the opening lines and Steps are always present.

````markdown
---
name: <verb-phrase>
description: <What the task is and when to use this skill, in the user's words. Name the requests and situations that should bring it up.>
---

# <Task name>

<One or two sentences: what this produces, and the one thing about it
that is not obvious.>

## Before you start

- <Hard blockers only: what must exist, what the user must supply.>
- <What to read first, for example one existing instance of the same thing.>

If any of these cannot be met, ask before step 1.

## Mode

<Collaborative | Autonomous | Supervised>: <one line on what that means
for this task>. "Just do it" from the user means run through without
pausing. "Walk me through it" means confirm each step first.

## Steps

1. <Command, with paths and placeholders.>
2. <Command.>

**Checkpoint: <label>.** Show <what>. Continue when <how the user judges
it correct>.

3. <Command.>

## If things differ

- If <condition>, <what changes in the steps>.

## Rules

- <Rule>, because <reason>.

## Pitfalls

- **<Symptom, or the tempting wrong move>.** <The fix, one sentence.>

## Done looks like

Input: "<a typical request>"

Output:
- `<path>/<Name>.<ext>`: new
- `<path>/<Registry>.<ext>`: one line added

## Check

- [ ] <How to confirm it worked: a command, a visible result.>

## Undo

1. <What to delete or revert if the run stops halfway.>
````

## Filling it in

### Mode

Pick the lightest mode the risk allows. Write the meaning out in the skill
itself, because the agent that reads it later has not seen this file.

| Mode | The agent | Fits |
|---|---|---|
| Autonomous | Runs every step without stopping | Well understood, low risk, fully reversible |
| Collaborative | Pauses at the listed checkpoints | Design choices, ambiguity, medium risk |
| Supervised | Proposes each step and waits for a yes | Irreversible, high risk, or unfamiliar ground |

### Checkpoints

Place one where a wrong turn gets expensive:

- after files are generated and before they are wired together
- after an action that is destructive or hard to reverse
- where a design choice has more than one valid answer
- before the final check

Each checkpoint says what to show and how the user decides it is right.
An autonomous skill has none. A supervised skill treats every step as one,
so it needs none listed.

### Steps

Only the path that worked. Failed attempts appear as one-line pitfalls or
not at all. If "If things differ" grows past about five entries, the skill
covers more than one task: split it.

### Rules and pitfalls

A rule is something to know before acting. A pitfall is a trap with its
fix. Promote a pitfall to a rule when it broke a build, lost data or cost
more than about ten minutes. State rules plainly and attach the reason.

Record the agent's own mistakes too: a wrong API signature, a guessed
package name, a version it assumed. They are the most likely to repeat.

### Done looks like

One example, two at most. It shows scope: the request and which files
appear or change. No implementation code.

### Undo

Needed whenever the task changes files or state, and most of all for
autonomous skills, where nobody is watching the run. For a purely additive
task one line is enough: delete the created files and revert the modified
ones.
