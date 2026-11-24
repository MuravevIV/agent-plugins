"""Tests for scripts/sync_docs_wiki.py against a fake BookStack running in this process.

The tests never contact a real wiki and never read a real settings file: the
BOOKSTACK_* variables point at the fake, and HOME/USERPROFILE point at a
temporary folder.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(os.path.dirname(ROOT), "plugins", "tool", "skills", "bookstack", "scripts", "sync_docs_wiki.py")
TOKEN_ID = "tokid7Q2xLm9"
TOKEN_SECRET = "s3cr3t-Zp81-never-print"


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("sync_docs_wiki", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_docs_wiki"] = module
    spec.loader.exec_module(module)
    return module


sdw = load_module()


# ---------------------------------------------------------------- fake BookStack


class FakeBookStack:
    """Keeps shelves, books and pages in memory and records every request."""

    def __init__(self) -> None:
        self.shelves: Dict[int, Dict[str, Any]] = {}
        self.books: Dict[int, Dict[str, Any]] = {}
        self.pages: Dict[int, Dict[str, Any]] = {}
        self.requests: List[Tuple[str, str, Any]] = []
        self.next_id = 100
        self.lock = threading.Lock()
        # (method, path) -> status code to answer with instead of handling the request
        self.fail: Optional[Callable[[str, str], Optional[int]]] = None
        self.expected_auth = f"Token {TOKEN_ID}:{TOKEN_SECRET}"
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw.decode("utf-8")) if raw else None
                status, answer = fake.handle(self.command, self.path, body, self.headers.get("Authorization", ""))
                data = json.dumps(answer).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_DELETE = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def new_id(self) -> int:
        self.next_id += 1
        return self.next_id

    def writes(self) -> List[Tuple[str, str, Any]]:
        return [r for r in self.requests if r[0] != "GET"]

    def add_shelf(self, name: str) -> int:
        shelf_id = self.new_id()
        self.shelves[shelf_id] = {"id": shelf_id, "name": name, "books": []}
        return shelf_id

    def add_book(self, shelf_id: int, name: str) -> int:
        book_id = self.new_id()
        self.books[book_id] = {"id": book_id, "name": name}
        self.shelves[shelf_id]["books"].append(book_id)
        return book_id

    def add_page(self, book_id: int, name: str, markdown: str) -> int:
        page_id = self.new_id()
        self.pages[page_id] = {"id": page_id, "name": name, "markdown": markdown, "book_id": book_id}
        return page_id

    def book_named(self, name: str) -> Dict[str, Any]:
        return next(b for b in self.books.values() if b["name"] == name)

    def handle(self, method: str, raw_path: str, body: Any, auth: str) -> Tuple[int, Any]:
        with self.lock:
            path = urlsplit(raw_path).path
            self.requests.append((method, raw_path, body))
            if auth != self.expected_auth:
                # a careless server that echoes the header: the script must hide the token
                return 401, {"error": {"code": 401, "message": f"The provided token is invalid: {auth}"}}
            if self.fail is not None:
                code = self.fail(method, path)
                if code is not None:
                    return code, {"error": {"code": code, "message": "Something broke on the server"}}
            parts = path.strip("/").split("/")
            if parts[0] != "api":
                return 404, {"error": {"code": 404, "message": "Not found"}}
            parts = parts[1:]
            not_found = (404, {"error": {"code": 404, "message": "Not found"}})
            if parts == ["shelves"] and method == "GET":
                return 200, {"data": [{"id": s["id"], "name": s["name"]} for s in self.shelves.values()],
                             "total": len(self.shelves)}
            if parts == ["shelves"] and method == "POST":
                shelf_id = self.add_shelf(body["name"])
                self.shelves[shelf_id]["description"] = body.get("description")
                return 200, {"id": shelf_id, "name": body["name"]}
            if len(parts) == 2 and parts[0] == "shelves":
                shelf = self.shelves.get(int(parts[1]))
                if shelf is None:
                    return not_found
                if method == "PUT":
                    shelf["books"] = list(body["books"])
                books = [{"id": b, "name": self.books[b]["name"]} for b in shelf["books"]]
                return 200, {"id": shelf["id"], "name": shelf["name"], "books": books}
            if parts == ["books"] and method == "POST":
                book_id = self.new_id()
                self.books[book_id] = {"id": book_id, "name": body["name"]}
                return 200, dict(self.books[book_id])
            if parts == ["pages"] and method == "POST":
                if body.get("book_id") not in self.books:
                    return 422, {"error": {"code": 422, "message": "book_id is invalid"}}
                page_id = self.add_page(body["book_id"], body["name"], body["markdown"].rstrip("\r\n"))
                return 200, dict(self.pages[page_id])
            if len(parts) == 2 and parts[0] == "pages":
                page = self.pages.get(int(parts[1]))
                if page is None:
                    return not_found
                if method == "PUT":
                    page.update({k: body[k] for k in ("name", "book_id") if k in body})
                    if "markdown" in body:
                        page["markdown"] = body["markdown"].rstrip("\r\n")
                return 200, dict(page)
            return 405, {"error": {"code": 405, "message": "Method not allowed"}}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ---------------------------------------------------------------- base test case


class SyncTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = os.path.join(self.tmp.name, "project")
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(self.project, "docs"))
        os.makedirs(self.home)
        self.wiki = FakeBookStack()
        self.addCleanup(self.wiki.stop)
        self.outputs: List[str] = []

    # helpers

    def write(self, rel: str, text: str, bom: bool = False) -> str:
        path = os.path.join(self.project, "docs", *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
        return path

    def state_path(self) -> str:
        return os.path.join(self.project, "docs", ".wiki-sync.json")

    def write_state(self, data: Any, text: Optional[str] = None) -> None:
        with open(self.state_path(), "w", encoding="utf-8", newline="") as handle:
            handle.write(text if text is not None else json.dumps(data))

    def read_state(self) -> Dict[str, Any]:
        with open(self.state_path(), encoding="ascii") as handle:
            return json.load(handle)

    def state_bytes(self) -> bytes:
        with open(self.state_path(), "rb") as handle:
            return handle.read()

    def env(self, **overrides: Optional[str]) -> Dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("BOOKSTACK_")}
        env.update({
            "HOME": self.home,
            "USERPROFILE": self.home,
            "BOOKSTACK_URL": self.wiki.url,
            "BOOKSTACK_TOKEN_ID": TOKEN_ID,
            "BOOKSTACK_TOKEN_SECRET": TOKEN_SECRET,
            "PYTHONIOENCODING": "utf-8",
            "NO_PROXY": "*",
            "no_proxy": "*",
        })
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return env

    def run_sync(self, *args: str, cwd: Optional[str] = None, **env: Optional[str]) -> subprocess.CompletedProcess:
        result = subprocess.run(
            [sys.executable, SCRIPT, *args],
            cwd=cwd or self.project,
            env=self.env(**env),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        self.outputs.append(result.stdout + result.stderr)
        return result

    def sync_ok(self, *args: str, **env: Optional[str]) -> subprocess.CompletedProcess:
        result = self.run_sync(*args, **env)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        return result

    def basic_project(self) -> None:
        self.write_state({"shelf": "Demo", "pages": {}})
        self.write("index.md", "# Home\n\nWelcome.\n")
        self.write("plans/roadmap.md", "# Roadmap\n\nGoals.\n")

    def tearDown(self) -> None:
        for text in self.outputs:
            self.assertNotIn(TOKEN_SECRET, text)
            self.assertNotIn(TOKEN_ID, text)

    def last_line(self, result: subprocess.CompletedProcess) -> str:
        return result.stdout.strip().splitlines()[-1]

    def assert_failure(self, result: subprocess.CompletedProcess, *needles: str) -> None:
        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
        self.assertIn("error: ", result.stderr)
        self.assertIn("why it matters: ", result.stderr)
        self.assertIn("what to do: ", result.stderr)
        for needle in needles:
            self.assertIn(needle, result.stderr)


# ---------------------------------------------------------------- sync behaviour


class FirstSyncTests(SyncTestCase):
    def test_first_sync_creates_shelf_books_and_pages(self) -> None:
        self.basic_project()
        self.write("my-big-plans/idea.md", "# Idea\n\nText.\n")
        result = self.sync_ok()

        self.assertEqual([s["name"] for s in self.wiki.shelves.values()], ["Demo"])
        shelf = next(iter(self.wiki.shelves.values()))
        self.assertEqual(sorted(self.wiki.books[b]["name"] for b in shelf["books"]),
                         ["My Big Plans", "Notes", "Plans"])
        self.assertEqual(len(self.wiki.pages), 3)
        state = self.read_state()
        sep = os.sep
        self.assertEqual(set(state["pages"]), {"index.md", f"my-big-plans{sep}idea.md", f"plans{sep}roadmap.md"})
        roadmap = self.wiki.pages[state["pages"][f"plans{sep}roadmap.md"]]
        self.assertEqual(roadmap["book_id"], self.wiki.book_named("Plans")["id"])
        index = self.wiki.pages[state["pages"]["index.md"]]
        self.assertEqual(index["book_id"], self.wiki.book_named("Notes")["id"])
        self.assertIn("created shelf: Demo (id ", result.stdout)
        self.assertIn(f"created: plans{sep}roadmap.md -> page {roadmap['id']} (book Plans)", result.stdout)
        self.assertEqual(self.last_line(result), "sync done: 3 created, 0 updated, 3 unchanged")

    def test_files_are_handled_in_path_order(self) -> None:
        self.write_state({"shelf": "Demo", "pages": {}})
        for rel in ("zeta.md", "alpha.md", "b-dir/one.md", "a-dir/two.md"):
            self.write(rel, f"# {rel}\n")
        result = self.sync_ok()
        created = [line.split(" ")[1] for line in result.stdout.splitlines() if line.startswith("created: ")]
        self.assertEqual(created, [f"a-dir{os.sep}two.md", "alpha.md", f"b-dir{os.sep}one.md", "zeta.md"])

    def test_existing_shelf_and_books_are_reused_only_on_that_shelf(self) -> None:
        other = self.wiki.add_shelf("Other")
        self.wiki.add_book(other, "Plans")
        demo = self.wiki.add_shelf("Demo")
        notes = self.wiki.add_book(demo, "Notes")
        self.basic_project()
        self.sync_ok()
        self.assertEqual(len(self.wiki.shelves), 2)
        demo_books = [self.wiki.books[b]["name"] for b in self.wiki.shelves[demo]["books"]]
        self.assertEqual(demo_books, ["Notes", "Plans"])
        self.assertNotIn(self.wiki.shelves[demo]["books"][1], self.wiki.shelves[other]["books"])
        index_id = self.read_state()["pages"]["index.md"]
        self.assertEqual(self.wiki.pages[index_id]["book_id"], notes)


class RepeatRunTests(SyncTestCase):
    def test_second_run_changes_nothing(self) -> None:
        self.basic_project()
        self.sync_ok()
        before = self.state_bytes()
        self.wiki.requests.clear()
        result = self.sync_ok()
        self.assertEqual(self.wiki.writes(), [])
        self.assertTrue(self.wiki.requests)
        self.assertEqual(result.stdout.strip(), "sync done: 0 created, 0 updated, 2 unchanged")
        self.assertEqual(self.state_bytes(), before)

    def test_changed_file_gives_one_update(self) -> None:
        self.basic_project()
        self.sync_ok()
        self.wiki.requests.clear()
        self.write("plans/roadmap.md", "# Roadmap\n\nNew goals.\n")
        result = self.sync_ok()
        writes = self.wiki.writes()
        self.assertEqual(len(writes), 1)
        page_id = self.read_state()["pages"][f"plans{os.sep}roadmap.md"]
        self.assertEqual(writes[0][:2], ("PUT", f"/api/pages/{page_id}"))
        self.assertEqual(self.wiki.pages[page_id]["markdown"], "New goals.")
        self.assertIn(f"updated: plans{os.sep}roadmap.md -> page {page_id} (book Plans)", result.stdout)
        self.assertEqual(self.last_line(result), "sync done: 0 created, 1 updated, 1 unchanged")

    def test_change_of_case_only_is_pushed(self) -> None:
        self.basic_project()
        self.sync_ok()
        self.write("index.md", "# HOME\n\nwelcome.\n")
        result = self.sync_ok()
        page = self.wiki.pages[self.read_state()["pages"]["index.md"]]
        self.assertEqual((page["name"], page["markdown"]), ("HOME", "welcome."))
        self.assertEqual(self.last_line(result), "sync done: 0 created, 1 updated, 1 unchanged")

    def test_trailing_whitespace_alone_is_not_a_change(self) -> None:
        self.basic_project()
        self.sync_ok()
        self.write("index.md", "# Home\n\nWelcome.\n\n\n   \n")
        self.wiki.requests.clear()
        self.sync_ok()
        self.assertEqual(self.wiki.writes(), [])


class MappingTests(SyncTestCase):
    def test_notes_book_for_top_level_and_title_case_for_directory(self) -> None:
        self.write_state({"shelf": "Demo", "pages": {}})
        self.write("top.md", "# Top\n")
        self.write("release-notes-2026/q1.md", "# Q1\n")
        self.sync_ok()
        state = self.read_state()["pages"]
        self.assertEqual(self.wiki.pages[state["top.md"]]["book_id"], self.wiki.book_named("Notes")["id"])
        self.assertEqual(self.wiki.pages[state[f"release-notes-2026{os.sep}q1.md"]]["book_id"],
                         self.wiki.book_named("Release Notes 2026")["id"])

    def test_file_nested_too_deep_is_skipped_with_warning(self) -> None:
        self.write_state({"shelf": "Demo", "pages": {}})
        self.write("a/b/deep.md", "# Deep\n")
        self.write("ok.md", "# Ok\n")
        result = self.sync_ok()
        self.assertIn(f"a{os.sep}b{os.sep}deep.md is nested too deep", result.stderr)
        self.assertNotIn("deep", result.stdout)
        self.assertEqual([p["name"] for p in self.wiki.pages.values()], ["Ok"])
        self.assertEqual(list(self.read_state()["pages"]), ["ok.md"])

    def test_title_from_heading_and_heading_removed_from_body(self) -> None:
        self.write_state({"shelf": "Demo", "pages": {}})
        self.write("titled.md", "\n# My Title\r\n\r\n\nBody line.\r\nSecond line.\n")
        self.write("untitled.md", "No heading here.\n")
        self.write("bom.md", "# With BOM\n\nText.\n", bom=True)
        self.sync_ok()
        state = self.read_state()["pages"]
        titled = self.wiki.pages[state["titled.md"]]
        self.assertEqual(titled["name"], "My Title")
        self.assertEqual(titled["markdown"], "Body line.\r\nSecond line.")
        untitled = self.wiki.pages[state["untitled.md"]]
        self.assertEqual((untitled["name"], untitled["markdown"]), ("untitled", "No heading here."))
        bom = self.wiki.pages[state["bom.md"]]
        self.assertEqual((bom["name"], bom["markdown"]), ("With BOM", "Text."))

    def test_links_to_docs_become_permalinks_with_anchor(self) -> None:
        self.write_state({"shelf": "Demo", "pages": {}})
        self.write("index.md", "# Home\n\n"
                   "[road](plans/roadmap.md#goals) [plain](plans/roadmap.md)\n"
                   "[out](https://example.com/x.md) [none](missing.md) [deep](a/b/c.md)\n")
        self.write("plans/roadmap.md", "# Roadmap\n\nBack to [home](../index.md).\n")
        self.write("a/b/c.md", "# Deep\n")
        result = self.sync_ok()
        state = self.read_state()["pages"]
        road_id, home_id = state[f"plans{os.sep}roadmap.md"], state["index.md"]
        home = self.wiki.pages[home_id]["markdown"]
        self.assertIn(f"[road]({self.wiki.url}/link/{road_id}#goals)", home)
        self.assertIn(f"[plain]({self.wiki.url}/link/{road_id})", home)
        self.assertIn("[out](https://example.com/x.md)", home)
        self.assertIn("[none](missing.md)", home)
        self.assertIn("[deep](a/b/c.md)", home)
        self.assertIn(f"[home]({self.wiki.url}/link/{home_id})", self.wiki.pages[road_id]["markdown"])
        self.assertEqual(self.last_line(result), "sync done: 2 created, 2 updated, 0 unchanged")


class StateFileTests(SyncTestCase):
    def test_moved_file_keeps_its_page_and_changes_book(self) -> None:
        self.write_state({"shelf": "Demo", "pages": {}})
        self.write("plans/x.md", "# X\n\nText.\n")
        self.sync_ok()
        page_id = self.read_state()["pages"][f"plans{os.sep}x.md"]
        os.makedirs(os.path.join(self.project, "docs", "ideas"))
        os.replace(os.path.join(self.project, "docs", "plans", "x.md"),
                   os.path.join(self.project, "docs", "ideas", "x.md"))
        self.write_state({"shelf": "Demo", "pages": {f"ideas{os.sep}x.md": page_id}})
        self.wiki.requests.clear()
        result = self.sync_ok()
        self.assertNotIn(("POST", "/api/pages"), [r[:2] for r in self.wiki.requests])
        self.assertEqual(len(self.wiki.pages), 1)
        self.assertEqual(self.wiki.pages[page_id]["book_id"], self.wiki.book_named("Ideas")["id"])
        self.assertIn(f"updated: ideas{os.sep}x.md -> page {page_id} (book Ideas)", result.stdout)

    def test_state_entry_without_file_warns_and_deletes_nothing(self) -> None:
        self.basic_project()
        self.sync_ok()
        state = self.read_state()
        os.remove(os.path.join(self.project, "docs", "index.md"))
        self.wiki.requests.clear()
        result = self.sync_ok()
        self.assertIn(f"index.md is in sync state but missing from docs/ - wiki page {state['pages']['index.md']} "
                      "left untouched", result.stderr)
        self.assertEqual(self.wiki.writes(), [])
        self.assertEqual(len(self.wiki.pages), 2)
        self.assertEqual(self.read_state(), state)

    def _project_with_existing_pages(self, sep: str) -> Tuple[int, int]:
        shelf = self.wiki.add_shelf("Demo")
        plans = self.wiki.add_book(shelf, "Plans")
        notes = self.wiki.add_book(shelf, "Notes")
        roadmap = self.wiki.add_page(plans, "Roadmap", "Goals.")
        index = self.wiki.add_page(notes, "Home", "Welcome.")
        self.write("index.md", "# Home\n\nWelcome.\n")
        self.write("plans/roadmap.md", "# Roadmap\n\nGoals.\n")
        self.write_state({"shelf": "Demo", "pages": {f"plans{sep}roadmap.md": roadmap, "index.md": index}})
        return roadmap, index

    def test_backslash_keys_are_kept_and_matched(self) -> None:
        roadmap, index = self._project_with_existing_pages("\\")
        self.write("ideas/new.md", "# New\n")
        self.sync_ok()
        self.assertEqual(len([r for r in self.wiki.requests if r[:2] == ("POST", "/api/pages")]), 1)
        pages = self.read_state()["pages"]
        self.assertEqual(list(pages)[:2], ["plans\\roadmap.md", "index.md"])
        self.assertEqual(pages["plans\\roadmap.md"], roadmap)
        self.assertIn("ideas\\new.md", pages)

    def test_forward_slash_keys_are_kept_and_matched(self) -> None:
        roadmap, _ = self._project_with_existing_pages("/")
        self.write("ideas/new.md", "# New\n")
        self.sync_ok()
        pages = self.read_state()["pages"]
        self.assertEqual(list(pages), ["plans/roadmap.md", "index.md", "ideas/new.md"])

    def test_state_file_not_rewritten_when_nothing_changed(self) -> None:
        roadmap, index = self._project_with_existing_pages("\\")
        # written the way the PowerShell script does: other order, other indent, CRLF
        text = ('{\r\n    "pages":  {\r\n                  "index.md":  %d,\r\n'
                '                  "plans\\\\roadmap.md":  %d\r\n              },\r\n'
                '    "shelf":  "Demo"\r\n}\r\n') % (index, roadmap)
        self.write_state(None, text=text)
        before = self.state_bytes()
        self.wiki.requests.clear()
        result = self.sync_ok()
        self.assertEqual(self.wiki.writes(), [])
        self.assertEqual(self.state_bytes(), before)
        self.assertEqual(self.last_line(result), "sync done: 0 created, 0 updated, 2 unchanged")

    def test_state_file_format(self) -> None:
        self.write_state({"pages": {}, "shelf": "Demo"})
        self.write("café.md", "# Café\n")
        self.sync_ok()
        text = self.state_bytes().decode("ascii")
        page_id = next(iter(self.wiki.pages))
        self.assertEqual(text, '{\n  "shelf": "Demo",\n  "pages": {\n    "caf\\u00e9.md": %d\n  }\n}\n' % page_id)

    def test_wiki_failure_while_creating_keeps_created_pages_recorded(self) -> None:
        self.write_state({"shelf": "Demo", "pages": {}})
        for name in ("a.md", "b.md", "c.md"):
            self.write(name, f"# {name}\n")
        posts = {"n": 0}

        def fail_third_post(method: str, path: str) -> Optional[int]:
            if (method, path) == ("POST", "/api/pages"):
                posts["n"] += 1
                if posts["n"] == 3:
                    return 500
            return None

        self.wiki.fail = fail_third_post
        result = self.run_sync()
        self.assert_failure(result, "HTTP 500", "already recorded")
        self.assertEqual(list(self.read_state()["pages"]), ["a.md", "b.md"])
        self.assertEqual(len(self.wiki.pages), 2)

        self.wiki.fail = None
        result = self.sync_ok()
        self.assertEqual(list(self.read_state()["pages"]), ["a.md", "b.md", "c.md"])
        self.assertEqual(len(self.wiki.pages), 3)
        self.assertEqual(self.last_line(result), "sync done: 1 created, 0 updated, 3 unchanged")


class DryRunTests(SyncTestCase):
    def test_dry_run_on_new_project_writes_nothing(self) -> None:
        self.basic_project()
        before = self.state_bytes()
        result = self.sync_ok("--dry-run")
        self.assertEqual(self.wiki.writes(), [])
        self.assertTrue(self.wiki.requests)
        self.assertEqual(self.state_bytes(), before)
        self.assertEqual(self.wiki.pages, {})
        self.assertIn("would create shelf: Demo", result.stdout)
        self.assertIn("would create: index.md (book Notes)", result.stdout)
        self.assertIn(f"would create: plans{os.sep}roadmap.md (book Plans)", result.stdout)
        self.assertEqual(self.last_line(result), "dry run: 2 would be created, 0 would be updated, 0 unchanged")
        self.assertEqual(os.listdir(os.path.join(self.project, "docs")).count(".wiki-sync.json.tmp"), 0)

    def test_dry_run_reports_updates_without_making_them(self) -> None:
        self.basic_project()
        self.sync_ok()
        before = self.state_bytes()
        self.write("plans/roadmap.md", "# Roadmap\n\nSee [home](../index.md) and [new](../new.md).\n")
        self.write("new.md", "# New\n")
        self.wiki.requests.clear()
        result = self.sync_ok("--dry-run")
        self.assertEqual(self.wiki.writes(), [])
        self.assertEqual(self.state_bytes(), before)
        page_id = self.read_state()["pages"][f"plans{os.sep}roadmap.md"]
        self.assertIn("would create: new.md (book Notes)", result.stdout)
        self.assertIn(f"would update: plans{os.sep}roadmap.md -> page {page_id} (book Plans)", result.stdout)
        self.assertEqual(self.last_line(result), "dry run: 1 would be created, 1 would be updated, 1 unchanged")


# ---------------------------------------------------------------- settings and failures


class SettingsTests(SyncTestCase):
    def _env_file_text(self) -> str:
        return f"# comment\nAPP_URL={self.wiki.url}\nAPI_TOKEN_ID={TOKEN_ID}\nAPI_TOKEN_SECRET={TOKEN_SECRET}\n"

    def test_settings_from_file_named_by_variable(self) -> None:
        self.basic_project()
        env_file = os.path.join(self.tmp.name, "custom.env")
        with open(env_file, "w", encoding="utf-8") as handle:
            handle.write(self._env_file_text())
        self.sync_ok(BOOKSTACK_URL=None, BOOKSTACK_ENV_FILE=env_file)
        self.assertEqual(len(self.wiki.pages), 2)

    def test_settings_from_default_file_in_home(self) -> None:
        self.basic_project()
        folder = os.path.join(self.home, ".config", "opencode", "playbooks", "install-bookstack")
        os.makedirs(folder)
        with open(os.path.join(folder, ".env"), "w", encoding="utf-8") as handle:
            handle.write(self._env_file_text())
        self.sync_ok(BOOKSTACK_TOKEN_SECRET=None)
        self.assertEqual(len(self.wiki.pages), 2)

    def _own_file(self, text: str) -> None:
        folder = os.path.join(self.home, ".config", "agent-plugins")
        os.makedirs(folder)
        with open(os.path.join(folder, "bookstack.env"), "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_settings_from_own_file_in_home(self) -> None:
        self.basic_project()
        self._own_file(f"# my wiki\nBOOKSTACK_URL={self.wiki.url}\nBOOKSTACK_TOKEN_ID = '{TOKEN_ID}'\n"
                       f"BOOKSTACK_TOKEN_SECRET=\"{TOKEN_SECRET}\"\n")
        self.sync_ok(BOOKSTACK_TOKEN_SECRET=None)
        self.assertEqual(len(self.wiki.pages), 2)

    def test_own_file_wins_over_the_older_place(self) -> None:
        self.basic_project()
        folder = os.path.join(self.home, ".config", "opencode", "playbooks", "install-bookstack")
        os.makedirs(folder)
        with open(os.path.join(folder, ".env"), "w", encoding="utf-8") as handle:
            handle.write(f"APP_URL=http://127.0.0.1:9\nAPI_TOKEN_ID={TOKEN_ID}\nAPI_TOKEN_SECRET={TOKEN_SECRET}\n")
        self._own_file(self._env_file_text())
        self.sync_ok(BOOKSTACK_URL=None)
        self.assertEqual(len(self.wiki.pages), 2)

    def test_settings_missing(self) -> None:
        self.basic_project()
        result = self.run_sync(BOOKSTACK_URL=None, BOOKSTACK_TOKEN_ID=None, BOOKSTACK_TOKEN_SECRET=None)
        self.assert_failure(result, "settings are missing", "BOOKSTACK_URL", "BOOKSTACK_ENV_FILE",
                            "bookstack.env", "with the three lines")
        self.assertEqual(self.wiki.requests, [])

    def test_settings_file_without_a_value(self) -> None:
        self.basic_project()
        env_file = os.path.join(self.tmp.name, "partial.env")
        with open(env_file, "w", encoding="utf-8") as handle:
            handle.write(f"APP_URL={self.wiki.url}\nAPI_TOKEN_ID={TOKEN_ID}\n")
        result = self.run_sync(BOOKSTACK_URL=None, BOOKSTACK_ENV_FILE=env_file)
        self.assert_failure(result, "no value for API_TOKEN_SECRET")


class FailureMessageTests(SyncTestCase):
    def test_no_docs_folder(self) -> None:
        elsewhere = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(elsewhere)
        result = self.run_sync(cwd=elsewhere)
        self.assert_failure(result, "no docs/ folder", "project's root folder")

    def test_no_state_file(self) -> None:
        self.write("index.md", "# Home\n")
        result = self.run_sync()
        self.assert_failure(result, "no state file", '{ "shelf": "<PROJECT>", "pages": {} }', "restore")
        self.assertFalse(os.path.exists(self.state_path()))

    def test_no_shelf_value(self) -> None:
        self.write_state({"pages": {}})
        result = self.run_sync()
        self.assert_failure(result, 'has no "shelf" value')

    def test_state_file_not_json(self) -> None:
        self.write_state(None, text="{ not json")
        result = self.run_sync()
        self.assert_failure(result, "could not be read as JSON")

    def test_wiki_cannot_be_reached(self) -> None:
        self.basic_project()
        result = self.run_sync(BOOKSTACK_URL=f"http://127.0.0.1:{free_port()}")
        self.assert_failure(result, "could not reach the wiki", "BookStack is running")

    def test_wiki_answers_with_error(self) -> None:
        self.basic_project()
        result = self.run_sync(BOOKSTACK_TOKEN_SECRET="wrong-secret-value")
        self.assert_failure(result, "HTTP 401", "API token")
        self.assertNotIn("wrong-secret-value", result.stdout + result.stderr)
        self.assertIn("[hidden]", result.stderr)

    def test_page_missing_in_wiki(self) -> None:
        self.basic_project()
        self.write_state({"shelf": "Demo", "pages": {"index.md": 999}})
        result = self.run_sync()
        self.assert_failure(result, "GET /pages/999 with HTTP 404", "remove its entry")

    def test_unknown_option(self) -> None:
        self.basic_project()
        result = self.run_sync("--force")
        self.assert_failure(result, "--force")
        self.assertEqual(self.wiki.requests, [])

    def test_token_never_printed(self) -> None:
        self.basic_project()
        self.sync_ok()
        self.sync_ok("--dry-run")
        self.wiki.expected_auth = "Token other:other"
        self.run_sync()
        # tearDown checks every captured output for the token id and secret
        self.assertEqual(len(self.outputs), 3)


class CommandLineTests(unittest.TestCase):
    def test_help_prints_usage(self) -> None:
        result = subprocess.run([sys.executable, SCRIPT, "--help"], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage: sync_docs_wiki.py", result.stdout)
        self.assertIn("--dry-run", result.stdout)

    def test_standard_library_only_and_type_hints(self) -> None:
        import ast
        with open(SCRIPT, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        allowed = {"__future__", "argparse", "json", "os", "re", "sys", "urllib", "dataclasses", "typing"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertIn(alias.name.split(".")[0], allowed)
            elif isinstance(node, ast.ImportFrom):
                self.assertIn((node.module or "").split(".")[0], allowed)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertIsNotNone(node.returns, node.name)
                for arg in node.args.args + node.args.kwonlyargs:
                    if arg.arg not in ("self", "cls"):
                        self.assertIsNotNone(arg.annotation, f"{node.name}({arg.arg})")


# ---------------------------------------------------------------- pure functions


class FunctionTests(unittest.TestCase):
    def test_title_case(self) -> None:
        self.assertEqual(sdw.title_case("my-big-plans"), "My Big Plans")
        self.assertEqual(sdw.title_case("a--b-"), "A B")
        self.assertEqual(sdw.title_case("API-docs"), "API Docs")

    def test_book_name_for(self) -> None:
        self.assertEqual(sdw.book_name_for(["x.md"]), "Notes")
        self.assertEqual(sdw.book_name_for(["plans", "x.md"]), "Plans")
        self.assertIsNone(sdw.book_name_for(["a", "b", "x.md"]))

    def test_get_title(self) -> None:
        self.assertEqual(sdw.get_title("intro\n#nospace\n# Real  \r\n# Second\n", "f"), "Real")
        self.assertEqual(sdw.get_title("## Sub\n", "fallback"), "fallback")

    def test_remove_title_only_at_top(self) -> None:
        self.assertEqual(sdw.remove_title("# T\n\n\n  Body\n"), "  Body\n")
        self.assertEqual(sdw.remove_title("intro\n# T\nbody\n"), "intro\n# T\nbody\n")
        self.assertEqual(sdw.remove_title("# Only heading"), "# Only heading")

    def test_pick_separator(self) -> None:
        self.assertEqual(sdw.pick_separator(["a.md", "b\\c.md"]), "\\")
        self.assertEqual(sdw.pick_separator(["b/c.md"]), "/")
        self.assertEqual(sdw.pick_separator(["a.md"]), os.sep)
        self.assertEqual(sdw.pick_separator([]), os.sep)

    def test_convert_links(self) -> None:
        docs = os.path.abspath(os.path.join("proj", "docs"))
        ids = {"plans/roadmap.md": "7", "index.md": "3"}
        md = ("[a](roadmap.md#x) [b](../index.md) [c](HTTP://h/x.md) [d](/abs.md) "
              "[e](../../outside.md) [f](plans\\roadmap.md) [g](other.md)")
        out = sdw.convert_links(md, os.path.join(docs, "plans"), docs, ids, "http://w")
        self.assertEqual(out, "[a](http://w/link/7#x) [b](http://w/link/3) [c](HTTP://h/x.md) [d](/abs.md) "
                              "[e](../../outside.md) [f](plans\\roadmap.md) [g](other.md)")


if __name__ == "__main__":
    unittest.main()
