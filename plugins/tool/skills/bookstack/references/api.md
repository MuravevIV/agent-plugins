# BookStack API and settings

API base: `{wiki address}/api/`, on the user's machines usually `http://localhost:8091/api/`.
Authentication: `Authorization: Token <id>:<secret>`.

The sync script and any direct call take the address and the token from the same place, looked up in this order:

1. The environment variables `BOOKSTACK_URL`, `BOOKSTACK_TOKEN_ID` and `BOOKSTACK_TOKEN_SECRET`.
2. A file named by `BOOKSTACK_ENV_FILE`.
3. `~/.config/opencode/playbooks/install-bookstack/.env`, where the user's installation keeps them.

In a file the names are `APP_URL`, `API_TOKEN_ID` and `API_TOKEN_SECRET`, one `NAME=value` per line. Read only the needed values and keep them out of logs and reports.

Pages accept raw `markdown` on create/update. BookStack trims trailing newlines, so compare content with trailing whitespace removed.

Workspace deployments, upgrades, and tracker/wiki stack operations belong on the Infrastructure shelf by default. Existing installation details are in its “BookStack Deployment” page. Repo-coupled docs stay in the repository with a mirror; see [sync.md](sync.md).
