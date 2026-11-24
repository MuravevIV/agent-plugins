#!/usr/bin/env python3
"""Read and change tickets in a self-hosted Plane tracker through its REST API.

Made for AI coding agents that have no Plane MCP server. Every command prints JSON on standard output. Failures go
to standard error with exit code 1; wrong usage exits with code 2.

Settings, first found wins for each value:
  1. the environment variables PLANE_BASE_URL, PLANE_WORKSPACE_SLUG, PLANE_API_KEY
  2. the file named by PLANE_CONFIG_FILE
  3. ~/.config/agent-plugins/plane.env
  4. ~/.config/opencode/opencode.json (an older place, still read)
A file holds either three lines of the form NAME=value, or JSON; in JSON the values are taken from the dict
that holds PLANE_API_KEY, wherever it is nested, and comments and trailing commas are allowed. The API key is
never printed.

When Plane answers 429 (too many calls per minute), the tool waits PLANE_RETRY_WAIT seconds (default 20) and tries
again, up to PLANE_RETRY_COUNT times (default 8).

Python 3.9 or later, standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

NAMES = ("PLANE_BASE_URL", "PLANE_WORKSPACE_SLUG", "PLANE_API_KEY")
GROUPS = ("backlog", "unstarted", "started", "completed", "cancelled")
CLOSED_GROUPS = ("completed", "cancelled")
DEFAULT_WAIT_SECONDS = 20.0
DEFAULT_RETRY_COUNT = 8
TIMEOUT_SECONDS = 60
KEY_PATTERN = re.compile(r"^([A-Za-z0-9]+)-(\d+)$")

_SECRETS: List[str] = []  # values that must never reach the output


class Problem(Exception):
    """A failure explained in three parts: what happened, why it matters, what to do next."""

    def __init__(self, what: str, why: str, next_step: str, code: int = 1) -> None:
        super().__init__(what)
        self.what = what
        self.why = why
        self.next_step = next_step
        self.code = code

    def text(self) -> str:
        return f"plane.py: {self.what}\nWhy it matters: {self.why}\nWhat to do next: {self.next_step}"


def hide_secrets(text: str) -> str:
    """Replace every known secret in the text with [hidden]."""
    for secret in _SECRETS + [os.environ.get("PLANE_API_KEY", "")]:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "[hidden]")
    return text


# ---------------------------------------------------------------- settings


class Settings:
    def __init__(self, base: str, slug: str, key: str) -> None:
        self.base = base.rstrip("/")
        self.slug = slug.strip("/")
        self.key = key

    def api(self, path: str) -> str:
        return f"{self.base}/api/v1/workspaces/{self.slug}/{path.lstrip('/')}"

    def browse(self, key: str) -> str:
        return f"{self.base}/{self.slug}/browse/{key}/"


def strip_json_comments(text: str) -> str:
    """Remove // and /* */ comments outside strings, then trailing commas before } or ]."""
    out: List[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
        elif c == '"':
            in_string = True
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        else:
            out.append(c)
            i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def find_settings_dict(node: Any) -> Optional[Dict[str, Any]]:
    """The first dict, depth first, that holds PLANE_API_KEY."""
    if isinstance(node, dict):
        if "PLANE_API_KEY" in node:
            return node
        children: Sequence[Any] = list(node.values())
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        found = find_settings_dict(child)
        if found is not None:
            return found
    return None


def resolve_env_reference(value: str) -> str:
    """OpenCode lets a config value be written as {env:NAME}; take it from the environment then."""
    match = re.fullmatch(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}", value.strip())
    return os.environ.get(match.group(1), "") if match else value


def read_config_file(path: Path) -> Dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise Problem(f"The settings file {path} could not be read ({e.strerror or e}).",
                      "The tool takes Plane's address, workspace and API key from it.",
                      "Check that the file exists and can be read, or set PLANE_BASE_URL, PLANE_WORKSPACE_SLUG and "
                      "PLANE_API_KEY in the environment.")
    lines = env_lines(text)
    if lines:  # a file of NAME=value lines
        return lines
    try:
        found = find_settings_dict(json.loads(strip_json_comments(text))) or {}
    except ValueError:  # still not valid JSON: pick the values out by name
        found = {}
        for name in NAMES:
            match = re.search(rf'"{name}"\s*:\s*"([^"]*)"', text)
            if match:
                found[name] = match.group(1)
    values: Dict[str, str] = {}
    for name in NAMES:
        value = found.get(name)
        if isinstance(value, str) and resolve_env_reference(value).strip():
            values[name] = resolve_env_reference(value).strip()
    return values


def env_lines(text: str) -> Dict[str, str]:
    """The settings found as NAME=value lines, one per line. Quotes around a value are dropped."""
    values: Dict[str, str] = {}
    for line in text.splitlines():
        name, eq, value = line.strip().partition("=")
        name, value = name.strip(), value.strip().strip("\"'").strip()
        if eq and name in NAMES and value and name not in values:
            values[name] = value
    return values


def own_settings_path() -> Path:
    """The settings file of this tool: three NAME=value lines."""
    return Path.home() / ".config" / "agent-plugins" / "plane.env"


def default_config_path() -> Path:
    """An older place, still read: the OpenCode config, where a Plane MCP entry holds the same values."""
    return Path.home() / ".config" / "opencode" / "opencode.json"


def load_settings() -> Settings:
    values: Dict[str, str] = {n: os.environ[n].strip() for n in NAMES if os.environ.get(n, "").strip()}
    looked_at: List[str] = ["the environment"]
    named = os.environ.get("PLANE_CONFIG_FILE", "").strip()
    if len(values) < len(NAMES) and named:
        path = Path(named).expanduser()
        if not path.is_file():
            raise Problem(f"PLANE_CONFIG_FILE names {path}, and that file does not exist.",
                          "The tool cannot reach Plane without its address, workspace and API key.",
                          "Point PLANE_CONFIG_FILE at an existing file, or unset it.")
        looked_at.append(str(path))
        for name, value in read_config_file(path).items():
            values.setdefault(name, value)
    for path in (own_settings_path(), default_config_path()):
        if len(values) == len(NAMES):
            break
        if path.is_file():
            looked_at.append(str(path))
            for name, value in read_config_file(path).items():
                values.setdefault(name, value)
        else:
            looked_at.append(f"{path} (not there)")
    missing = [n for n in NAMES if n not in values]
    if missing:
        raise Problem(f"No value for {', '.join(missing)}. Looked in: {'; '.join(looked_at)}.",
                      "The tool cannot reach Plane without its address, workspace and API key.",
                      f"Create the file {own_settings_path()} with the three lines PLANE_BASE_URL=..., "
                      "PLANE_WORKSPACE_SLUG=... and PLANE_API_KEY=..., or set those three as environment "
                      "variables, or point PLANE_CONFIG_FILE at a file that holds them.")
    if not re.match(r"^https?://", values["PLANE_BASE_URL"]):
        raise Problem(f"PLANE_BASE_URL is {values['PLANE_BASE_URL']!r}, which does not start with http:// or "
                      "https://.", "The tool cannot build Plane's addresses from it.",
                      "Set PLANE_BASE_URL to Plane's address, for example http://localhost:8090.")
    _SECRETS.append(values["PLANE_API_KEY"])
    return Settings(values["PLANE_BASE_URL"], values["PLANE_WORKSPACE_SLUG"], values["PLANE_API_KEY"])


def number_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = -1.0
    if value < 0:
        raise Problem(f"{name} is {raw!r}, which is not a number of zero or more.",
                      "The tool uses it to decide how to wait when Plane says there were too many calls.",
                      f"Set {name} to a number such as {default:g}, or unset it.", code=2)
    return value


# ---------------------------------------------------------------- talking to Plane


def origin(url: str) -> Tuple[str, str]:
    parts = urllib.parse.urlsplit(url)
    return parts.scheme.lower(), parts.netloc.lower()


class KeepKeyAtHome(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but never send the API key to another origin (signed asset links, for example)."""

    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any,
                         newurl: str) -> Optional[urllib.request.Request]:
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and origin(newurl) != origin(req.full_url):
            for store in (new.headers, new.unredirected_hdrs):
                for name in [h for h in store if h.lower() == "x-api-key"]:
                    del store[name]
        return new


class Plane:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.wait = number_from_env("PLANE_RETRY_WAIT", DEFAULT_WAIT_SECONDS)
        self.tries = int(number_from_env("PLANE_RETRY_COUNT", DEFAULT_RETRY_COUNT))
        self.opener = urllib.request.build_opener(KeepKeyAtHome())

    def fetch(self, method: str, url: str, body: Optional[Dict[str, Any]] = None,
              with_key: bool = True) -> Tuple[bytes, str]:
        """Send one call, waiting and trying again on 429. Returns the answer's bytes and content type."""
        data = json.dumps(body).encode("utf-8") if body is not None else None
        shown = urllib.parse.urlsplit(url).path
        for attempt in range(self.tries + 1):
            headers = {"Accept": "application/json"}
            if data is not None:
                headers["Content-Type"] = "application/json"
            if with_key:
                headers["X-API-Key"] = self.settings.key
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with self.opener.open(req, timeout=TIMEOUT_SECONDS) as answer:
                    return answer.read(), answer.headers.get("Content-Type", "")
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300].strip()
                if e.code == 429 and attempt < self.tries:
                    time.sleep(self.wait)
                    continue
                raise http_problem(e.code, method, shown, detail, self.tries, self.wait)
            except urllib.error.URLError as e:
                written = method != "GET"
                raise Problem(f"Plane at {self.settings.base} could not be reached ({e.reason}).",
                              "No answer came back, so the command did not finish"
                              + (" and it is not known whether the change was made." if written else "."),
                              "Check that Plane is running and that PLANE_BASE_URL is right"
                              + (", then look at the ticket before running the command again." if written
                                 else ", then run the command again."))
            except (TimeoutError, OSError) as e:
                raise Problem(f"The call {method} {shown} to Plane failed ({e}).",
                              "The command did not finish; for a change it is not known whether it was made.",
                              "Check that Plane is running, look at the ticket, then run the command again.")
        raise AssertionError("unreachable")

    def call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        raw, _ = self.fetch(method, self.settings.api(path), body)
        if not raw.strip():
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise Problem(f"Plane's answer to {method} {path} is not JSON.",
                          "The tool cannot read tickets out of it.",
                          "Check that PLANE_BASE_URL points at Plane itself and not at another web page.")

    def every(self, path: str) -> List[Dict[str, Any]]:
        """All rows of a listing, following Plane's pages to the end."""
        rows: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        seen: set = set()
        while True:
            sep = "&" if "?" in path else "?"
            query = "per_page=100" + (f"&cursor={urllib.parse.quote(str(cursor))}" if cursor else "")
            page = self.call("GET", f"{path}{sep}{query}")
            if isinstance(page, list):
                return rows + page
            if not isinstance(page, dict):
                return rows
            rows += page.get("results") or []
            cursor = page.get("next_cursor")
            if not page.get("next_page_results") or not cursor or cursor in seen:
                return rows
            seen.add(cursor)


def http_problem(code: int, method: str, path: str, detail: str, tries: int, wait: float) -> Problem:
    detail = hide_secrets(detail)
    if code == 429:
        return Problem(f"Plane kept answering 429 (too many calls per minute) to {method} {path}, also after "
                       f"waiting {tries} times {wait:g} seconds.",
                       "Plane allows a key only so many calls per minute; this command did not finish.",
                       "Wait a few minutes and run the same command again, with fewer Plane commands running at "
                       "the same time.")
    if code in (401, 403):
        return Problem(f"Plane refused the API key (HTTP {code}) for {method} {path}.",
                       "Without an accepted key no ticket can be read or changed.",
                       "Check PLANE_API_KEY and PLANE_WORKSPACE_SLUG; if the key was revoked, create a new API "
                       "token in Plane's settings.")
    if code == 404:
        return Problem(f"Plane answered 404 (not found) to {method} {path}.",
                       "The workspace, project, ticket or attachment in that address does not exist on this Plane.",
                       "Check PLANE_WORKSPACE_SLUG and the names you gave; `plane.py projects` lists the projects.")
    return Problem(f"Plane answered HTTP {code} to {method} {path}" + (f": {detail}" if detail else "."),
                   "The command did not finish.",
                   "Read Plane's answer above; fix the input it names, or run the command again if Plane was "
                   "busy.")


# ---------------------------------------------------------------- projects, states, tickets


def parse_key(key: str) -> Tuple[str, int]:
    match = KEY_PATTERN.match(key.strip())
    if not match:
        raise Problem(f"{key!r} is not a ticket key.", "The tool finds a ticket by its key.",
                      "Give the key as PROJECT-NUMBER, for example PDX-12.", code=2)
    return match.group(1).upper(), int(match.group(2))


def find_project(plane: Plane, identifier: str) -> Dict[str, Any]:
    projects = plane.every("projects/")
    for project in projects:
        if str(project.get("identifier", "")).upper() == identifier.upper():
            return project
    known = ", ".join(sorted(str(p.get("identifier")) for p in projects)) or "none"
    raise Problem(f"There is no project {identifier} in workspace {plane.settings.slug}.",
                  "Nothing was read or changed.",
                  f"Use one of the existing project identifiers: {known}.")


def ref_id(value: Any) -> Optional[str]:
    """Plane gives a related object either as its id or as a dict with an id."""
    if isinstance(value, dict):
        value = value.get("id")
    return str(value) if value else None


class ProjectView:
    """One project with its states and tickets, read once per command."""

    def __init__(self, plane: Plane, project: Dict[str, Any]) -> None:
        self.plane = plane
        self.project = project
        self.id = str(project["id"])
        self.identifier = str(project.get("identifier", ""))
        self._states: Optional[List[Dict[str, Any]]] = None
        self._issues: Optional[List[Dict[str, Any]]] = None

    def states(self) -> List[Dict[str, Any]]:
        if self._states is None:
            self._states = self.plane.every(f"projects/{self.id}/states/")
        return self._states

    def issues(self) -> List[Dict[str, Any]]:
        if self._issues is None:
            self._issues = self.plane.every(f"projects/{self.id}/issues/")
        return self._issues

    def key_of(self, issue: Dict[str, Any]) -> str:
        return f"{self.identifier}-{issue.get('sequence_id')}"

    def key_by_id(self) -> Dict[str, str]:
        return {str(i.get("id")): self.key_of(i) for i in self.issues()}

    def issue_by_number(self, number: int) -> Dict[str, Any]:
        for issue in self.issues():
            try:
                if int(issue.get("sequence_id")) == number:
                    return issue
            except (TypeError, ValueError):
                continue
        raise Problem(f"There is no ticket {self.identifier}-{number} in project {self.identifier}.",
                      "Nothing was read or changed.",
                      f"Check the key; `plane.py list {self.identifier}` shows the existing tickets.")

    def state_for_group(self, group: str) -> Dict[str, Any]:
        """The project's state in that group: the default state if it is in the group, else the first by order."""
        matching = [s for s in self.states() if s.get("group") == group]
        if not matching:
            raise Problem(f"Project {self.identifier} has no state in the group {group}.",
                          "The ticket's state cannot be set to that group, so nothing was changed.",
                          f"Run `plane.py states {self.identifier}` to see which groups exist.")
        defaults = [s for s in matching if s.get("default")]
        if defaults:
            return defaults[0]
        return sorted(matching, key=lambda s: float(s.get("sequence") or 0))[0]

    def summary(self, issue: Dict[str, Any], keys: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        keys = keys if keys is not None else self.key_by_id()
        states = {str(s.get("id")): s for s in self.states()}
        state_value = issue.get("state")
        state = state_value if isinstance(state_value, dict) else states.get(ref_id(state_value) or "", {})
        parent_id = ref_id(issue.get("parent"))
        key = self.key_of(issue)
        return {
            "key": key,
            "id": issue.get("id"),
            "name": issue.get("name"),
            "state": state.get("name"),
            "group": state.get("group"),
            "parent": keys.get(parent_id, parent_id) if parent_id else None,
            "url": self.plane.settings.browse(key),
        }


def open_ticket(plane: Plane, key: str) -> Tuple[ProjectView, Dict[str, Any]]:
    identifier, number = parse_key(key)
    view = ProjectView(plane, find_project(plane, identifier))
    return view, view.issue_by_number(number)


def read_text_option(text: Optional[str], file: Optional[str], what: str) -> Optional[str]:
    if file is None:
        return text
    try:
        return Path(file).read_text(encoding="utf-8-sig")
    except OSError as e:
        raise Problem(f"The {what} file {file} could not be read ({e.strerror or e}).",
                      "Nothing was sent to Plane.", "Check the path and run the command again.")


# ---------------------------------------------------------------- commands


def cmd_projects(plane: Plane, args: argparse.Namespace) -> Any:
    return [{"identifier": p.get("identifier"), "name": p.get("name"), "id": p.get("id")}
            for p in plane.every("projects/")]


def cmd_states(plane: Plane, args: argparse.Namespace) -> Any:
    view = ProjectView(plane, find_project(plane, args.project))
    return [{"id": s.get("id"), "name": s.get("name"), "group": s.get("group")} for s in view.states()]


def sequence_number(issue: Dict[str, Any]) -> int:
    try:
        return int(issue.get("sequence_id"))
    except (TypeError, ValueError):
        return 0


def cmd_list(plane: Plane, args: argparse.Namespace) -> Any:
    view = ProjectView(plane, find_project(plane, args.project))
    keys = view.key_by_id()
    rows = [view.summary(i, keys) for i in sorted(view.issues(), key=sequence_number)]
    if args.open:
        rows = [r for r in rows if r["group"] not in CLOSED_GROUPS]
    if args.group:
        rows = [r for r in rows if r["group"] in args.group]
    return rows


def comment_rows(plane: Plane, view: ProjectView, issue: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = plane.every(f"projects/{view.id}/issues/{issue['id']}/comments/")
    result = []
    for c in rows:
        actor = c.get("actor_detail") if isinstance(c.get("actor_detail"), dict) else {}
        result.append({
            "id": c.get("id"),
            "author": actor.get("display_name") or ref_id(c.get("actor")) or ref_id(c.get("created_by")),
            "created_at": c.get("created_at"),
            "text": c.get("comment_html") if c.get("comment_html") is not None else c.get("comment_stripped"),
        })
    return sorted(result, key=lambda r: str(r.get("created_at") or ""))


def cmd_show(plane: Plane, args: argparse.Namespace) -> Any:
    view, issue = open_ticket(plane, args.key)
    full = plane.call("GET", f"projects/{view.id}/issues/{issue['id']}/") or issue
    keys = view.key_by_id()
    result = view.summary(full, keys)
    result["description"] = full.get("description_html") or full.get("description_stripped") or ""
    children = [i for i in view.issues() if ref_id(i.get("parent")) == str(issue["id"])]
    result["children"] = [view.key_of(i) for i in sorted(children, key=sequence_number)]
    result["comments"] = comment_rows(plane, view, issue)
    return result


def parent_id_for(plane: Plane, view: ProjectView, key: str) -> str:
    identifier, number = parse_key(key)
    if identifier == view.identifier.upper():
        return str(view.issue_by_number(number)["id"])
    return str(ProjectView(plane, find_project(plane, identifier)).issue_by_number(number)["id"])


def cmd_create(plane: Plane, args: argparse.Namespace) -> Any:
    description = read_text_option(args.description, args.description_file, "description")
    view = ProjectView(plane, find_project(plane, args.project))
    body: Dict[str, Any] = {"name": args.name}
    if description is not None:
        body["description_html"] = description
    if args.parent:
        body["parent"] = parent_id_for(plane, view, args.parent)
    if args.group:
        body["state"] = view.state_for_group(args.group)["id"]
    created = plane.call("POST", f"projects/{view.id}/issues/", body) or {}
    keys = view.key_by_id()
    if args.parent:
        keys[body["parent"]] = args.parent.upper()
    return view.summary(created, keys)


def cmd_update(plane: Plane, args: argparse.Namespace) -> Any:
    description = read_text_option(args.description, args.description_file, "description")
    view, issue = open_ticket(plane, args.key)
    body: Dict[str, Any] = {}
    if args.name is not None:
        body["name"] = args.name
    if description is not None:
        body["description_html"] = description
    if args.parent:
        parent = parent_id_for(plane, view, args.parent)
        if parent == str(issue["id"]):
            raise Problem(f"{args.key} cannot be its own parent.", "Nothing was changed.",
                          "Give the key of another ticket with --parent.", code=2)
        body["parent"] = parent
    if args.group:
        states = {str(s.get("id")): s for s in view.states()}
        current = states.get(ref_id(issue.get("state")) or "", {})
        if current.get("group") != args.group:  # a ticket already in that group keeps its state
            body["state"] = view.state_for_group(args.group)["id"]
    changed = plane.call("PATCH", f"projects/{view.id}/issues/{issue['id']}/", body) if body else None
    merged = dict(issue)
    merged.update(changed or {})
    return view.summary(merged)


def cmd_comment(plane: Plane, args: argparse.Namespace) -> Any:
    text = read_text_option(args.text, args.file, "comment")
    if not text or not text.strip():
        raise Problem("The comment is empty.", "Plane would store a blank comment.",
                      "Give the comment with --text or --file.", code=2)
    view, issue = open_ticket(plane, args.key)
    made = plane.call("POST", f"projects/{view.id}/issues/{issue['id']}/comments/", {"comment_html": text}) or {}
    return {"key": view.key_of(issue), "comment_id": made.get("id"), "created_at": made.get("created_at"),
            "url": plane.settings.browse(view.key_of(issue))}


def cmd_comments(plane: Plane, args: argparse.Namespace) -> Any:
    view, issue = open_ticket(plane, args.key)
    return comment_rows(plane, view, issue)


def attachment_base(view: ProjectView, issue: Dict[str, Any]) -> str:
    return f"projects/{view.id}/issues/{issue['id']}/issue-attachments/"


def cmd_attachments(plane: Plane, args: argparse.Namespace) -> Any:
    view, issue = open_ticket(plane, args.key)
    answer = plane.call("GET", attachment_base(view, issue))
    rows = answer.get("results", []) if isinstance(answer, dict) else (answer or [])
    result = []
    for a in rows:
        attributes = a.get("attributes") if isinstance(a.get("attributes"), dict) else {}
        result.append({
            "id": a.get("id"),
            "name": attributes.get("name") or a.get("name"),
            "type": attributes.get("type") or a.get("type"),
            "size": attributes.get("size") or a.get("size"),
            "created_at": a.get("created_at"),
        })
    return result


def cmd_download(plane: Plane, args: argparse.Namespace) -> Any:
    view, issue = open_ticket(plane, args.key)
    url = plane.settings.api(attachment_base(view, issue) + f"{args.attachment_id}/")
    data, content_type = plane.fetch("GET", url)
    if "json" in content_type.lower():  # some versions answer with a link to the file instead of the file
        try:
            answer = json.loads(data.decode("utf-8"))
        except ValueError:
            answer = None
        link = None
        if isinstance(answer, dict):
            link = next((answer[k] for k in ("url", "asset_url", "presigned_url")
                         if isinstance(answer.get(k), str) and answer[k].startswith("http")), None)
        if link:
            same_place = origin(link) == origin(plane.settings.base)
            data, _ = plane.fetch("GET", link, with_key=same_place)
    out = Path(args.out).expanduser().resolve()
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=str(out.parent), prefix=out.name + ".", suffix=".part")
        with os.fdopen(handle, "wb") as f:
            f.write(data)
        os.replace(temp, out)
    except OSError as e:
        raise Problem(f"The attachment could not be saved to {out} ({e.strerror or e}).",
                      "The file is not on disk.", "Pick a folder you can write to and run the command again.")
    return {"key": view.key_of(issue), "attachment_id": args.attachment_id, "file": str(out), "bytes": len(data)}


# ---------------------------------------------------------------- command line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plane.py", description="Read and change tickets in a self-hosted Plane through its REST API. "
        "Output is JSON. PROJECT is a project identifier such as PDX; KEY is a ticket key such as PDX-12.",
        epilog="Settings: PLANE_BASE_URL, PLANE_WORKSPACE_SLUG, PLANE_API_KEY from the environment, else from the "
        "file in PLANE_CONFIG_FILE, else from ~/.config/agent-plugins/plane.env (three NAME=value lines), else "
        "from ~/.config/opencode/opencode.json. Waiting after 'too many calls': "
        "PLANE_RETRY_WAIT seconds (default 20), PLANE_RETRY_COUNT times (default 8).")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_text, description=help_text)

    def add_description(p: argparse.ArgumentParser) -> None:
        group = p.add_mutually_exclusive_group()
        group.add_argument("--description", help="Markdown text")
        group.add_argument("--description-file", metavar="FILE", help="file with Markdown text (UTF-8)")

    add("projects", "list the workspace's projects").set_defaults(run=cmd_projects)

    p = add("states", "list a project's states with their groups")
    p.add_argument("project", metavar="PROJECT")
    p.set_defaults(run=cmd_states)

    p = add("list", "list all tickets of a project, every page")
    p.add_argument("project", metavar="PROJECT")
    p.add_argument("--open", action="store_true", help="leave out completed and cancelled tickets")
    p.add_argument("--group", action="append", choices=GROUPS, help="only tickets in this state group; repeatable")
    p.set_defaults(run=cmd_list)

    p = add("show", "show one ticket with description, child tickets and comments")
    p.add_argument("key", metavar="KEY")
    p.set_defaults(run=cmd_show)

    p = add("create", "create a ticket")
    p.add_argument("project", metavar="PROJECT")
    p.add_argument("--name", required=True, help="the ticket's title")
    p.add_argument("--parent", metavar="KEY", help="key of the parent ticket")
    p.add_argument("--group", choices=GROUPS, help="put the ticket in the project's state of this group")
    add_description(p)
    p.set_defaults(run=cmd_create)

    p = add("update", "change a ticket's name, state group, parent or description")
    p.add_argument("key", metavar="KEY")
    p.add_argument("--name", help="new title")
    p.add_argument("--group", choices=GROUPS, help="move to the project's state of this group")
    p.add_argument("--parent", metavar="KEY", help="key of the new parent ticket")
    add_description(p)
    p.set_defaults(run=cmd_update)

    p = add("comment", "add a comment to a ticket")
    p.add_argument("key", metavar="KEY")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", help="Markdown text")
    group.add_argument("--file", help="file with Markdown text (UTF-8)")
    p.set_defaults(run=cmd_comment)

    p = add("comments", "list a ticket's comments")
    p.add_argument("key", metavar="KEY")
    p.set_defaults(run=cmd_comments)

    p = add("attachments", "list a ticket's attachments")
    p.add_argument("key", metavar="KEY")
    p.set_defaults(run=cmd_attachments)

    p = add("download", "save one attachment of a ticket to a file")
    p.add_argument("key", metavar="KEY")
    p.add_argument("attachment_id", metavar="ATTACHMENT_ID")
    p.add_argument("--out", required=True, metavar="FILE", help="where to save the file")
    p.set_defaults(run=cmd_download)
    return parser


def check_usage(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.command in ("create", "update") and args.name is not None and not args.name.strip():
        parser.error("--name must not be empty")
    if args.command == "update" and not any(
            v is not None for v in (args.name, args.group, args.parent, args.description, args.description_file)):
        parser.error("update needs at least one of --name, --group, --parent, --description, --description-file")


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    parser = build_parser()
    args = parser.parse_args(argv)
    check_usage(parser, args)
    try:
        plane = Plane(load_settings())
        result = args.run(plane, args)
    except Problem as p:
        print(hide_secrets(p.text()), file=sys.stderr)
        return p.code
    except Exception as e:  # anything unforeseen: still plain, still without the key
        print(hide_secrets(f"plane.py: The command stopped on an unexpected error: {type(e).__name__}: {e}\n"
                           "Why it matters: the command may not have finished.\n"
                           "What to do next: look at the ticket in Plane, then run the command again."),
              file=sys.stderr)
        return 1
    print(hide_secrets(json.dumps(result, indent=2, ensure_ascii=False)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
