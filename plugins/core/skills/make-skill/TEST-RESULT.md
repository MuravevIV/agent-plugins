# Test result: make-skill

## 2026-11-22

- **Decision:** untested (the user chose to skip the test)
- **What was tested:** nothing by comparison. A fair test would set `make-skill` against Anthropic's unchanged `skill-creator` on a few skill-making tasks. The user chose on 2026-11-22 to skip it for now: such runs are long and costly, and the fork changes little of Anthropic's text.
- **Not covered:**
  - Whether the house rules in `house/` make a better skill than Anthropic's process alone. Not compared.
  - Whether a model follows the house rules when it is only told to make a skill, with nobody steering it. Not tried.
  - Copilot and Codex. The skill has only been used in Claude Code.

### What one real use showed

This is one use with the author steering it, so it is a record and no proof.

The Triad skill (now `triad` in the plugin `protocol`) was made and tested with `make-skill` on 2026-11-22.

- The comparison that rule 1 asks for did its job. With a third side added (no skill, seven lines in the project's instruction file), it showed that the skill as first drafted was not opened for a plain request and did worse than the seven lines.
- The two scripts worked: `run_tests.py` made 54 runs and two small retests, and `grade_outside.py` sent the judged checks to the outside grader after the user's yes.
- The process got one thing wrong. Its first decision, "shrink", judged the skill as something the model finds by its description. The user loads that skill by name, and it took the user to point this out. House rule 8 and the `--load-by-name` option were added because of it.
- The filing script filed the result into a plugin, and Claude Code loaded it from there.
