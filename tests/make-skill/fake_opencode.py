"""Stand-in for the `opencode` program, used only by test_grade_outside.py.

Reads the prompt from standard input, finds the answer letters and the number of expectations,
and replies according to FAKE_OPENCODE_MODE: ok, not_json, missing_letter, error, hang.
Appends one JSON line per start to the file named by FAKE_OPENCODE_LOG.
"""
import json, os, re, sys, time


def main():
    prompt = sys.stdin.buffer.read().decode("utf-8")
    mode = os.environ.get("FAKE_OPENCODE_MODE", "ok")
    log = os.environ.get("FAKE_OPENCODE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"mode": mode, "pwd_in_env": "PWD" in os.environ, "cwd": os.getcwd(), "argv": sys.argv[1:],
                                "agent_file": os.path.isfile(os.path.join(".opencode", "agent", "outside-grader.md")),
                                "prompt_chars": len(prompt)}) + "\n")
    letters = re.findall(r"^===== ANSWER ([A-Z]) =====$", prompt, flags=re.M)
    m = re.search(r"^===== EXPECTATIONS =====\n(.*?)^===== END EXPECTATIONS =====", prompt, flags=re.M | re.S)
    count = len(re.findall(r"^\d+\. ", m.group(1), flags=re.M)) if m else 0

    def emit(ev):
        sys.stdout.write(json.dumps(ev) + "\n")
        sys.stdout.flush()

    emit({"type": "step_start", "sessionID": "ses_fake", "part": {}})
    if mode == "hang":
        time.sleep(600)
        return 0
    if mode == "error":
        emit({"type": "error", "sessionID": "ses_fake",
              "error": {"name": "ProviderAuthError", "data": {"message": "No credentials found for provider openai"}}})
        return 1
    if mode == "not_json":
        emit({"type": "text", "sessionID": "ses_fake", "part": {"text": "I am sorry, I cannot grade these answers."}})
        return 0
    answers = {}
    for i, l in enumerate(letters):
        exps = [{"n": n, "passed": (n % 2 == 1) if i == 0 else True, "evidence": f"fake evidence {l}{n}"}
                for n in range(1, count + 1)]
        answers[l] = {"expectations": exps, "claims": [{"claim": "fake", "type": "factual", "verified": True, "evidence": "-"}]}
    if mode == "missing_letter" and letters:
        del answers[letters[-1]]
    reply = {"answers": answers, "comparison": f"Answer {letters[-1] if letters else 'A'} is best. Answer A is weaker.",
             "ranking": list(reversed(letters)), "eval_feedback": {"suggestions": [], "overall": "fine"}}
    text = "Here is the grading:\n```json\n" + json.dumps(reply, indent=2) + "\n```\n"
    half = len(text) // 2
    emit({"type": "text", "sessionID": "ses_fake", "part": {"text": text[:half]}})
    emit({"type": "text", "sessionID": "ses_fake", "part": {"text": text[half:]}})
    emit({"type": "step_finish", "sessionID": "ses_fake", "part": {"tokens": {"input": 1000, "output": 200}, "cost": 0.01}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
