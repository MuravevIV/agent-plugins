"""Tests for scripts/plane.py against a fake Plane that runs inside the test process.

Nothing here contacts a real Plane or reads a real config file: PLANE_* are set by each test, and HOME and
USERPROFILE point at a temporary folder.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parents[1] / "plugins" / "tool" / "skills" / "plane" / "scripts" / "plane.py"
sys.path.insert(0, str(SCRIPT.parent))
import plane  # noqa: E402

KEY = "plk_TEST_secret_0123456789abcdef"
SLUG = "test-ws"


class FakePlane:
    """Just enough of Plane's REST API for the tool."""

    def __init__(self) -> None:
        self.projects: List[Dict[str, Any]] = [
            {"id": "p1", "identifier": "PDX", "name": "Paradox"},
            {"id": "p2", "identifier": "OPS", "name": "Operations"},
        ]
        self.states: Dict[str, List[Dict[str, Any]]] = {"p1": [
            {"id": "s-back", "name": "Backlog", "group": "backlog", "sequence": 1, "default": True},
            {"id": "s-todo", "name": "Todo", "group": "unstarted", "sequence": 2},
            {"id": "s-prog", "name": "In Progress", "group": "started", "sequence": 3},
            {"id": "s-rev", "name": "In Review", "group": "started", "sequence": 4},
            {"id": "s-done", "name": "Done", "group": "completed", "sequence": 5},
            {"id": "s-cxl", "name": "Cancelled", "group": "cancelled", "sequence": 6},
        ], "p2": []}
        self.issues: Dict[str, List[Dict[str, Any]]] = {"p1": [
            {"id": "i1", "sequence_id": 1, "name": "Epic", "state": "s-prog", "parent": None,
             "description_html": "# Plan\n\nDo **it**."},
            {"id": "i2", "sequence_id": 2, "name": "Child task", "state": "s-todo", "parent": "i1",
             "description_html": ""},
            {"id": "i3", "sequence_id": 3, "name": "Done task", "state": "s-done", "parent": "i1",
             "description_html": ""},
            {"id": "i4", "sequence_id": 4, "name": "Dropped", "state": "s-cxl", "parent": None,
             "description_html": ""},
            {"id": "i5", "sequence_id": 5, "name": "Old idea", "state": "s-back", "parent": None,
             "description_html": ""},
        ], "p2": []}
        self.comments: Dict[str, List[Dict[str, Any]]] = {"i1": [
            {"id": "c1", "comment_html": "First note", "created_at": "2026-11-20T10:00:00Z",
             "actor_detail": {"display_name": "ann"}},
        ]}
        self.attachments: Dict[str, List[Dict[str, Any]]] = {"i1": [
            {"id": "a1", "attributes": {"name": "shot.png", "type": "image/png", "size": 4},
             "created_at": "2026-11-21T09:00:00Z"},
        ]}
        self.blobs: Dict[str, bytes] = {"a1": b"\x89PNG"}
        self.asset_server: Optional[str] = None  # when set, downloads redirect there
        self.page_size = 100
        self.plain_lists = False
        self.answer_429 = 0
        self.reject_key = False
        self.requests: List[Tuple[str, str, Dict[str, str], Optional[Dict[str, Any]]]] = []
        self.lock = threading.Lock()

    def page(self, rows: List[Dict[str, Any]], query: Dict[str, List[str]]) -> Any:
        if self.plain_lists:
            return rows
        start = int((query.get("cursor") or ["0"])[0].split(":")[-1])
        chunk = rows[start:start + self.page_size]
        more = start + self.page_size < len(rows)
        return {"results": chunk, "next_page_results": more,
                "next_cursor": f"{self.page_size}:{start + self.page_size}" if more else None}

    def handle(self, method: str, raw_path: str, headers: Dict[str, str],
               body: Optional[Dict[str, Any]]) -> Tuple[int, Any, Dict[str, str]]:
        with self.lock:
            self.requests.append((method, raw_path, headers, body))
            if self.answer_429 > 0:
                self.answer_429 -= 1
                return 429, {"error": "RATE_LIMIT_EXCEEDED"}, {}
        if headers.get("x-api-key") != KEY or self.reject_key:
            return 401, {"detail": f"Invalid API key {headers.get('x-api-key')}"}, {}
        parts = urllib.parse.urlsplit(raw_path)
        query = urllib.parse.parse_qs(parts.query)
        prefix = f"/api/v1/workspaces/{SLUG}/"
        if not parts.path.startswith(prefix):
            return 404, {"detail": "Not found."}, {}
        path = parts.path[len(prefix):]
        m = re.fullmatch(r"projects/", path)
        if m and method == "GET":
            return 200, self.page(self.projects, query), {}
        m = re.fullmatch(r"projects/([^/]+)/states/", path)
        if m and method == "GET":
            return 200, self.page(self.states.get(m.group(1), []), query), {}
        m = re.fullmatch(r"projects/([^/]+)/issues/", path)
        if m:
            rows = self.issues.setdefault(m.group(1), [])
            if method == "GET":
                return 200, self.page(rows, query), {}
            if method == "POST":
                new = {"id": f"i{100 + len(rows)}", "sequence_id": max([r["sequence_id"] for r in rows] + [0]) + 1,
                       "name": body["name"], "description_html": body.get("description_html", ""),
                       "parent": body.get("parent"), "state": body.get("state", "s-back")}
                rows.append(new)
                return 201, new, {}
        m = re.fullmatch(r"projects/([^/]+)/issues/([^/]+)/", path)
        if m:
            issue = next((i for i in self.issues.get(m.group(1), []) if i["id"] == m.group(2)), None)
            if issue is None:
                return 404, {"detail": "Not found."}, {}
            if method == "GET":
                return 200, issue, {}
            if method == "PATCH":
                issue.update(body or {})
                return 200, issue, {}
        m = re.fullmatch(r"projects/([^/]+)/issues/([^/]+)/comments/", path)
        if m:
            rows = self.comments.setdefault(m.group(2), [])
            if method == "GET":
                return 200, self.page(rows, query), {}
            if method == "POST":
                new = {"id": f"c{100 + len(rows)}", "comment_html": body["comment_html"],
                       "created_at": "2026-11-22T12:00:00Z"}
                rows.append(new)
                return 201, new, {}
        m = re.fullmatch(r"projects/([^/]+)/issues/([^/]+)/issue-attachments/", path)
        if m and method == "GET":
            return 200, self.attachments.get(m.group(2), []), {}
        m = re.fullmatch(r"projects/([^/]+)/issues/([^/]+)/issue-attachments/([^/]+)/", path)
        if m and method == "GET":
            if m.group(3) not in self.blobs:
                return 404, {"detail": "Not found."}, {}
            if self.asset_server:
                return 302, b"", {"Location": f"{self.asset_server}/asset/{m.group(3)}"}
            return 200, self.blobs[m.group(3)], {"Content-Type": "image/png"}
        return 404, {"detail": "Not found."}, {}


class AssetStore:
    """A second origin, standing in for the signed file links Plane redirects to."""

    def __init__(self, blobs: Dict[str, bytes]) -> None:
        self.blobs = blobs
        self.requests: List[Dict[str, str]] = []

    def handle(self, method: str, raw_path: str, headers: Dict[str, str],
               body: Optional[Dict[str, Any]]) -> Tuple[int, Any, Dict[str, str]]:
        self.requests.append(headers)
        name = raw_path.rsplit("/", 1)[-1]
        if name in self.blobs:
            return 200, self.blobs[name], {"Content-Type": "application/octet-stream"}
        return 404, b"", {}


def serve(app: Any) -> Tuple[ThreadingHTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def answer(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw) if raw else None
            headers = {k.lower(): v for k, v in self.headers.items()}
            code, payload, extra = app.handle(self.command, self.path, headers, body)
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
            self.send_response(code)
            if "Content-Type" not in extra and not isinstance(payload, bytes):
                self.send_header("Content-Type", "application/json")
            for k, v in extra.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PATCH = answer

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class PlaneTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakePlane()
        self.server, self.base = serve(self.fake)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        env = {"PLANE_BASE_URL": self.base, "PLANE_WORKSPACE_SLUG": SLUG, "PLANE_API_KEY": KEY,
               "PLANE_RETRY_WAIT": "0", "PLANE_RETRY_COUNT": "3",
               "HOME": self.home.name, "USERPROFILE": self.home.name}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("PLANE_CONFIG_FILE", None)
        plane._SECRETS.clear()

    def run_tool(self, *args: str) -> Tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = plane.main(list(args))
            except SystemExit as e:
                code = int(e.code or 0)
        self.assertNotIn(KEY, out.getvalue())
        self.assertNotIn(KEY, err.getvalue())
        return code, out.getvalue(), err.getvalue()

    def ok(self, *args: str) -> Any:
        code, out, err = self.run_tool(*args)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def fails(self, *args: str, code: int = 1) -> str:
        got, out, err = self.run_tool(*args)
        self.assertEqual(got, code, err)
        self.assertEqual(out, "")
        return err


class CommandTests(PlaneTestCase):
    def test_projects(self) -> None:
        self.assertEqual([p["identifier"] for p in self.ok("projects")], ["PDX", "OPS"])

    def test_states(self) -> None:
        states = self.ok("states", "pdx")
        self.assertIn({"id": "s-done", "name": "Done", "group": "completed"}, states)

    def test_list(self) -> None:
        rows = self.ok("list", "PDX")
        self.assertEqual([r["key"] for r in rows], ["PDX-1", "PDX-2", "PDX-3", "PDX-4", "PDX-5"])
        child = rows[1]
        self.assertEqual(child, {"key": "PDX-2", "id": "i2", "name": "Child task", "state": "Todo",
                                 "group": "unstarted", "parent": "PDX-1",
                                 "url": f"{self.base}/{SLUG}/browse/PDX-2/"})

    def test_list_open_and_group(self) -> None:
        self.assertEqual([r["key"] for r in self.ok("list", "PDX", "--open")], ["PDX-1", "PDX-2", "PDX-5"])
        rows = self.ok("list", "PDX", "--group", "started", "--group", "backlog")
        self.assertEqual([r["key"] for r in rows], ["PDX-1", "PDX-5"])

    def test_list_over_two_pages(self) -> None:
        self.fake.page_size = 3
        self.assertEqual(len(self.ok("list", "PDX")), 5)
        issue_calls = [r[1] for r in self.fake.requests if "/issues/" in r[1]]
        self.assertEqual(len(issue_calls), 2)
        self.assertIn("cursor=", issue_calls[1])

    def test_list_plain_list_answer(self) -> None:
        self.fake.plain_lists = True
        self.assertEqual(len(self.ok("list", "PDX")), 5)

    def test_show(self) -> None:
        shown = self.ok("show", "PDX-1")
        self.assertEqual(shown["state"], "In Progress")
        self.assertEqual(shown["group"], "started")
        self.assertEqual(shown["description"], "# Plan\n\nDo **it**.")
        self.assertEqual(shown["children"], ["PDX-2", "PDX-3"])
        self.assertEqual(shown["comments"][0]["text"], "First note")
        self.assertEqual(shown["comments"][0]["author"], "ann")
        self.assertIsNone(shown["parent"])

    def test_create(self) -> None:
        made = self.ok("create", "PDX", "--name", "New task", "--parent", "PDX-1", "--group", "unstarted",
                       "--description", "Some *markdown*")
        self.assertEqual(made["key"], "PDX-6")
        self.assertEqual(made["parent"], "PDX-1")
        self.assertEqual(made["state"], "Todo")
        body = [r[3] for r in self.fake.requests if r[0] == "POST"][0]
        self.assertEqual(body, {"name": "New task", "description_html": "Some *markdown*", "parent": "i1",
                                "state": "s-todo"})

    def test_create_description_file(self) -> None:
        path = Path(self.home.name) / "d.md"
        path.write_text("From a file\n", encoding="utf-8")
        self.ok("create", "PDX", "--name", "Filed", "--description-file", str(path))
        self.assertEqual(self.fake.issues["p1"][-1]["description_html"], "From a file\n")

    def test_update(self) -> None:
        changed = self.ok("update", "PDX-2", "--name", "Renamed", "--group", "started")
        self.assertEqual((changed["name"], changed["state"]), ("Renamed", "In Progress"))
        self.assertEqual(self.fake.issues["p1"][1]["state"], "s-prog")

    def test_update_same_group_keeps_state(self) -> None:
        self.fake.issues["p1"][0]["state"] = "s-rev"
        self.ok("update", "PDX-1", "--group", "started")
        self.assertEqual([r for r in self.fake.requests if r[0] == "PATCH"], [])
        self.assertEqual(self.fake.issues["p1"][0]["state"], "s-rev")

    def test_update_parent_and_description(self) -> None:
        changed = self.ok("update", "PDX-5", "--parent", "PDX-1", "--description", "New text")
        self.assertEqual(changed["parent"], "PDX-1")
        self.assertEqual(self.fake.issues["p1"][4]["description_html"], "New text")

    def test_update_without_changes_is_usage_error(self) -> None:
        self.fails("update", "PDX-1", code=2)

    def test_comment_and_comments(self) -> None:
        made = self.ok("comment", "PDX-1", "--text", "Done: **tests** pass")
        self.assertEqual(made["key"], "PDX-1")
        texts = [c["text"] for c in self.ok("comments", "PDX-1")]
        self.assertEqual(texts, ["First note", "Done: **tests** pass"])

    def test_comment_from_file(self) -> None:
        path = Path(self.home.name) / "c.md"
        path.write_text("Note from file", encoding="utf-8")
        self.ok("comment", "PDX-2", "--file", str(path))
        self.assertEqual(self.fake.comments["i2"][0]["comment_html"], "Note from file")

    def test_attachments(self) -> None:
        self.assertEqual(self.ok("attachments", "PDX-1"),
                         [{"id": "a1", "name": "shot.png", "type": "image/png", "size": 4,
                           "created_at": "2026-11-21T09:00:00Z"}])

    def test_download(self) -> None:
        out = Path(self.home.name) / "sub" / "shot.png"
        result = self.ok("download", "PDX-1", "a1", "--out", str(out))
        self.assertEqual(out.read_bytes(), b"\x89PNG")
        self.assertEqual(result["bytes"], 4)

    def test_download_redirect_does_not_carry_key(self) -> None:
        store = AssetStore({"a1": b"signed-bytes"})
        server, base = serve(store)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.fake.asset_server = base  # another port, so another origin
        out = Path(self.home.name) / "shot.png"
        self.ok("download", "PDX-1", "a1", "--out", str(out))
        self.assertEqual(out.read_bytes(), b"signed-bytes")
        self.assertEqual(len(store.requests), 1)
        self.assertNotIn("x-api-key", store.requests[0])


class FailureTests(PlaneTestCase):
    def test_429_then_success(self) -> None:
        self.fake.answer_429 = 2
        self.assertEqual(len(self.ok("projects")), 2)
        self.assertEqual(len(self.fake.requests), 3)

    def test_429_that_does_not_stop(self) -> None:
        self.fake.answer_429 = 100
        err = self.fails("projects")
        self.assertIn("429", err)
        self.assertIn("Why it matters", err)
        self.assertIn("What to do next", err)

    def test_unknown_key(self) -> None:
        err = self.fails("show", "PDX-99")
        self.assertIn("There is no ticket PDX-99 in project PDX.", err)
        self.assertIn("plane.py list PDX", err)

    def test_unknown_project(self) -> None:
        err = self.fails("list", "NOPE")
        self.assertIn("There is no project NOPE", err)
        self.assertIn("OPS, PDX", err)
        self.assertNotIn("Traceback", err)

    def test_malformed_key_is_usage_error(self) -> None:
        self.fails("show", "not-a-key", code=2)

    def test_missing_group_state(self) -> None:
        err = self.fails("create", "OPS", "--name", "x", "--group", "started")
        self.assertIn("no state in the group started", err)
        self.assertEqual([r for r in self.fake.requests if r[0] == "POST"], [])

    def test_missing_description_file(self) -> None:
        err = self.fails("create", "PDX", "--name", "x", "--description-file", str(Path(self.home.name) / "no.md"))
        self.assertIn("could not be read", err)
        self.assertEqual(self.fake.requests, [])

    def test_missing_settings(self) -> None:
        del os.environ["PLANE_API_KEY"]
        del os.environ["PLANE_BASE_URL"]
        err = self.fails("projects")
        self.assertIn("No value for PLANE_BASE_URL, PLANE_API_KEY", err)
        self.assertIn(self.home.name, err)  # it looked in the (temporary) home folder, not the real one
        self.assertIn("What to do next", err)

    def test_missing_config_file_named(self) -> None:
        del os.environ["PLANE_API_KEY"]
        os.environ["PLANE_CONFIG_FILE"] = str(Path(self.home.name) / "absent.json")
        self.assertIn("does not exist", self.fails("projects"))

    def test_rejected_key_is_hidden(self) -> None:
        self.fake.reject_key = True
        err = self.fails("projects")
        self.assertIn("refused the API key", err)

    def test_key_hidden_in_echoed_error(self) -> None:
        os.environ["PLANE_API_KEY"] = KEY + "x"  # wrong key: the fake echoes it back in the 401 body
        got, out, err = self.run_tool("projects")
        self.assertEqual(got, 1)
        self.assertNotIn(KEY + "x", err)

    def test_unreachable_plane(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        err = self.fails("projects")
        self.assertIn("could not be reached", err)


class SettingsFileTests(PlaneTestCase):
    def write_config(self, path: Path, base: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "{\n"
            "  // OpenCode style config with comments\n"
            '  "$schema": "https://opencode.ai/config.json",\n'
            '  "mcp": {\n'
            '    "github": {"environment": {"TOKEN": "x"}},\n'
            '    "plane": {\n'
            '      "type": "local", /* inline comment */\n'
            '      "environment": {\n'
            f'        "PLANE_BASE_URL": "{base}",\n'
            f'        "PLANE_WORKSPACE_SLUG": "{SLUG}",\n'
            f'        "PLANE_API_KEY": "{KEY}",\n'
            "      },\n"
            "    },\n"
            "  },\n"
            "}\n", encoding="utf-8")

    def clear_env(self) -> None:
        for name in plane.NAMES:
            os.environ.pop(name, None)

    def test_config_file_named_by_env(self) -> None:
        self.clear_env()
        path = Path(self.home.name) / "plane.jsonc"
        self.write_config(path, self.base)
        os.environ["PLANE_CONFIG_FILE"] = str(path)
        self.assertEqual(len(self.ok("projects")), 2)

    def test_default_config_file_in_home(self) -> None:
        self.clear_env()
        self.write_config(Path(self.home.name) / ".config" / "opencode" / "opencode.json", self.base)
        self.assertEqual(len(self.ok("projects")), 2)

    def test_environment_wins_over_file(self) -> None:
        path = Path(self.home.name) / "plane.json"
        self.write_config(path, "http://127.0.0.1:9")  # nothing listens there
        os.environ["PLANE_CONFIG_FILE"] = str(path)
        self.assertEqual(len(self.ok("projects")), 2)

    def test_strip_comments_keeps_strings(self) -> None:
        text = '{"a": "http://x//y", "b": "/* no */", // c\n "c": [1,2,],}'
        self.assertEqual(json.loads(plane.strip_json_comments(text)),
                         {"a": "http://x//y", "b": "/* no */", "c": [1, 2]})


class CommandLineTests(unittest.TestCase):
    def test_help(self) -> None:
        done = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
        self.assertEqual(done.returncode, 0)
        self.assertIn("usage: plane.py", done.stdout)
        for command in ("projects", "states", "list", "show", "create", "update", "comment", "comments",
                        "attachments", "download"):
            self.assertIn(command, done.stdout)

    def test_missing_settings_as_a_process(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            env = {k: v for k, v in os.environ.items() if not k.startswith("PLANE_")}
            env.update({"HOME": home, "USERPROFILE": home})
            done = subprocess.run([sys.executable, str(SCRIPT), "projects"], capture_output=True, text=True,
                                  env=env, timeout=60)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout, "")
        self.assertIn("No value for", done.stderr)

    def test_wrong_usage_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            env = {k: v for k, v in os.environ.items() if not k.startswith("PLANE_")}
            env.update({"HOME": home, "USERPROFILE": home})
            done = subprocess.run([sys.executable, str(SCRIPT), "comment", "PDX-1"], capture_output=True,
                                  text=True, env=env, timeout=60)
        self.assertEqual(done.returncode, 2)


if __name__ == "__main__":
    unittest.main()
