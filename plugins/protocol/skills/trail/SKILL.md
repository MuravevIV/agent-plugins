---
name: trail
description: The user's working protocol for ticketed work in the local Plane and BookStack, from picking a ticket to closing it, with ticket, commit and wiki page linked to each other. Loaded by name only, when the user picks it for a session.
disable-model-invocation: true
---

# Trail: ticket, work, proof, record

The user picked this protocol for the session by typing its name. It
applies until the session ends. Work leaves a trail: a ticket in Plane,
a local commit and, where something was learned or decided, a page in
BookStack, each pointing at the others. Tickets and pages are made
without being asked.

This text holds the rules. Plane and BookStack here always mean the
user's own local instances, the ones the tool skills `plane` and
`bookstack` point at. Those skills hold the addresses, credentials,
field formats and the sync script. Open them when you need those facts.

## Only the local Plane and BookStack

Tickets and pages made on their own must never land where other people
read them. So:

- This protocol writes to two places only: the local Plane and the
  local BookStack.
- It never creates, changes or comments on anything in another tracker
  or wiki. A company's Jira or Confluence are examples.
- Sending results to such a system is a separate request of the user's,
  each time. Show what would be sent and wait for the yes.
- A ticket key or a link from another system is something to read about
  when the user asks. It is never a place to write.
- If the `plane` or `bookstack` skill is missing, or points at
  something that is not the user's own local instance, stop and ask.

## How far a request goes

- A request to find or list work ends with candidates.
- A request to implement runs through verification and the completion
  record. Do not stop for a review of a first draft.
- An implementation request includes the full course: the ticket, its
  updates, the completion comment and the local commit.

## Every repository change has a ticket

- No change to a repository without a Plane ticket, however small. A
  typo fix has one too. Every commit names its ticket's key.
- Find the ticket or create it before the first edit, in a step of its
  own. A test file counts as an edit, so the failing test also comes
  after the ticket. A small change that belongs to the ticket in hand
  rides on that ticket.
- A new ticket goes under the epic that fits. Create it without asking
  and tell the user in one line, with the linked key.
- When no epic fits, a new epic is needed. Stop and ask first, showing
  the name you propose. When the session runs without the user at hand
  (the app's autopilot or auto mode, or the user said to go on without
  asking), create the epic and report it afterwards.
- A repository with no project in Plane: ask once whether to create
  the project or to work without Plane. Without it, the ticket steps of
  this protocol are skipped; say so.

## Major and minor findings

One test, used for tickets and for docs alike.

- Major: later work or a decision will stand on it, or finding it again
  would cost more than one quick search.
- Minor: a lookup anyone can repeat in a minute, for example listing
  the classes that use a library.
- Major research gets its own ticket, and that ticket is done when its
  BookStack page is written. Minor research gets no ticket and no page; at
  most a line in the completion comment of the ticket it served.

## Writing down what was found

- Major findings, and what was settled in discussion with the user, go
  into the project's docs and are synced to BookStack without being
  asked. This includes what was learned while implementing a ticket.
- Update a page that fits before making a new one.
- Write at the end of a task, not on every turn.
- Say in the page what was checked and what is only a lead.
- Where the project has its own rules for docs, those win.
- A project with no BookStack mirror set up: ask once whether to set
  it up or to keep the docs in Git only.

## Picking work

- Take the project from a ticket key the user mentioned, then from the
  repository, then from matching projects. Ask only when the ambiguity
  changes which project or task would be acted on.
- Leave out completed and cancelled items unless asked. Sort the rest
  by:
  1. Granularity: task, feature, epic.
  2. Within granularity, state group: `started`, `unstarted`, `backlog`.
  3. Within a group, the ticket key by its number, then
     sequence, order, name.
- Prefer explicit type and parent data. Where there is none, judge
  granularity from the deliverable. Leave remaining ties as ties; do
  not invent importance.
- Show up to five candidates, each as a linked key plus title. Ask for
  a choice unless the user already chose or told you to pick the next
  one. Accept full keys, numbers that can mean only one ticket, or a
  pick from the list you showed.
- For an epic, work through its features and tasks. Break work down
  only within the scope asked for. A feature with tasks: pick from
  those tasks. A feature without children can be implemented directly
  when it is a concrete deliverable that can be tested.
- Do not cap authorized, sustained work at one session's size.
- Keep the state of a planning container (epic, feature) separate from
  the item being implemented. When the user handed you the selection or
  the breakdown, go on within that; do not add a selection round.

## Doing the work

- Read the chosen item, the parent context that matters, and the code
  and docs its acceptance criteria need. Leave unrelated changes in the
  worktree alone. Move the item to the project's `started` state.
- Tests first for behavior changes: pick a meaningful regression test,
  run it to see the expected failure, implement, run the affected tests
  again. Choose the test layer from the repository's conventions
  without asking about routine test design.
- Unit tests for isolated behavior; integration tests for registration
  or contracts between components; runtime or manual fixtures where
  behavior depends on an IDE or an outside service. For prose-only and
  other low-impact edits with nothing to test, use a direct check
  instead of inventing a failing test.
- Fix failures the requested change caused. A failure of the
  environment is not a regression test failing correctly: diagnose it,
  use another fitting check, and report the limit. Widen verification
  when changed contracts or failures call for it. Once the relevant
  checks pass, go on to completion; do not repeat them.
- For visible editor changes, keep a focused sample or visual fixture
  when it helps the user verify. Keep it valid under the project's
  checker, add brief instructions for trying it, and follow the
  project's naming.

## Docs and links

- Follow a destination the user names outright.
- Changed docs go through the `bookstack` skill. Run the BookStack
  sync before the final local commit so the changed page mapping is
  part of it.
- A ticket's description links its related BookStack pages (plan,
  investigation, results) by permalink. A project description links
  the project's overview page, an epic links its plan, and a child
  links the page for its part, or the epic's plan when it has none.
- A doc written for or about tickets carries a `Tickets:` line right
  under its first heading, with each key as a link. The line lives in
  the Markdown file in Git, so it syncs with the page. Add keys when
  tickets are created after the doc.

## Finishing

In this order:

1. Finish the implementation and the required verification.
2. Write down what was found, and sync the docs.
3. Have the change reviewed, but only when another loaded protocol
   provides a reviewer. Hand it the change with the ticket's title and
   description, and deal with what comes back before going on. With no
   such protocol loaded there is no review; go on.
4. Look over what changed and stage only the task's files.
5. Make a concise conventional local commit that names the ticket's
   key. Do not amend or push unless asked.
6. Post a brief completion comment on the ticket: changes, checks, the
   commit, and the BookStack pages this work created or changed, by
   permalink. When the change was reviewed, say who reviewed it and
   what came of it. Add a newly created page's link to the ticket's
   description, and the ticket's key to the page's `Tickets:` line.
   When another loaded protocol asks for a closing note on the task,
   that note goes into this comment too.
7. Move the ticket to Done.

Then report to the user: the commit, the verification, and any material
work that remains.

If the implementation, a required check or a required sync is blocked:
keep the finished work, leave the ticket In Progress, and record the
blocker on the ticket when you are allowed to comment. Do not mark it
Done and do not call a partial result complete.

## What kind each step is

A protocol that splits work between agents decides by kind who may do
a step. This protocol only names the kind.

| Step | Kind |
|---|---|
| Showing candidates, asking for a choice, asking about a new epic, the final report | Talking to the user |
| Creating a ticket or an epic in Plane; a ticket's state, description and comments | Shared record |
| The BookStack sync; staging and the commit | Shared record |
| Reading, implementing, testing | Work |
| Writing or updating a docs page | Work |
| The review before the commit | Judgement |

## With other protocols

The user may load more than one protocol in a session. All of them
apply.

- Where two of them disagree, the stricter one wins. When you cannot
  tell which is stricter, ask the user.
- An agent you hand work to sees none of the protocols. Put the rules
  that apply to its piece into its brief, for example "do not touch any
  tracker or wiki, do not commit".
- Each protocol keeps its own line in a summary. Adding yours never
  removes another's.

## When the conversation is summarised

A long session gets summarised to free space, and this text can be lost
with it. The protocol still applies.

- If you write the summary, put this in it, on a line of its own, next
  to the line of every other loaded protocol. In place of `<path>` put
  the full path of this file as you saw it when the protocol was loaded
  (the skill's base directory plus `SKILL.md`):

  ```
  protocol:trail is active. Its text is the file <path>. If the text is not in view, read that file again and tell the user in one line that you did.
  ```

- After a summary, check that you can still see this whole text, down to
  the section "With other protocols". If you cannot, read this file
  again before any other work, and tell the user in one line that you
  did. The user picked this protocol for the session already, so
  reading its text again is not loading a protocol on your own.
- Ask the user to type the skill's name again only when the file cannot
  be found or read. Say that in one line, and do not go on from memory.
