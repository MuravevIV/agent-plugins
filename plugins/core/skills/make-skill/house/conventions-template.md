# Conventions skill template

For standards, library usage patterns and gotchas that apply across many
tasks in one domain. It says "when you do X, do it this way". It has no
ordered steps toward a single result: that is a procedure.

````markdown
---
name: <domain>
description: <What the conventions cover and when to apply them: the kinds of files, libraries or work that should bring this skill up.>
---

# <Domain>

<One to three sentences: what this covers and when to apply it. State the
version it was written against if the facts depend on one.>

## Rules

### <Topic>

- <Rule>, because <reason>.
- <Symptom> means <cause>. <What to do.>

### <Topic>

- <Rule>.

## Patterns

### <What the snippet shows>

```<language>
<the smallest snippet that settles how a rule is applied>
```

## Avoid

- <The wrong move>. <Why it fails, or what to do in its place.>

## References

- <Link or path for deeper reading.>
````

## Filling it in

- **Keep rules checkable.** An agent should be able to look at its own
  output and tell whether it complied. "Write clean code" fails that test.
  "Wrap at 120 characters" passes.
- **Drop the defaults.** Leave out anything a model does unprompted. The
  value is in what was surprising: a setting inherited silently, an API
  that changed between versions, a signature the agent guessed wrong.
- **Write gotchas as symptom, cause, fix.** The next agent meets the
  symptom first, so that is what it will search the skill for.
- **Pin versions.** A fact that holds only from some version on carries
  that version. Without it the rule turns into a wrong claim after the
  next release.
- **Group by topic** once there are more than about ten rules, so the
  agent can jump to the part it needs.
- **Formatting belongs to a formatter.** Indentation, line length and
  brace spacing are enforced more reliably by a formatter or linter
  config than by a prompt. If the project has one, point to it. Keep only
  the style rules no tool can enforce.
- **Distill, do not paste.** When working from an external rulebook, keep
  the rules that matter in this project and link the source in References.
- **Snippets stay minimal.** Enough to remove doubt about a rule. Use
  placeholders where the name does not matter.
- **Include at least one "Avoid" entry** when the session produced one.
  The mistakes that already happened are the ones most likely to recur.
- **Split when it sprawls.** If the body grows past a couple of hundred
  lines, move a sub-domain into its own skill or into a `references/` file
  the body points to.
