# Test result template

Copy the block into `TEST-RESULT.md` in the skill's folder and fill it.
Add a new block on top for each later round; keep the old ones.

````markdown
# Test result: <skill-name>

## <date>

- **Decision:** <keep | shrink | drop | untested (the user chose to skip the test)>
- **What was tested:** <the whole skill, or which part; which version>
- **Test cases:** <how many>, of which <n> real and <n> made up
- **Where the real cases came from:** <the session it was made from, past requests, ...>
- **Who answered:** <app and model>
- **Who graded:** <script checks | the user, by reading | outside model, which one | same model family>
- **With the skill:** <what came out, in one or two lines or a count>
- **Without the skill:** <the same, or "not compared" and why>
- **What the difference was:** <one or two plain sentences>
- **Would one line in the project instruction file do?** <yes, which line | no, why>
- **Not covered:** <what these tests could not show>
````

If the decision is "untested", only the first two lines and "Not covered"
need filling.
