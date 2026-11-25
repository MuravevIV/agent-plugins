# Test result: phrases

## 2026-11-25

- **Decision:** untested (the user chose to skip the test)
- **What was tested:** nothing
- **Not covered:** everything; nobody knows yet whether this skill helps

### Checked on 2026-11-25

- Two small runs of `claude-haiku-5-5` from an empty folder, with the plugin installed for the user and a message
  starting "autopilot preflight": both opened `core:phrases` by themselves and found the line the plan has to end
  with.
- The first version kept the procedure in a file of its own, `phrases/autopilot-preflight.md`. Both runs opened
  the skill but were refused reading that file: a plugin's files lie outside the user's project, and a session
  without the user at hand gets no permission prompt. The procedure moved into `SKILL.md`, which loads with the
  skill, and the check passed.
- Not tried: a real preflight, the "go" rule, the time quota during a run.
