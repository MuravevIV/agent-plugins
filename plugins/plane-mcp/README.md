# plane-mcp

Registers the Plane MCP server and nothing else. It is the faster path
to Plane for places where MCP servers are allowed. The skill
`tool:plane` works without it, through its own script.

## What it needs

- Node.js with `npx`. The server is the package
  `@makeplane/plane-mcp-server`, started as
  `npx -y @makeplane/plane-mcp-server stdio`. The first start downloads
  it.
- Four environment variables, set by the user. The plugin holds no
  value of its own:

  | Name | What it is |
  |---|---|
  | `PLANE_API_KEY` | The key. Keep it out of files in this repository |
  | `PLANE_WORKSPACE_SLUG` | The workspace's short name |
  | `PLANE_BASE_URL` | Plane's address, for example a local one |
  | `PLANE_API_HOST_URL` | The address of Plane's API, usually the same |

## Files

- `.mcp.json`: read by Claude Code. It takes the four values from the
  environment (`${NAME}`).
- `mcp.json`: the same server in the form GitHub Copilot's newer plugin
  format asks for.

## What is not checked (2026-11-22)

- The server was never started from this plugin. The command and the
  four names come from the user's working OpenCode setup.
- On Windows, Claude Code may need the command wrapped as
  `cmd /c npx ...`. Not tried.
- Copilot's documentation does not say that `${NAME}` is filled from
  the user's environment inside a plugin. If it is not, the server
  starts without its settings there.
- Codex's documentation is unclear on how a plugin declares a local
  server. Nothing here was written for Codex beyond the plugin's own
  description files.

## Install

From the local marketplace of this repository, in Claude Code:

    /plugin install plane-mcp@agent-plugins
