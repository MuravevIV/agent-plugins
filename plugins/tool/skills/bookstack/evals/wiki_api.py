"""Small helper for the test of the bookstack tool skill: reads the user's local BookStack over its API.

Settings come from the same places the sync script uses. The token is never printed.
Used once, on this PC, on 2026-11-23.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class WikiProblem(Exception):
    """Something the person running the test can act on."""


def settings() -> Tuple[str, str]:
    """The wiki's address and the value of the Authorization header."""
    url = os.environ.get("BOOKSTACK_URL")
    tid, secret = os.environ.get("BOOKSTACK_TOKEN_ID"), os.environ.get("BOOKSTACK_TOKEN_SECRET")
    if not (url and tid and secret):
        path = Path(os.environ.get("BOOKSTACK_ENV_FILE") or
                    Path.home() / ".config" / "opencode" / "playbooks" / "install-bookstack" / ".env")
        if not path.is_file():
            raise WikiProblem(f"No wiki settings: the BOOKSTACK_* variables are not set and {path} does not exist.")
        found: Dict[str, str] = {}
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                found[key.strip()] = value.strip().strip('"')
        url, tid, secret = found.get("APP_URL"), found.get("API_TOKEN_ID"), found.get("API_TOKEN_SECRET")
        if not (url and tid and secret):
            raise WikiProblem(f"{path} lacks APP_URL, API_TOKEN_ID or API_TOKEN_SECRET.")
    host = url.split("//")[-1].split("/")[0].split(":")[0]
    if host not in ("localhost", "127.0.0.1", "[::1]"):
        raise WikiProblem(f"The wiki's address is {url}, which is not on this computer. The test creates shelves "
                          "and pages, so it runs against a local wiki only. Nothing was sent.")
    return url.rstrip("/"), f"Token {tid}:{secret}"


def call(path: str, method: str = "GET", body: Optional[Dict[str, Any]] = None) -> Any:
    base, auth = settings()
    req = urllib.request.Request(f"{base}/api/{path.lstrip('/')}", method=method,
                                 headers={"Authorization": auth, "Content-Type": "application/json"},
                                 data=json.dumps(body).encode("utf-8") if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as answer:
            raw = answer.read()
    except urllib.error.HTTPError as e:
        raise WikiProblem(f"The wiki answered {e.code} to {method} {path}: {e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        raise WikiProblem(f"The wiki at {base} could not be reached ({e.reason}). Is its Docker stack running?")
    return json.loads(raw) if raw.strip() else None


def shelf_pages(shelf_name: str) -> Optional[Dict[str, Any]]:
    """The shelf with that name, its books, and every page in them with its text. None when there is no such shelf."""
    hits = [s for s in call("shelves?count=500")["data"] if s["name"] == shelf_name]
    if not hits:
        return None
    shelf = call(f"shelves/{hits[0]['id']}")
    books: List[Dict[str, Any]] = []
    for b in shelf.get("books") or []:
        pages = [call(f"pages/{p['id']}") for p in call(f"pages?count=500&filter[book_id]={b['id']}")["data"]]
        books.append({"id": b["id"], "name": b["name"],
                      "pages": [{"id": p["id"], "name": p["name"], "markdown": p.get("markdown") or ""}
                                for p in pages]})
    return {"id": shelf["id"], "name": shelf["name"], "books": books}
