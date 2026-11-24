---
name: plane
description: Read and change tickets, states and comments in the user's Plane tracker. Use whenever a Plane ticket or a key such as PDX-1 comes up.
---

# Plane

How to reach the user's Plane tracker, and what is particular about it.

## Two ways in

Use the first one that is there.

1. **The tools of a Plane MCP server**, when this session has them.
2. **The script in this skill's folder.** It needs no server:

   ```
   python "<this skill's folder>/scripts/plane.py" <command>
   ```

| Command | What it gives or does |
|---|---|
| `projects` | Every project: identifier and name |
| `states PROJECT` | The project's states and the group each is in |
| `list PROJECT [--open] [--group GROUP ...]` | All tickets, every page. `--open` leaves out completed and cancelled |
| `show KEY` | One ticket with description, parent, child tickets and comments |
| `create PROJECT --name TEXT [--parent KEY] [--group GROUP] [--description TEXT or --description-file FILE]` | A new ticket |
| `update KEY [--name TEXT] [--group GROUP] [--parent KEY] [--description TEXT or --description-file FILE]` | Changes a ticket |
| `comment KEY (--text TEXT or --file FILE)` | Adds a comment |
| `comments KEY` | The ticket's comments |
| `attachments KEY`, `download KEY ATTACHMENT_ID --out FILE` | Lists a ticket's attachments, saves one |

- `PROJECT` is an identifier such as `PDX`, `KEY` a ticket key such as `PDX-12`.
- `GROUP` is one of `backlog`, `unstarted`, `started`, `completed`, `cancelled`. The script picks the project's state of that group.
- The answer is JSON. Every ticket comes with its `url`.
- For longer text, write it to a file and pass `--description-file` or `--file`.
- `create` and `comment` are not safe to repeat blindly: if one fails after Plane may have acted, look at the ticket first.

The script finds Plane's address, the workspace and the key in the environment variables `PLANE_BASE_URL`, `PLANE_WORKSPACE_SLUG` and `PLANE_API_KEY`, or in the file `~/.config/agent-plugins/plane.env`, which holds the same three as `NAME=value` lines. An older place is still read after those: the `plane` entry of the OpenCode config in the home folder. When nothing is found, the script says which file to create. It never prints the key. Keep the key out of your own output too.

## What is particular here

- Infer the project from the active ticket or the repository before asking, and reuse it.
- Work with a state's group, not its display name.
- Descriptions and comments take Markdown as it is, even though the fields are named `description_html` and `comment_html`; HTML shows up escaped. Seen on the user's self-hosted Plane.
- In chat, write a ticket key as a link to the ticket, using the `url` the script gives: [PDX-1](http://localhost:8090/my-workspace/browse/PDX-1/). The form is `{address}/{workspace}/browse/{key}/`. Bare keys are fine in commits and code.
- Plane allows a key a limited number of calls per minute. The script waits and tries again by itself; do not start many calls at once.
- A link from a ticket to a wiki page uses the page's permalink. The wiki is covered by the `bookstack` skill.
- Uploading an attachment is three calls by hand; read [references/attachments.md](references/attachments.md) for that, and for screenshots in general.

This skill only says how to reach Plane. The user's rules for working on a ticket are in the protocol `protocol:trail`. Only the user loads a protocol, by typing its name; never load it yourself. If you are asked to implement a ticket and that text is not in view, tell the user so in one line and ask whether they want to load it. A plain request to change a ticket, such as marking it done or adding a comment, needs no such note: just do it.
