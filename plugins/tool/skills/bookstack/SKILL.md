---
name: bookstack
description: Manage the local BookStack wiki and docs mirrors, including edits to projects with docs/.wiki-sync.json and workspace operations documentation.
---

# BookStack

The user's wiki is a BookStack they host themselves, usually at `http://localhost:8091`. Git is the source of truth for repo-coupled documentation; the Infrastructure shelf holds workspace operations documentation.

For a configured project, keep plans, investigations, and code/ticket-linked docs in `docs/`, then sync after changes. Follow an explicit destination in the user's request. Do not turn an unrelated documentation edit into wiki setup.

The sync is one script in this skill's folder, run from the project's root:

```
python "<this skill's folder>/scripts/sync_docs_wiki.py"
python "<this skill's folder>/scripts/sync_docs_wiki.py" --dry-run
```

`--dry-run` changes nothing and prints what a real run would create and update.

- For a mirror, bootstrap, move, or sync failure, read [references/sync.md](references/sync.md).
- For direct wiki edits, the wiki's address and token, or Infrastructure operations docs, read [references/api.md](references/api.md).

A page can carry a `Tickets:` line right under its H1, listing Plane keys as links: `Tickets: [PDX-3](http://localhost:8090/my-workspace/browse/PDX-3/), ...`. The line lives in the Markdown in Git, not in BookStack comments or tags, so it syncs with the page. When to add it is part of the user's protocol `protocol:trail`; how to reach Plane is in the `plane` skill.

Preserve `docs/.wiki-sync.json`: it contains the shelf and page identities, and losing it can create duplicates. A missing mapping in a previously mirrored project needs recovery, not an empty replacement.

Complete a requested sync by checking the script's result and saved mapping. Fix failures caused by the requested change and retry when the state is known. If the wiki is unavailable or a partial write leaves page identity uncertain, preserve local work and report what remains.
