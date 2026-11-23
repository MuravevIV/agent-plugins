# Good and bad sections

Calibration pairs for the parts that most often come out wrong.

## Description

Good: says what it does and when to use it, in the user's words.

```
Add a new card type to the payments service: class, registry entry and
config files. Use when the user asks to add, create or register a card
type, or mentions a new card product.
```

Bad: names the topic and stops. The agent cannot tell when to load it.

```
Card type playbook.
```

## Steps

Good: commands, placeholders, a concrete check.

```markdown
1. Create `src/main/kotlin/card/<Name>Card.kt` extending `Card`.
2. Add to `CardRegistry.kt`: `val <NAME> = registerCard("<id>", ::<Name>Card)`.
3. Create the card config at `resources/config/cards/<id>.json`.
4. Run `./gradlew build` and fix any registration errors before continuing.
```

Bad: narrative, tied to the session, nothing to act on.

```markdown
When we did this task, we first had to figure out the card registration
system. Kotlin data classes might be useful here. You should probably look
at existing cards to understand the pattern. Make sure the JSON files are
correct.
```

## Pitfall

Good: names the symptom, gives the fix.

```markdown
- **A missing fee schedule makes card issuance apply zero rates
  silently.** Always create `config/fees/<id>.json` alongside
  `config/cards/<id>.json`.
```

Bad: vague, no fix.

```markdown
- Make sure all config files are present and correct.
```

## Rule

Good: checkable, with the reason.

```markdown
- Do not use `a and b or c` as a ternary, because it returns `c` when `b`
  is false or nil. Use `if/then/else`.
```

Bad: cannot be checked, no reason.

```markdown
- NEVER write unclear conditionals.
```

## Gotcha in a conventions skill

Good: symptom first, then cause and fix, with the version.

```markdown
- A purple and black checkerboard in the inventory means the item has no
  `assets/<ns>/items/<id>.json`. From MC 1.21.4 every item needs one, even
  when `models/item/<id>.json` exists.
```

Bad: states the fact without the symptom the agent will actually see.

```markdown
- Items need definition files.
```

## Done looks like

Good: shape only, placeholders, quick to scan.

```markdown
Input: "Add a <Name> card type"

Output:
- `card/<Name>Card.kt`: new
- `CardRegistry.kt`: one line added
- `config/cards/<id>.json`: new
- `config/fees/<id>.json`: new
- `i18n/en_us.json`: one entry added
```

Bad: pasted implementation.

```markdown
Input: "Add Platinum Card"

Output:
class PlatinumCard(config: CardConfig) : Card(config) {
    override fun validateTransaction(tx: Transaction, account: Account): ValidationResult {
        // ... 40 lines of implementation
    }
}
```

The agent now leans toward this exact class, and the code will be stale
by the next run.

## Checkpoint

Good: says what to show and how it is judged.

```markdown
**Checkpoint: generated files.** Show the list of new files and the
registry diff. Continue when the user confirms the ids and names.
```

Bad: a pause with no purpose.

```markdown
Check with the user here.
```
