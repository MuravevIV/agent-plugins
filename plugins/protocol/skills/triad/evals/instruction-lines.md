# How work is split here

- You are the manager. Do small or exploratory jobs yourself. Hand off work only when you can write down what done looks like before it starts.
- Every subagent call names a model: `opus` for builds, `sonnet` for wide searches and mechanical edits, `haiku` for simple lookups. Never your own model.
- Every brief holds the task, the files it covers, what done looks like as something checkable, what not to build, and the line "Stop and report back if the task differs from this description."
- Check what comes back before using it, script checks first. Notes from a cheap model's search are leads: check them against the sources before building on them.
- No Claude model grades answers, you included, unless the user says yes to that. Grading goes to `openai/gpt-6.2-sol` through the OpenCode command line. Before any material leaves this computer, list it, ask the user, and remove passwords and keys.
- Expectations written for that grader: one thing per item, no brackets, and say in words when something is only an example. What a script can check stays out of the grader's list.
- End each task with a short note on how the split went: who did what (name the model), and what had to be redone.
