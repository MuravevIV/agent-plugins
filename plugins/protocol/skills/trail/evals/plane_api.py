"""Small helper for the trail test: talks to the user's local Plane over its REST API.

Reads the address, the workspace and the key from the `plane` entry of the user's OpenCode config, the same place
the `plane` tool skill names. The key is never printed and never written to a file.
Used once, on this PC, on 2026-11-22 (Plane CE on localhost:8090).
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

CONFIG = Path(os.environ.get("TRAIL_TEST_PLANE_CONFIG") or Path.home() / ".config" / "opencode" / "opencode.json")
NAMES = ("PLANE_BASE_URL", "PLANE_WORKSPACE_SLUG", "PLANE_API_KEY")
WAITS, WAIT_SECONDS = 8, 20  # how often and how long to wait when Plane says "too many calls"


class PlaneProblem(Exception):
    """Something the person running the test can act on."""


def _find(node):
    if isinstance(node, dict):
        if "PLANE_API_KEY" in node:
            return node
        for value in node.values():
            found = _find(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find(value)
            if found:
                return found
    return None


def settings():
    if not CONFIG.is_file():
        raise PlaneProblem(f"The file {CONFIG} does not exist. The trail test reads Plane's address and key from "
                           "it. Set TRAIL_TEST_PLANE_CONFIG to a JSON file that holds PLANE_BASE_URL, "
                           "PLANE_WORKSPACE_SLUG and PLANE_API_KEY.")
    text = CONFIG.read_text(encoding="utf-8-sig")
    try:
        found = _find(json.loads(text)) or {}
    except ValueError:  # a config with comments is not strict JSON; pick the three values out by name
        found = {n: m.group(1) for n in NAMES if (m := re.search(rf'"{n}"\s*:\s*"([^"]*)"', text))}
    missing = [n for n in NAMES if not found.get(n)]
    if missing:
        raise PlaneProblem(f"The file {CONFIG} has no value for {', '.join(missing)}. The trail test cannot reach "
                           "Plane without them.")
    base = found["PLANE_BASE_URL"].rstrip("/")
    host = re.sub(r"^https?://", "", base).split("/")[0].split(":")[0]
    if host not in ("localhost", "127.0.0.1", "[::1]"):
        raise PlaneProblem(f"Plane's address in {CONFIG} is {base}, which is not on this computer. The trail test "
                           "creates and changes tickets, so it runs against a local Plane only. Nothing was sent.")
    return base, found["PLANE_WORKSPACE_SLUG"], found["PLANE_API_KEY"]


def call(method, path, body=None):
    """path starts after /api/v1/workspaces/<slug>/ . Returns the decoded JSON answer, or None for an empty one."""
    base, slug, key = settings()
    url = f"{base}/api/v1/workspaces/{slug}/{path.lstrip('/')}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    for attempt in range(1, WAITS + 2):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"X-API-Key": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as answer:
                raw = answer.read()
            return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            # Plane allows a key a fixed number of calls per minute (seen on 2026-11-22: 429, RATE_LIMIT_EXCEEDED).
            if e.code == 429 and attempt <= WAITS:
                time.sleep(WAIT_SECONDS)
                continue
            if e.code == 429:
                raise PlaneProblem(f"Plane kept answering 429 (too many calls per minute) to {method} {path}, also "
                                   f"after waiting {WAITS} times {WAIT_SECONDS} seconds. Start again in a few "
                                   "minutes, with fewer runs at the same time (--parallel 1).")
            raise PlaneProblem(f"Plane answered {e.code} to {method} {path}: {detail}")
        except urllib.error.URLError as e:
            raise PlaneProblem(f"Plane at {base} could not be reached ({e.reason}). Is its Docker stack running?")


def every(path):
    """All rows of a listing, following Plane's pages."""
    rows, cursor = [], None
    while True:
        sep = "&" if "?" in path else "?"
        page = call("GET", f"{path}{sep}per_page=100" + (f"&cursor={cursor}" if cursor else ""))
        if isinstance(page, list):
            return rows + page
        rows += page.get("results") or []
        if not page.get("next_page_results"):
            return rows
        cursor = page.get("next_cursor")
