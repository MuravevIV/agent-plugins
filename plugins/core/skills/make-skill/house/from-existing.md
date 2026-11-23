# Making a skill from something that already exists

Use this when the user has something that works already and wants it
brought up to the rules in `house/rules.md`: a skill, a plugin, an MCP
server, an extension, a rules file or playbook, or a mix of these, such
as a server with a thin skill on top.

Written from one real conversion on 2026-11-22: two loose skills became
two tool skills and a protocol. Followed for the first time the next
day, on those two tool skills: one had an MCP server beside it, the
other a script in another language. Both went into one plugin and
passed their comparison. Not yet tried: a plugin from another app, an
extension, a live bridge. Treat those parts as a first version.

Two things hold from start to end:

- The original is never changed and never deleted. Work on a copy.
- Add no fact. Move and reshape what is there. Where the original
  leaves something open, ask or say so; do not fill the gap from your
  own knowledge.

## Step 1: Take stock

List what the input is made of, piece by piece, and show the user the
list before going on.

| Piece | Look for |
|---|---|
| Text for the model | Rules, steps, facts, examples |
| Scripts and commands | What each does, what it needs installed, which language |
| Tools of an MCP server | Only the tools the text really uses. Name each one |
| Hooks, slash commands, agents, settings | What starts them and what they change |
| Program code with its own screens | An extension's code. It cannot become a skill |
| Facts of one machine or one project | Addresses, paths, where a key is kept |

Note two more things:

- Who wrote it and under which licence (step 7).
- Where other copies may live: other apps' skill folders, other
  projects. Do not read outside the project without the user's yes.

## Step 2: Sort each piece

One input often becomes more than one thing. Sort by what a piece is,
not by where it stood.

| The piece is | It goes to |
|---|---|
| A fact about a system, true whoever does the work | A tool skill, found by its description |
| The user's own rule about how work is done | A protocol skill, loaded by name (rule 8) |
| A step that runs the same way every time | A script in the skill's `scripts/` folder (rule 4) |
| A call to a tool of an MCP server | Both paths, see step 4 |
| A rule needed on every turn of one project | Lines in that project's instruction file. Say so; it is not a skill |
| Program code with screens, or a hook into an editor | It stays what it is. A skill may say how to use it |
| Advice a strong model follows anyway | Cut it (rule 1) |

- Keep the user's wording for the user's rules. Move them; do not
  rewrite them into your own style.
- A protocol that writes to an outside system names that system and
  says it writes nowhere else (rule 8).
- Show the user the sorted list, and what you were unsure about: names
  that may belong to one project only, versions left open, steps you
  could not place.

Example. On 2026-11-22 the loose skill `plane-protocol` held where the
tracker is and how to call it, and also how the user wants tickets
picked, worked and closed. The first part became the tool skill
`plane`. The second became the protocol `trail`.

## Step 3: Ask where it will live

There are two end states (`house/rules.md`, "How far this skill has to
go"): a skill in one project, or a plugin. A skill loose in the user's
own skills folder is not one.

- Ask which it is, if the user has not said.
- For a plugin, agree on the names with the user before building. Every
  app shows the plugin's name in front of the skill's, so a skill named
  like its plugin reads twice.

## Step 4: An MCP server becomes two paths

A skill may be built where servers are allowed and used where they are
blocked. So whether a server is switched on here decides nothing.
Always build both paths.

- **The script** is the path that must work everywhere, and the one
  that gets tested. It covers the calls found in step 1 and no more.
  The server's other tools stay with the server.
- **The server** is the faster path where it exists.
- **The skill's text** says: use the server's tools when they are
  present, otherwise run the script.

The shape:

```
plugin  <plugin>              installs anywhere; may hold several such skills
└── skill  <name>
    ├── SKILL.md              when to use, the few calls, local facts
    └── scripts/<name>.py     makes the calls

plugin  <name>-mcp            installed only where servers are allowed
└── the server's registration, nothing else
```

Two plugins, so that the server can be switched on and off by itself.
The apps' documents say a blocked server is not started; they do not
say what happens to the rest of a plugin that declares one (looked up
2026-11-22), so do not count on a mixed plugin installing everywhere.

The registration takes the key from the user's environment and holds
no value of its own. Claude Code reads `.mcp.json` at the plugin's top
and fills in `${NAME}`. Copilot's newer plugin format reads `mcp.json`
there; whether it fills in `${NAME}` is not documented. Codex's
documents are unclear on a local server in a plugin. Say in the
plugin's README what was started for real and what was not.

How much work the script is depends on the server:

| The server | The script |
|---|---|
| Wraps a web service | Calls the service itself. Cheap |
| Is a live bridge into a running program | More work: it must connect on every call. Say so and ask whether it is worth it now |
| Does long back-and-forth work with screenshots | Poor value. Leave that work to the server and say so |

Things to get right in the script:

- It reads the key from the environment or from a file the user names,
  and never prints it.
- Services limit calls per minute. Wait and try again.
- Where an employer has switched servers off, the script calls the
  service's own interface. It does not start the same server by
  another route.

## Step 5: Compare with the original

The new thing has to do at least what the old one did.

- Answer each test case twice: with the new version and with the
  original. `run_tests.py --compare-with <original>` does that. Load
  both the same way.
- Checks a script can decide come first. Where the skill acts on an
  outside system, let the runs act on the real one in a throwaway
  project and read the facts back afterwards. A case can prepare its
  run with a `setup` script (`house/testing.md`).
- A script gets unit tests against a stand-in for the service, never
  against the real one. The stand-in only shows what the script's
  writer assumed, so afterwards try each command once by hand against
  a throwaway place in the real system.
- A script that replaces another gets a mode that changes nothing, and
  is run in that mode on real data next to the old one. The two have
  to agree before the new one writes anything.
- Say in `TEST-RESULT.md` what this comparison cannot show: with no
  side that has no skill at all, it proves the new version is no worse
  than the old one, not that either is needed.

## Step 6: Retire the original safely

Do this on the user's word, after the new version is in place.

1. Park the original where the app no longer loads it. Never delete it.
2. Look for other copies and for mentions of the old name: other
   projects' instruction files, other apps' skill folders. Ask before
   searching outside the project.
3. Fix a mention where the file is read only by the app that changed.
   Leave a file that other apps read as well, and add a line that maps
   the names for this app.
4. Leave other apps' own copies alone and tell the user they exist.
5. Tell the user that sessions already open keep the old names until
   they are restarted.

## Step 7: Other people's work

- Keep the licence file. List what you changed, as `house/CHANGES.md`
  does for this skill.
- Or leave their files unchanged and put your own layer next to them.
  A pack copied unchanged into a plugin is recorded as "untested".

## Promoting a skill from one project to a plugin

A skill that lives in one project is to be used elsewhere. Follow the
steps above, with these additions.

1. **Ask first whether it is wanted outside its project.** A second
   project that needs it, or another app. If there is none, it stays
   where it is: a project skill is a valid end state, and a skill about
   one repository belongs in that repository.
2. **In step 1, also list what belongs to the home project**: paths,
   project and folder names, ticket prefixes, versions. For each one,
   make it general, turn it into a setting, or keep it and say in the
   text whose fact it is. `pack_skill.py add` prints the absolute paths
   and the home folder's name it finds; the rest needs reading.
3. **The test is now required** (rule 1). The best cases are real
   requests from the home project. Ask before reading its session
   history.
4. **Ask where it should be on.** For the user in every project, or
   only in projects that switch its plugin on
   (`pack_skill.py enable`). A skill for one kind of work is off unless
   a project needs it.
5. **In step 6, the home project comes first.** Park its local copy and
   switch the plugin on there. Otherwise that project sees the skill
   twice.
6. **Several projects with their own versions.** Lay the differences
   side by side and let the user say which wording wins. Then make one
   skill and park every copy.

## What to tell the user at the end

In a few lines: what became what, what was parked and where, what was
left alone, what the comparison showed, and what you were unsure about.
