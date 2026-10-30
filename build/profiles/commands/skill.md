---
description: Create or update a skill
argument-hint: "<skill name>"
disable-model-invocation: true
---
Create or update the skill "$ARGUMENTS".

Use the repository's existing skill layout. The SKILL.md needs a clear
`description` that says when to use it, a short body, and references only for
material that is too large to load eagerly. Do not duplicate what a top model
already knows; put the repository-specific procedure, commands, and gotchas in
the skill.

Test it by invoking it in a fresh session. If the skill is only for a narrow
workflow, set `disable-model-invocation: true` so it does not enter every
session's skill list. Report the path and how to invoke it.
