# Docs mirror

Run `scripts/sync_docs_wiki.py` (in this skill's folder) from the project root. It reads `docs/.wiki-sync.json` with this shape:

```json
{ "shelf": "<PROJECT>", "pages": {} }
```

For a new mirror, use the project's identifier and an empty page map. Commit the mapping with the docs. For an established mirror, restore missing state from Git or reconcile existing wiki page IDs before writing; an empty map duplicates pages.

Check changed docs and the mapping with `git status` and `git check-ignore -v -- <paths>`. No check-ignore output means the paths are not ignored; it does not prove they are tracked. Correct an accidental ignore rule when keeping these docs in Git is part of the task.

## Mapping and links

- Top-level `docs/*.md` goes to the Notes book.
- `docs/<dir>/*.md` goes to a book named from the directory, kebab case to Title Case.
- Books are matched within the project shelf. Names can repeat across shelves.
- Deeper nesting is skipped with a warning.
- Page title comes from the first H1, falling back to the file name. The H1 is left out of the page's body, because BookStack shows the title itself.
- Write file-relative Markdown links. Sync rewrites links to mapped docs into `{wiki address}/link/{page_id}`; anchors pass through and external links remain unchanged.

A path is the mapping key. The script does not infer renames: a moved file with no mapping at its new path becomes a new page, while the old page is left untouched. To preserve identity during a move, transfer the old mapping entry to the new relative path before syncing. The script then updates the existing page's book.

The keys keep the kind of slash the file already uses. Older mappings on Windows have backslashes (`plans\\roadmap.md` in the JSON); leave them as they are, since an older copy of the sync in another app reads the same file.

## Run and recover

```
python "<this skill's folder>/scripts/sync_docs_wiki.py" --dry-run
python "<this skill's folder>/scripts/sync_docs_wiki.py"
```

Review created, updated and unchanged counts and any warning. Missing local files produce warnings; the script never deletes wiki pages. Include any resulting mapping change with the documentation work. The mapping file is rewritten only when its content changed.

The script creates missing pages first and saves the mapping after each one, then rewrites links and pushes what differs. So a run that fails in the middle can be started again: pages made so far are on record.

The script replaced a PowerShell one on 2026-11-22. Used since then: see `TEST-RESULT.md` next to `SKILL.md`.

See [api.md](api.md) only if settings, direct page access, or reconciliation are needed.
