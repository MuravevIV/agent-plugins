---
name: phrases
description: 'Procedures the user starts by saying a set phrase. Use whenever the user says one of these phrases: "autopilot preflight".'
---

# Phrases

Each section below is a procedure the user has written down once. When the
user says its phrase, follow that section. The phrase may come inside a
longer message; the rest of the message is context for the procedure.

All procedures are in this one file on purpose: the skill's other files sit
outside the user's project, and reading them can need a permission that an
unattended session does not have.

To add a phrase: add a section here whose heading is the phrase, and add
the phrase to the list in the description at the top.

## autopilot preflight

Said by the user before leaving you to work alone. Goal: every question the
work will raise is asked now, so the run needs no one. Change nothing during
preflight; only read.

### Before the run

1. **Scope.** Work out what the run covers. If the context says it, propose
   that: with `protocol:trail` loaded, the open tickets under the epic in
   focus, else all open tickets of the project. Otherwise ask. Show the
   items it covers.
2. **Open questions.** Read through the items and collect every point the
   work would stop for: unclear requirements, a choice between approaches,
   a new epic, a download or install, sending anything outside, spending
   money, deleting anything. Settle what the sources or the project's
   conventions already answer, and list those as assumptions; do not ask
   them.
3. **Time quota.** Estimate each item, add them up, add about a third on
   top, and round up. Offer that as the default, with a shorter and a
   longer choice.

Ask every question with choices and your proposed answer first, up to four
per round.

4. **The plan.** When all questions are answered, print the plan:
   - the items in the order you will take them,
   - the answers given and the assumptions taken,
   - the time quota,
   - what makes the run stop early.

   End it with this line, on its own:

   > Type **go** to start.

5. **Start only on "go".** Start when the user's reply is the word "go",
   in any mix of upper and lower case, with nothing else. Any other reply
   is not a start: take it as a change, update the plan, print it again
   with the same last line, and wait.

### During the run

- Note the time at "go"; the quota counts from there.
- The preflight answers are the user's yes for those points only.
- A question nobody foresaw: if the safe choice can be undone, take it and
  note it. If not, skip that item, note why, and go on. Never wait.
- Check the time at the end of each item. At the quota, stop at the next
  safe point and keep all work.
- End with: what was done, what was skipped and why, the questions that
  came up, the assumptions taken, time used against the quota.
