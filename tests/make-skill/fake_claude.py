"""A stand-in for the claude program, used only by test_run_tests.py.

Behaviour is set by environment variables:
  FAKE_CLAUDE_MODE    ok (default), not_signed_in, error, hang
  FAKE_CLAUDE_LOG     if set, one line is added to this file per start
  FAKE_CLAUDE_EXTRA_SKILLS  comma-separated skill names to list as if they were in the user's own setup
  FAKE_CLAUDE_DENY    comma-separated tool names to report as not allowed
  FAKE_CLAUDE_HIDE_SKILLS   if set, installed skills are left out of the list (the app "did not see" them)
  FAKE_CLAUDE_NO_SKILL_CALL if set, the skill is listed but never called
A CLAUDE.md found in the work folder is copied into made-by-run.txt after "claude_md: ".
"""
import json
import os
import sys
import time
from pathlib import Path


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    prompt = sys.stdin.buffer.read().decode("utf-8")
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    log = os.environ.get("FAKE_CLAUDE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"cwd": os.getcwd(), "argv": sys.argv[1:], "mode": mode}) + "\n")

    skills_dir = Path(".claude") / "skills"
    skills = sorted(p.name for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else []
    extra = [s for s in os.environ.get("FAKE_CLAUDE_EXTRA_SKILLS", "").split(",") if s]
    listed = [] if os.environ.get("FAKE_CLAUDE_HIDE_SKILLS") else skills
    emit({"type": "system", "subtype": "init", "skills": listed + extra, "model": "claude-fake-1",
          "permissionMode": "default", "tools": ["Read", "Write", "Skill"], "plugins": []})

    if mode == "hang":
        time.sleep(60)
        return 0
    if mode == "not_signed_in":
        emit({"type": "result", "subtype": "success", "is_error": True,
              "result": "Not logged in · Please run /login", "duration_ms": 5, "num_turns": 1})
        return 1
    if mode == "error":
        emit({"type": "result", "subtype": "error_during_execution", "is_error": True,
              "result": "Something broke inside the fake app", "duration_ms": 5, "num_turns": 1})
        return 1

    content = [{"type": "text", "text": "Working on it."}]
    if listed and not os.environ.get("FAKE_CLAUDE_NO_SKILL_CALL"):
        content.append({"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": skills[0]}})
    emit({"type": "assistant", "message": {"content": content}})
    installed = sorted(p.relative_to(skills_dir).as_posix() for p in skills_dir.rglob("*")) if skills_dir.is_dir() else []
    claude_md = Path("CLAUDE.md")
    seen_md = "claude_md: " + claude_md.read_text(encoding="utf-8") + "\n" if claude_md.is_file() else ""
    Path("made-by-run.txt").write_text("prompt: " + prompt + "\n" + seen_md + "installed:\n" + "\n".join(installed)
                                       + "\n", encoding="utf-8")
    denials = [{"tool_name": t, "tool_use_id": "x", "tool_input": {}}
               for t in os.environ.get("FAKE_CLAUDE_DENY", "").split(",") if t]
    emit({"type": "result", "subtype": "success", "is_error": False, "result": "The answer to: " + prompt,
          "duration_ms": 1234, "total_cost_usd": 0.0123, "num_turns": 2,
          "usage": {"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 30,
                    "cache_read_input_tokens": 40},
          "permission_denials": denials})
    return 0


if __name__ == "__main__":
    sys.exit(main())
