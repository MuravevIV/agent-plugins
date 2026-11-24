#!/usr/bin/env python3
"""Mirror a project's docs/ folder to its shelf in a BookStack wiki.

Run it from the project root after changing docs. Git is the source of truth;
docs/.wiki-sync.json holds {"shelf": "<name>", "pages": {"<relative path>": <page id>}}.

Mapping:
  docs/*.md        -> the book "Notes" (pages cannot sit on a shelf directly)
  docs/<dir>/*.md  -> a book named from <dir> (kebab case to Title Case)
  deeper nesting   -> skipped with a warning

The shelf is created when missing. Books are looked up on that shelf only and
created and added to it when missing. Relative .md links between docs are
rewritten to {APP_URL}/link/{page_id} permalinks. Two phases: first every file
without a page id gets a page (so links inside the same run resolve), then links
are rewritten and every page that differs is pushed. Nothing is ever deleted in
the wiki; a doc that is gone only gives a warning.

Python 3.9 or later, standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, NoReturn, Optional, Sequence, Set, Tuple

DEFAULT_BOOK_NAME = "Notes"
STATE_FILE_NAME = ".wiki-sync.json"
# Where the settings file is looked for when BOOKSTACK_ENV_FILE is not set: this tool's own place first, then
# an older place that is still read.
OWN_ENV_FILE = "~/.config/agent-plugins/bookstack.env"
OLDER_ENV_FILE = "~/.config/opencode/playbooks/install-bookstack/.env"
# (environment variable, name in the settings file)
SETTING_NAMES: Tuple[Tuple[str, str], ...] = (
    ("BOOKSTACK_URL", "APP_URL"),
    ("BOOKSTACK_TOKEN_ID", "API_TOKEN_ID"),
    ("BOOKSTACK_TOKEN_SECRET", "API_TOKEN_SECRET"),
)
TIMEOUT_SECONDS = 60
BOOTSTRAP_CONTENT = '{ "shelf": "<PROJECT>", "pages": {} }'
NEW_PAGE_PLACEHOLDER = "<new page>"

LINK_RE = re.compile(r"\]\(([^)#]+\.md)(#[^)]*)?\)")
URL_RE = re.compile(r"^[a-z]+://", re.IGNORECASE)
DRIVE_RE = re.compile(r"^[A-Za-z]:")
TITLE_LINE_RE = re.compile(r"^# ")
TITLE_BLOCK_RE = re.compile(r"^\s*# [^\r\n]*\r?\n(\s*\r?\n)*")


class SyncError(Exception):
    """A failure explained in three parts: what happened, why it matters, what to do."""

    def __init__(self, what: str, why: str, next_step: str) -> None:
        super().__init__(what)
        self.what = what
        self.why = why
        self.next_step = next_step

    def render(self) -> str:
        return f"error: {self.what}\nwhy it matters: {self.why}\nwhat to do: {self.next_step}"


def warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr, flush=True)


def say(message: str) -> None:
    print(message, flush=True)


# ---------------------------------------------------------------- settings


@dataclass
class Settings:
    url: str
    token_id: str
    token_secret: str


def load_settings(environ: Mapping[str, str]) -> Settings:
    """Environment variables first; if not all set, the settings file."""
    values = [environ.get(var, "") for var, _ in SETTING_NAMES]
    if all(values):
        return Settings(values[0].rstrip("/"), values[1], values[2])

    own, older = os.path.expanduser(OWN_ENV_FILE), os.path.expanduser(OLDER_ENV_FILE)
    env_file = environ.get("BOOKSTACK_ENV_FILE") or (older if os.path.isfile(older) and not os.path.isfile(own)
                                                      else own)
    env_vars = ", ".join(var for var, _ in SETTING_NAMES)
    if not os.path.isfile(env_file):
        raise SyncError(
            f"the wiki settings are missing: the environment variables {env_vars} are not all set, "
            f"and the settings file {env_file} does not exist",
            "without the wiki's address and an API token the script cannot read or change the wiki, "
            "so nothing was synced",
            f"create the file {own} with the three lines BOOKSTACK_URL=..., BOOKSTACK_TOKEN_ID=... and "
            "BOOKSTACK_TOKEN_SECRET=..., or set those three as environment variables, or point "
            "BOOKSTACK_ENV_FILE at a file that holds them, then run the script again",
        )
    try:
        with open(env_file, encoding="utf-8-sig") as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeDecodeError) as err:
        raise SyncError(
            f"the settings file {env_file} could not be read ({type(err).__name__})",
            "the wiki's address and API token are in it, so the script cannot reach the wiki",
            "check that the file exists, is readable and is UTF-8 text, then run the script again",
        ) from None

    found: Dict[str, str] = {}
    for line in lines:
        key, equals, value = line.strip().partition("=")
        for var, name in SETTING_NAMES:  # a line may use either name: BOOKSTACK_URL=... or APP_URL=...
            if equals and key.strip() in (var, name) and name not in found:
                found[name] = value.strip().strip("\"'").strip()
    missing = [name for _, name in SETTING_NAMES if not found.get(name)]
    if missing:
        raise SyncError(
            f"the settings file {env_file} has no value for {', '.join(missing)}",
            "the script needs the wiki's address and both parts of the API token to reach the wiki, "
            "so nothing was synced",
            "add the missing lines in the form NAME=value, or set the environment variables "
            f"{env_vars}, then run the script again",
        )
    return Settings(found["APP_URL"].rstrip("/"), found["API_TOKEN_ID"], found["API_TOKEN_SECRET"])


# ---------------------------------------------------------------- wiki access


class Wiki:
    """A small BookStack API client that never shows the token."""

    def __init__(self, settings: Settings, dry_run: bool) -> None:
        self.url = settings.url
        self.base = settings.url + "/api"
        self._auth = f"Token {settings.token_id}:{settings.token_secret}"
        self._secrets = [s for s in (settings.token_secret, settings.token_id) if len(s) >= 4]
        self.dry_run = dry_run

    def hide_secrets(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "[hidden]")
        return text

    def _stopped(self) -> str:
        if self.dry_run:
            return "the dry run stopped here; it changes nothing, so the wiki and the state file are as before"
        return (
            "the sync stopped here; pages created before this point are already recorded in "
            "docs/.wiki-sync.json and nothing in the wiki was deleted, but some docs are not synced yet"
        )

    def call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        headers = {"Authorization": self._auth, "Accept": "application/json"}
        data: Optional[bytes] = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read()
        except urllib.error.HTTPError as err:
            raise self._answer_error(method, path, err) from None
        except urllib.error.URLError as err:
            raise self._unreachable(str(err.reason)) from None
        except ValueError as err:
            raise SyncError(
                f"the wiki address {self.hide_secrets(self.url)!r} is not a valid web address "
                f"({self.hide_secrets(str(err))})",
                "the script cannot reach the wiki, so nothing was synced",
                "set BOOKSTACK_URL (or APP_URL in the settings file) to the wiki's main address, "
                "for example http://localhost:8091, then run the script again",
            ) from None
        except OSError as err:
            raise self._unreachable(str(err) or type(err).__name__) from None
        if not raw.strip():
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise SyncError(
                f"the wiki at {self.url} answered {method} {path} with something that is not JSON",
                "the address may point to something other than the BookStack wiki; " + self._stopped(),
                "check that BOOKSTACK_URL (or APP_URL) is the wiki's main address without /api, "
                "then run the script again",
            ) from None

    def _unreachable(self, reason: str) -> SyncError:
        return SyncError(
            f"could not reach the wiki at {self.url} ({self.hide_secrets(reason)})",
            self._stopped(),
            "check that BookStack is running and that BOOKSTACK_URL (or APP_URL in the settings file) "
            "is right, then run the script again; it is safe to run again",
        )

    def _answer_error(self, method: str, path: str, err: urllib.error.HTTPError) -> SyncError:
        detail = ""
        try:
            text = err.read().decode("utf-8", "replace")
        except OSError:
            text = ""
        try:
            payload = json.loads(text)
            message = payload["error"]["message"]
            if isinstance(message, str):
                detail = message
        except (ValueError, KeyError, TypeError):
            detail = " ".join(text.split())[:300]
        detail = self.hide_secrets(detail)
        what = f"the wiki answered {method} {path} with HTTP {err.code}"
        if detail:
            what += f": {detail}"
        if err.code in (401, 403):
            hint = "check that the API token is right and that its user may read and change this shelf"
        elif err.code == 404:
            hint = (
                "an id the script used does not exist in the wiki; if a page listed in "
                "docs/.wiki-sync.json was deleted in the wiki, restore it there or remove its entry "
                "so the script creates the page again"
            )
        elif err.code == 422:
            hint = "the wiki refused the content; check the message and the doc it is about"
        else:
            hint = "check that the wiki works (open it in a browser, look at its logs)"
        return SyncError(what, self._stopped(), hint + ", then run the script again; it is safe to run again")


# ---------------------------------------------------------------- state file


def norm_key(path: str) -> str:
    """The form used to match paths: either slash, upper and lower case alike."""
    return "/".join(re.split(r"[\\/]", path)).lower()


def pick_separator(keys: Sequence[str]) -> str:
    """Keep the slash already used in the state file; else the system's."""
    for key in keys:
        if "\\" in key:
            return "\\"
        if "/" in key:
            return "/"
    return os.sep


def _page_id_value(key: str, value: Any, path: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise SyncError(
        f"{path} gives {key!r} the page id {value!r}, which is not a whole number",
        "the script uses these ids to find the wiki page of each doc and cannot sync with a broken one",
        "fix the entry (restore the file from Git if needed), then run the script again",
    )


class StateFile:
    """docs/.wiki-sync.json: the shelf name and the page id of each doc."""

    def __init__(self, path: str) -> None:
        self.path = path
        if not os.path.isfile(path):
            raise SyncError(
                f"there is no state file at {path}",
                "this file names the wiki shelf and records the wiki page of every doc; without it "
                "the script cannot tell which pages already exist",
                f"for a project that was never mirrored, create it with the content {BOOTSTRAP_CONTENT}, "
                "putting the project's name as the shelf; for a project that was mirrored before, "
                "restore the file from Git instead, because an empty one makes duplicate pages",
            )
        shape = f"its shape is {BOOTSTRAP_CONTENT} with page ids in \"pages\""
        try:
            with open(path, encoding="utf-8-sig") as handle:
                raw = json.load(handle)
        except (OSError, UnicodeDecodeError, ValueError) as err:
            raise SyncError(
                f"{path} could not be read as JSON ({err})",
                "the script cannot read the shelf name and page ids from it, so it cannot sync safely",
                f"fix the file or restore it from Git ({shape}), then run the script again",
            ) from None
        if not isinstance(raw, dict):
            raise SyncError(
                f"{path} does not hold a JSON object",
                "the script cannot read the shelf name and page ids from it, so it cannot sync safely",
                f"fix the file or restore it from Git ({shape}), then run the script again",
            )
        shelf = raw.get("shelf")
        if not isinstance(shelf, str) or not shelf:
            raise SyncError(
                f'{path} has no "shelf" value',
                "the shelf name says where in the wiki the docs go; without it the script does not "
                "know where to put them",
                f'add "shelf": "<PROJECT>" with the project\'s name, as in {BOOTSTRAP_CONTENT}, '
                "then run the script again",
            )
        pages_raw = raw.get("pages")
        if pages_raw and not isinstance(pages_raw, dict):
            raise SyncError(
                f'"pages" in {path} is not a JSON object',
                "the script cannot read the page ids from it, so it cannot sync safely",
                f"fix the file or restore it from Git ({shape}), then run the script again",
            )
        self.raw: Dict[str, Any] = raw
        self.shelf: str = shelf
        self.pages: Dict[str, int] = {}
        for key, value in (pages_raw or {}).items():
            self.pages[key] = _page_id_value(key, value, path)
        self._index: Dict[str, str] = {}
        for key in self.pages:
            self._index.setdefault(norm_key(key), key)
        self.sep = pick_separator(list(self.pages))

    def find(self, parts: Sequence[str]) -> Optional[str]:
        """The key in the file for this doc, whatever slash or case it was written with."""
        return self._index.get(norm_key("/".join(parts)))

    def add(self, parts: Sequence[str], page_id: int) -> str:
        key = self.sep.join(parts)
        self.pages[key] = page_id
        self._index.setdefault(norm_key(key), key)
        return key

    def content(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"shelf": self.shelf}
        for name, value in self.raw.items():
            if name != "shelf":
                data[name] = value
        data["pages"] = dict(self.pages)
        return data

    def save_if_changed(self) -> bool:
        data = self.content()
        if data == self.raw:
            return False
        text = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
        temp_path = self.path + ".tmp"
        try:
            with open(temp_path, "w", encoding="ascii", newline="\n") as handle:
                handle.write(text)
            os.replace(temp_path, self.path)
        except OSError as err:
            raise SyncError(
                f"could not write {self.path} ({err})",
                "the file records which wiki pages belong to which docs; pages created in this run "
                "may now be missing from it, and running again would create them twice",
                "make the file writable, then add the page ids printed above as \"created:\" lines "
                "to it by hand before running the script again",
            ) from None
        self.raw = data
        return True


# ---------------------------------------------------------------- markdown


def title_case(dir_name: str) -> str:
    """kebab-case directory name to a Title Case book name."""
    words = [word[0].upper() + word[1:] for word in dir_name.split("-") if word]
    return " ".join(words)


def book_name_for(parts: Sequence[str]) -> Optional[str]:
    if len(parts) == 1:
        return DEFAULT_BOOK_NAME
    if len(parts) > 2:
        return None
    return title_case(parts[0])


def get_title(markdown: str, fallback: str) -> str:
    """The first line starting with '# ', else the fallback."""
    for line in markdown.split("\n"):
        if TITLE_LINE_RE.match(line):
            return line[2:].strip()
    return fallback


def remove_title(markdown: str) -> str:
    """Drop a heading at the very top and the blank lines after it (BookStack shows the name)."""
    return TITLE_BLOCK_RE.sub("", markdown, count=1)


def convert_links(
    markdown: str, file_dir: str, docs_dir: str, page_ids: Mapping[str, str], app_url: str
) -> str:
    """Rewrite relative .md links to docs that have a page into {APP_URL}/link/{id} permalinks."""
    prefix = docs_dir.rstrip("\\/") + os.sep

    def replace(match: re.Match[str]) -> str:
        target = match.group(1)
        anchor = match.group(2) or ""
        if URL_RE.match(target) or target.startswith(("/", "\\")) or DRIVE_RE.match(target):
            return match.group(0)
        local = target.replace("\\", os.sep).replace("/", os.sep)
        try:
            full = os.path.normpath(os.path.join(file_dir, local))
        except ValueError:
            return match.group(0)
        if not full.startswith(prefix):
            return match.group(0)
        page_id = page_ids.get(norm_key(full[len(prefix):]))
        if page_id is None:
            return match.group(0)
        return f"]({app_url}/link/{page_id}{anchor})"

    return LINK_RE.sub(replace, markdown)


def read_doc(path: str) -> str:
    """UTF-8 with or without a byte order mark; line endings kept as they are."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return handle.read()
    except UnicodeDecodeError:
        raise SyncError(
            f"{path} is not UTF-8 text",
            "the script would push garbled text to the wiki, so it stopped before that doc",
            "save the file as UTF-8, then run the script again; it is safe to run again",
        ) from None
    except OSError as err:
        raise SyncError(
            f"could not read {path} ({err})",
            "the doc cannot be synced while it cannot be read, so the script stopped",
            "check the file, then run the script again; it is safe to run again",
        ) from None


# ---------------------------------------------------------------- sync


@dataclass
class DocFile:
    parts: List[str]
    full_path: str
    base_name: str
    book_name: str
    display: str


def collect_files(docs_dir: str, sep: str) -> List[DocFile]:
    """Every .md file under docs/, sorted by path; deeper nesting skipped with a warning."""

    def on_error(err: OSError) -> None:
        raise SyncError(
            f"could not list {err.filename} ({err.strerror})",
            "docs inside it would be left out, so the script stopped before changing anything",
            "check the folder's permissions, then run the script again",
        )

    found: List[Tuple[List[str], str, str]] = []
    for current, _dirs, names in os.walk(docs_dir, onerror=on_error):
        for name in names:
            if name.lower().endswith(".md"):
                full = os.path.join(current, name)
                parts = os.path.relpath(full, docs_dir).split(os.sep)
                found.append((parts, full, name))
    found.sort(key=lambda item: item[0])

    files: List[DocFile] = []
    for parts, full, name in found:
        display = sep.join(parts)
        book = book_name_for(parts)
        if book is None:
            warn(f"{display} is nested too deep (max docs/<book>/page.md) - skipped")
            continue
        files.append(DocFile(parts, full, os.path.splitext(name)[0], book, display))
    return files


def page_id_from(answer: Any, what: str, wiki: Wiki) -> int:
    try:
        return int(answer["id"])
    except (TypeError, KeyError, ValueError):
        raise SyncError(
            f"the wiki's answer to {what} has no id",
            "the script needs the id to record or update the page; " + wiki._stopped(),
            "check that the address points at a BookStack wiki, then run the script again",
        ) from None


def same_name(value: Any, name: str) -> bool:
    """Shelf and book names match ignoring case, as the PowerShell script did."""
    return isinstance(value, str) and value.casefold() == name.casefold()


class Syncer:
    def __init__(self, root: str, dry_run: bool, environ: Mapping[str, str]) -> None:
        self.root = root
        self.dry_run = dry_run
        self.environ = environ
        self._shelf_looked_up = False
        self._shelf_id: Optional[int] = None
        self._book_ids: Dict[str, Optional[int]] = {}

    def shelf_id(self) -> Optional[int]:
        if self._shelf_looked_up:
            return self._shelf_id
        answer = self.wiki.call("GET", "/shelves?count=500")
        shelves = answer.get("data", []) if isinstance(answer, dict) else []
        hit = next((s for s in shelves if isinstance(s, dict) and same_name(s.get("name"), self.state.shelf)), None)
        if hit is not None:
            self._shelf_id = page_id_from(hit, "the shelf list", self.wiki)
        elif self.dry_run:
            say(f"would create shelf: {self.state.shelf}")
            self._shelf_id = None
        else:
            name = self.state.shelf
            created = self.wiki.call(
                "POST",
                "/shelves",
                {"name": name, "description": f"{name} - project docs (mirror of git docs/ in {self.root})"},
            )
            self._shelf_id = page_id_from(created, "POST /shelves", self.wiki)
            say(f"created shelf: {name} (id {self._shelf_id})")
        self._shelf_looked_up = True
        return self._shelf_id

    def book_id(self, name: str) -> Optional[int]:
        cache_key = name.casefold()
        if cache_key in self._book_ids:
            return self._book_ids[cache_key]
        shelf_id = self.shelf_id()
        books: List[Any] = []
        if shelf_id is not None:
            answer = self.wiki.call("GET", f"/shelves/{shelf_id}")
            books = [b for b in (answer.get("books") or []) if isinstance(b, dict)] if isinstance(answer, dict) else []
        hit = next((b for b in books if same_name(b.get("name"), name)), None)
        book_id: Optional[int]
        if hit is not None:
            book_id = page_id_from(hit, f"GET /shelves/{shelf_id}", self.wiki)
        elif self.dry_run:
            book_id = None
        else:
            created = self.wiki.call(
                "POST", "/books", {"name": name, "description": f"{self.state.shelf} docs (mirror of git docs/)"}
            )
            book_id = page_id_from(created, "POST /books", self.wiki)
            book_ids = [b.get("id") for b in books] + [book_id]
            self.wiki.call("PUT", f"/shelves/{shelf_id}", {"books": book_ids})
        self._book_ids[cache_key] = book_id
        return book_id

    def run(self) -> None:
        docs_dir = os.path.join(os.path.abspath(self.root), "docs")
        if not os.path.isdir(docs_dir):
            raise SyncError(
                f"there is no docs/ folder in {self.root}",
                "the script mirrors the docs/ folder of the project it is run from, so here it has "
                "nothing to sync",
                "run it from the project's root folder, the one that contains docs/",
            )
        self.state = StateFile(os.path.join(docs_dir, STATE_FILE_NAME))
        settings = load_settings(self.environ)
        self.wiki = Wiki(settings, self.dry_run)
        files = collect_files(docs_dir, self.state.sep)

        link_ids: Dict[str, str] = {norm_key(k): str(v) for k, v in self.state.pages.items()}
        new_in_dry_run: Set[str] = set()

        # phase 1: every file gets a page id, so links inside this run resolve
        created = 0
        for doc in files:
            if self.state.find(doc.parts) is not None:
                continue
            markdown = read_doc(doc.full_path)
            book_id = self.book_id(doc.book_name)
            if self.dry_run:
                link_ids[norm_key(doc.display)] = NEW_PAGE_PLACEHOLDER
                new_in_dry_run.add(doc.full_path)
                say(f"would create: {doc.display} (book {doc.book_name})")
                created += 1
                continue
            page = self.wiki.call(
                "POST",
                "/pages",
                {"book_id": book_id, "name": get_title(markdown, doc.base_name), "markdown": remove_title(markdown)},
            )
            page_id = page_id_from(page, "POST /pages", self.wiki)
            self.state.add(doc.parts, page_id)
            self.state.save_if_changed()
            link_ids[norm_key(doc.display)] = str(page_id)
            say(f"created: {doc.display} -> page {page_id} (book {doc.book_name})")
            created += 1

        # phase 2: rewrite links and push every page that differs
        updated = 0
        unchanged = 0
        for doc in files:
            if doc.full_path in new_in_dry_run:
                continue
            key = self.state.find(doc.parts)
            assert key is not None
            markdown = read_doc(doc.full_path)
            rendered = convert_links(
                markdown, os.path.dirname(doc.full_path), docs_dir, link_ids, self.wiki.url
            )
            title = get_title(rendered, doc.base_name)
            rendered = remove_title(rendered)
            book_id = self.book_id(doc.book_name)

            page = self.wiki.call("GET", f"/pages/{self.state.pages[key]}")
            if not isinstance(page, dict):
                page = {}
            page_id = page_id_from(page, f"GET /pages/{self.state.pages[key]}", self.wiki)
            current = page.get("markdown") or ""
            in_place = (
                current.rstrip() == rendered.rstrip()
                and page.get("name") == title
                and page.get("book_id") == book_id
            )
            if in_place:
                unchanged += 1
                continue
            if self.dry_run:
                say(f"would update: {doc.display} -> page {page_id} (book {doc.book_name})")
                updated += 1
                continue
            self.wiki.call("PUT", f"/pages/{page_id}", {"name": title, "markdown": rendered, "book_id": book_id})
            say(f"updated: {doc.display} -> page {page_id} (book {doc.book_name})")
            updated += 1

        present = {norm_key(doc.display) for doc in files}
        for known, page_id in self.state.pages.items():
            if norm_key(known) not in present:
                warn(f"{known} is in sync state but missing from docs/ - wiki page {page_id} left untouched")

        if self.dry_run:
            say(f"dry run: {created} would be created, {updated} would be updated, {unchanged} unchanged")
            return
        self.state.save_if_changed()
        say(f"sync done: {created} created, {updated} updated, {unchanged} unchanged")


# ---------------------------------------------------------------- command line


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        failure = SyncError(
            f"the command line could not be read: {message}",
            "the script did not run, so nothing was synced",
            "run it with no options, with --dry-run, or with --help to see the usage",
        )
        print(failure.render(), file=sys.stderr, flush=True)
        sys.exit(1)


def parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = _Parser(
        prog="sync_docs_wiki.py",
        description="Mirror this project's docs/ folder to its shelf in the BookStack wiki. "
        "Run it from the project root; docs/.wiki-sync.json names the shelf and records the page ids.",
        epilog="Settings: the environment variables BOOKSTACK_URL, BOOKSTACK_TOKEN_ID and "
        "BOOKSTACK_TOKEN_SECRET; if they are not all set, the file named by BOOKSTACK_ENV_FILE, "
        f"or else {OWN_ENV_FILE}, or else {OLDER_ENV_FILE}. A file holds three lines, BOOKSTACK_URL=..., "
        "BOOKSTACK_TOKEN_ID=... and BOOKSTACK_TOKEN_SECRET=... (the older names APP_URL, API_TOKEN_ID and "
        "API_TOKEN_SECRET are read too).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="read the wiki and print what would be created and updated; change nothing and write no file",
    )
    return parser.parse_args(argv)


def _make_output_safe() -> None:
    """Never crash on printing a file name the console cannot show."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _make_output_safe()
    args = parse_args(argv)
    try:
        Syncer(os.getcwd(), args.dry_run, os.environ).run()
    except SyncError as err:
        print(err.render(), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
