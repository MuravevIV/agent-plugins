# Local Plane attachments

Use attachments when they clarify the requested bug or expected UI. Screenshots supplement the issue text. Prefer available tools; otherwise use configured Plane credentials from the MCP configuration/environment or an existing project `.mcp.json`. Do not print tokens.

Issue attachment base:
`{base}/api/v1/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/issue-attachments/`.
Authenticate with `X-API-Key: <token>`.

- List: GET the attachment base.
- Download: GET `{attachment_base}{attachment_id}/`. It can redirect to a signed asset URL; follow the redirect without forwarding the API key to another origin. Use the available image viewer for saved screenshots.
- Upload: POST the attachment base with `{"name","type","size"}`, using the exact byte count. Multipart POST to returned `upload_data.url` with all `upload_data.fields` and the file last. After successful upload, PATCH `{attachment_base}{asset_id}/` with `{"is_uploaded":true}`. Unconfirmed uploads are hidden from listings.
- DELETE `{attachment_base}{asset_id}/` only for an authorized removal.

These procedures were recorded against the local installation on 2026-08-21. Its self-hosted CE v1.4.1 Pages API returned 404 at that time; do not assume newer installations have the same limitation. Use descriptions/comments and attachments for tracker context, with long-form project docs in Git/BookStack as configured.
