"""Reads back what each run of the bookstack tool skill's test did, from the wiki and from the run's folder.

  python check_runs.py <workspace>/iteration-N

Writes checks.json and grading.json into every run folder and prints a table. A script decides everything.
The runs must have been made with --keep-work, because the mapping file is read from the run's work folder.
Used once, on this PC, on 2026-11-23.
"""
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki_api as W  # noqa: E402


def row(text: str, passed: Any, evidence: Any) -> Dict[str, Any]:
    return {"text": text, "passed": bool(passed), "evidence": str(evidence)[:400]}


def tool_calls(run: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    events = run / "events.jsonl"
    if not events.is_file():
        return counts
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        message = ev.get("message") if isinstance(ev, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = str(block.get("name", "?"))
                text = json.dumps(block.get("input") or {})
                if "sync_docs_wiki.py" in text or "sync-docs-wiki.ps1" in text:
                    name = f"{name}, the sync script"
                counts[name] = counts.get(name, 0) + 1
    return counts


def by_key(pages: Dict[str, Any], rel: str) -> Optional[int]:
    """The page id the mapping gives a path, whichever slash its keys use."""
    for key, value in pages.items():
        if key.replace("\\", "/") == rel:
            return int(value)
    return None


def check_run(run: Path) -> Dict[str, Any]:
    meta = json.loads((run / "wiki-shelf.json").read_text(encoding="utf-8"))
    case, before = str(meta["case"]), meta.get("pages_before") or {}
    shelf = W.shelf_pages(meta["shelf"])
    books = shelf["books"] if shelf else []
    pages = [dict(p, book=b["name"]) for b in books for p in b["pages"]]
    state_file = run / "work" / "docs" / ".wiki-sync.json"
    mapping: Dict[str, Any] = {}
    if state_file.is_file():
        try:
            mapping = json.loads(state_file.read_text(encoding="utf-8-sig")).get("pages") or {}
        except ValueError:
            mapping = {}
    ids = sorted(p["id"] for p in pages)
    named = {p["name"]: p for p in pages}
    overview, roadmap = named.get("Overview"), named.get("Roadmap")
    link = re.search(r"\]\((\S*?/link/(\d+))(#[^)]*)?\)", overview["markdown"]) if overview else None

    if case == "1":
        rows = [row("The shelf exists and has exactly two pages", shelf and len(pages) == 2,
                    [(p["book"], p["name"]) for p in pages] if shelf else "no such shelf"),
                row("The pages sit in books named Notes and Plans", sorted(b["name"] for b in books) == ["Notes", "Plans"],
                    [b["name"] for b in books]),
                row("The mapping file holds the ids of both pages",
                    len(ids) == 2 and sorted(int(v) for v in mapping.values()) == ids, mapping),
                row("The overview page links to the roadmap page by permalink and keeps the anchor",
                    link and roadmap and int(link.group(2)) == roadmap["id"] and link.group(3) == "#next",
                    link.group(0) if link else "no permalink in the overview page"),
                row("The outside link in the overview page is unchanged",
                    overview and "(https://example.invalid/tally)" in overview["markdown"],
                    "found" if overview and "(https://example.invalid/tally)" in overview["markdown"] else "not found"),
                row("No page starts with its own title as a heading",
                    pages and not any(p["markdown"].lstrip().startswith("# ") for p in pages),
                    [p["markdown"].lstrip()[:30] for p in pages])]
    elif case == "2":
        rows = [row("The roadmap page on the wiki contains Count by word",
                    roadmap and "Count by word" in roadmap["markdown"],
                    roadmap["markdown"][-120:] if roadmap else "no roadmap page"),
                row("The shelf still has exactly two pages", len(pages) == 2, [(p["book"], p["name"]) for p in pages]),
                row("Both pages have the ids they had before", ids == sorted(int(v) for v in before.values()),
                    f"before {sorted(before.values())}, now {ids}")]
    else:
        work = run / "work" / "docs" / "plans"
        old_id = by_key(before, "plans/roadmap.md")
        rows = [row("docs/plans/plan-2027.md exists and docs/plans/roadmap.md does not",
                    (work / "plan-2027.md").is_file() and not (work / "roadmap.md").exists(),
                    sorted(p.name for p in work.glob("*")) if work.is_dir() else "no docs/plans folder"),
                row("The mapping file gives the new path the page id the old path had",
                    old_id is not None and by_key(mapping, "plans/plan-2027.md") == old_id
                    and by_key(mapping, "plans/roadmap.md") is None, mapping),
                row("The shelf still has exactly two pages", len(pages) == 2, [(p["book"], p["name"]) for p in pages]),
                row("The overview page still links to that page by permalink",
                    link and old_id is not None and int(link.group(2)) == old_id,
                    link.group(0) if link else "no permalink in the overview page")]

    passed = sum(1 for r in rows if r["passed"])
    record = json.loads((run / "run.json").read_text(encoding="utf-8")) if (run / "run.json").is_file() else {}
    timing = json.loads((run / "timing.json").read_text(encoding="utf-8")) if (run / "timing.json").is_file() else {}
    facts = {"case": case, "arm": meta["arm"], "shelf": meta["shelf"], "status": record.get("status"),
             "cost_usd": timing.get("cost_usd"), "seconds": timing.get("total_duration_seconds"),
             "turns": record.get("num_turns"), "refused_tool_calls": len(record.get("permission_denials") or []),
             "skill_opened": record.get("skill_used"), "tool_calls": tool_calls(run),
             "pages": [(p["book"], p["name"], p["id"]) for p in pages], "mapping": mapping,
             "passed": passed, "total": len(rows)}
    (run / "checks.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")
    (run / "grading.json").write_text(json.dumps({
        "expectations": rows, "graded_by": "check_runs.py (a script; no model graded)",
        "summary": {"passed": passed, "failed": len(rows) - passed, "total": len(rows),
                    "pass_rate": round(passed / len(rows), 2)}}, indent=2, ensure_ascii=False), encoding="utf-8")
    return facts


def main() -> None:
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        sys.exit("Give the iteration folder, for example: python check_runs.py C:/make-skill-runs/tool-bookstack/iteration-1")
    runs = sorted(p.parent for p in Path(sys.argv[1]).glob("eval-*/*/run-*/wiki-shelf.json"))
    if not runs:
        sys.exit(f"No run with a wiki-shelf.json under {sys.argv[1]}.")
    facts: List[Dict[str, Any]] = []
    for run in runs:
        try:
            facts.append(check_run(run))
        except W.WikiProblem as e:
            sys.exit(f"Could not read the wiki for {run}: {e}")
    for f in facts:
        print(f"case {f['case']} {f['arm']:<10} {f['passed']} of {f['total']}  ${f['cost_usd'] or 0:.2f}  "
              f"{f['seconds']} s  {f['turns']} turns  skill opened: {f['skill_opened']}  "
              f"refused: {f['refused_tool_calls']}  calls: {f['tool_calls']}")
    for arm in sorted({f["arm"] for f in facts}):
        mine = [f for f in facts if f["arm"] == arm]
        print(f"{arm} in all: {sum(f['passed'] for f in mine)} of {sum(f['total'] for f in mine)}, "
              f"${sum(f['cost_usd'] or 0 for f in mine):.2f}, {sum(f['seconds'] or 0 for f in mine):.0f} s, "
              f"{sum(f['turns'] or 0 for f in mine)} turns")


if __name__ == "__main__":
    main()
